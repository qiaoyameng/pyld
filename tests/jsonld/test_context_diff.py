"""Tests for pyld.context_diff.compare_contexts."""

import copy
import json

from pyld import FrozenDocumentLoader, compare_contexts, jsonld

BASE = 'https://base.example/doc'
OPTIONS = {'base': BASE}


def _change(report, term):
    """Finds the change entry for a term."""
    for entry in report['changes']:
        if entry['term'] == term:
            return entry
    raise AssertionError(f'no change reported for {term!r}')


def _assert_witness_replays(report, options=None):
    """Every witness document must replay through jsonld.expand as reported."""
    options = options or OPTIONS
    for entry in report['changes']:
        witness = entry['witness']
        for side in ('old', 'new'):
            document = witness[f'{side}_document']
            error = witness[f'{side}_error']
            if error is None:
                assert (
                    jsonld.expand(document, dict(options))
                    == witness[f'{side}_expansion']
                )
            else:
                try:
                    jsonld.expand(document, dict(options))
                    raise AssertionError('expected expansion to fail')
                except jsonld.JsonLdError as e:
                    assert e.code == error['code']


def test_identical_contexts_report_no_changes():
    """Identical contexts produce an empty report."""
    ctx = {'ex': 'http://example.com/', 'name': 'ex:name'}
    report = compare_contexts(ctx, ctx, base=BASE)
    assert report['changes'] == []
    assert report['undetermined'] == []
    assert report['errors'] == []
    assert report['summary'] == {'changes': 0, 'undetermined': 0, 'errors': 0}


def test_equivalent_prefix_spellings_do_not_alert():
    """A compact IRI and its absolute form are equivalent definitions."""
    old = {'ex': 'http://example.com/', 'name': 'ex:name'}
    new = {
        'ex': 'http://example.com/',
        'name': {'@id': 'http://example.com/name'},
    }
    report = compare_contexts(old, new, base=BASE)
    assert report['changes'] == []
    assert report['undetermined'] == []


def test_dropped_prefix_term_is_reported():
    """Removing a prefix reinterprets inputs using prefix:suffix keys."""
    old = {'ex': 'http://example.com/', 'name': 'ex:name'}
    new = {'name': {'@id': 'http://example.com/name'}}
    report = compare_contexts(old, new, base=BASE)
    entry = _change(report, 'ex')
    assert entry['kinds'] == ['removed']
    witness = entry['witness']
    assert witness['old_expansion'] == [
        {'http://example.com/witness': [{'@value': 'value'}]}
    ]
    # without the prefix, ex:witness is kept as a scheme-like absolute IRI
    assert witness['new_expansion'] == [{'ex:witness': [{'@value': 'value'}]}]
    _assert_witness_replays(report)


def test_term_iri_change_has_replayable_witness():
    """A changed term IRI is reported with both expansion results."""
    old = {'name': 'http://example.com/old-name'}
    new = {'name': 'http://example.com/new-name'}
    report = compare_contexts(old, new, base=BASE)
    entry = _change(report, 'name')
    assert entry['kinds'] == ['iri']
    witness = entry['witness']
    assert witness['old_expansion'] == [
        {'http://example.com/old-name': [{'@value': 'value'}]}
    ]
    assert witness['new_expansion'] == [
        {'http://example.com/new-name': [{'@value': 'value'}]}
    ]
    _assert_witness_replays(report)


def test_set_to_list_container_change_witness():
    """@set versus @list is visible in the witness expansion."""
    old = {'tags': {'@id': 'http://example.com/tags', '@container': '@set'}}
    new = {'tags': {'@id': 'http://example.com/tags', '@container': '@list'}}
    report = compare_contexts(old, new, base=BASE)
    entry = _change(report, 'tags')
    assert entry['kinds'] == ['container']
    witness = entry['witness']
    assert witness['old_expansion'] == [
        {'http://example.com/tags': [{'@value': 'alpha'}, {'@value': 'beta'}]}
    ]
    assert witness['new_expansion'] == [
        {
            'http://example.com/tags': [
                {'@list': [{'@value': 'alpha'}, {'@value': 'beta'}]}
            ]
        }
    ]
    _assert_witness_replays(report)


def test_language_map_container_change_witness():
    """Adding an @language container changes map keys into language tags."""
    old = {'label': 'http://example.com/label'}
    new = {'label': {'@id': 'http://example.com/label', '@container': '@language'}}
    report = compare_contexts(old, new, base=BASE)
    entry = _change(report, 'label')
    assert 'container' in entry['kinds']
    witness = entry['witness']
    assert witness['new_expansion'] == [
        {
            'http://example.com/label': [
                {'@value': 'hallo', '@language': 'de'},
                {'@value': 'hello', '@language': 'en'},
            ]
        }
    ]
    _assert_witness_replays(report)


def test_type_coercion_change_witness():
    """A changed @type coercion shows up in the expanded value."""
    old = {'count': 'http://example.com/count'}
    new = {
        'count': {
            '@id': 'http://example.com/count',
            '@type': 'http://www.w3.org/2001/XMLSchema#integer',
        }
    }
    report = compare_contexts(old, new, base=BASE)
    entry = _change(report, 'count')
    assert entry['kinds'] == ['type_coercion']
    witness = entry['witness']
    assert witness['old_expansion'] == [
        {'http://example.com/count': [{'@value': '42'}]}
    ]
    assert witness['new_expansion'] == [
        {
            'http://example.com/count': [
                {
                    '@value': '42',
                    '@type': 'http://www.w3.org/2001/XMLSchema#integer',
                }
            ]
        }
    ]
    _assert_witness_replays(report)


def test_id_type_coercion_change_witness():
    """An @type: @id coercion turns string values into node references."""
    old = {'homepage': 'http://example.com/homepage'}
    new = {'homepage': {'@id': 'http://example.com/homepage', '@type': '@id'}}
    report = compare_contexts(old, new, base=BASE)
    entry = _change(report, 'homepage')
    assert entry['kinds'] == ['type_coercion']
    witness = entry['witness']
    assert witness['new_expansion'] == [
        {'http://example.com/homepage': [{'@id': 'https://example.com/target'}]}
    ]
    _assert_witness_replays(report)


def test_language_coercion_change_witness():
    """A changed @language coercion retags literal values."""
    old = {'label': {'@id': 'http://example.com/label', '@language': 'en'}}
    new = {'label': {'@id': 'http://example.com/label', '@language': 'de'}}
    report = compare_contexts(old, new, base=BASE)
    entry = _change(report, 'label')
    assert entry['kinds'] == ['language']
    witness = entry['witness']
    assert witness['old_expansion'][0]['http://example.com/label'] == [
        {'@value': 'hello', '@language': 'en'}
    ]
    assert witness['new_expansion'][0]['http://example.com/label'] == [
        {'@value': 'hello', '@language': 'de'}
    ]
    _assert_witness_replays(report)


def test_reverse_change_witness():
    """Switching a term to @reverse moves values under @reverse."""
    old = {'knows': {'@id': 'http://xmlns.com/foaf/0.1/knows'}}
    new = {'knows': {'@reverse': 'http://xmlns.com/foaf/0.1/knows'}}
    report = compare_contexts(old, new, base=BASE)
    entry = _change(report, 'knows')
    assert 'reverse' in entry['kinds']
    witness = entry['witness']
    assert witness['old_expansion'] == [
        {'http://xmlns.com/foaf/0.1/knows': [{'@id': 'https://example.com/target'}]}
    ]
    assert witness['new_expansion'] == [
        {
            '@reverse': {
                'http://xmlns.com/foaf/0.1/knows': [
                    {'@id': 'https://example.com/target'}
                ]
            }
        }
    ]
    _assert_witness_replays(report)


def test_protected_term_redefinition_error_witness():
    """Dropping @protected is witnessed by a redefinition that now succeeds."""
    old = {'name': {'@id': 'http://example.com/name', '@protected': True}}
    new = {'name': {'@id': 'http://example.com/name'}}
    report = compare_contexts(old, new, base=BASE)
    entry = _change(report, 'name')
    assert entry['kinds'] == ['protected']
    witness = entry['witness']
    assert witness['old_error']['code'] == 'protected term redefinition'
    assert witness['new_error'] is None
    assert witness['new_expansion'] != []
    _assert_witness_replays(report)


def test_added_and_removed_terms_are_reported():
    """Terms present on only one side are reported as added or removed."""
    old = {'gone': 'http://example.com/gone'}
    new = {'fresh': 'http://example.com/fresh'}
    report = compare_contexts(old, new, base=BASE)
    added = _change(report, 'fresh')
    removed = _change(report, 'gone')
    assert added['kinds'] == ['added']
    assert added['old'] is None
    assert removed['kinds'] == ['removed']
    assert removed['new'] is None
    # the removed term no longer expands with the new context
    assert removed['witness']['new_expansion'] == []
    assert removed['witness']['old_expansion'] == [
        {'http://example.com/gone': [{'@value': 'value'}]}
    ]
    _assert_witness_replays(report)


def test_remote_contexts_are_loaded_via_document_loader():
    """Remote context references are resolved through the given loader."""
    loader = FrozenDocumentLoader(
        documents={
            'https://example.com/ctx': {'@context': {'name': 'http://schema.org/name'}}
        }
    )
    report = compare_contexts(
        'https://example.com/ctx',
        {'name': 'http://schema.org/fullname'},
        base=BASE,
        document_loader=loader,
    )
    entry = _change(report, 'name')
    assert entry['kinds'] == ['iri']
    assert entry['old']['@id'] == 'http://schema.org/name'
    assert entry['new']['@id'] == 'http://schema.org/fullname'


def test_unreachable_remote_context_is_undetermined():
    """A context that cannot be loaded lists its terms as undetermined."""
    loader = FrozenDocumentLoader(documents={})
    report = compare_contexts(
        'https://missing.example/ctx',
        {'name': 'http://schema.org/name'},
        base=BASE,
        document_loader=loader,
    )
    assert report['changes'] == []
    assert len(report['errors']) == 1
    assert report['errors'][0]['context'] == 'old'
    assert report['errors'][0]['code'] == 'loading remote context failed'
    terms = [entry['term'] for entry in report['undetermined']]
    assert terms == ['name']


def test_protected_redefinition_inside_new_context_is_an_error():
    """A new context that redefines a protected remote term is reported."""
    loader = FrozenDocumentLoader(
        documents={
            'https://example.com/ctx': {
                '@context': {
                    'name': {
                        '@id': 'http://schema.org/name',
                        '@protected': True,
                    }
                }
            }
        }
    )
    new = [
        'https://example.com/ctx',
        {'name': {'@id': 'http://schema.org/fullname'}},
    ]
    report = compare_contexts(
        'https://example.com/ctx', new, base=BASE, document_loader=loader
    )
    assert report['changes'] == []
    assert any(
        error['code'] == 'protected term redefinition'
        for error in report['errors']
        if error['context'] == 'new'
    )


def test_scoped_context_change_is_undetermined():
    """Terms with differing scoped contexts cannot be decided."""
    old = {
        'name': {
            '@id': 'http://example.com/name',
            '@context': {'sub': 'http://example.com/old-sub'},
        }
    }
    new = {
        'name': {
            '@id': 'http://example.com/name',
            '@context': {'sub': 'http://example.com/new-sub'},
        }
    }
    report = compare_contexts(old, new, base=BASE)
    assert report['changes'] == []
    assert len(report['undetermined']) == 1
    entry = report['undetermined'][0]
    assert entry['term'] == 'name'
    assert 'scoped_context' in entry['kinds']
    assert 'reason' in entry


def test_default_language_change_is_reported():
    """A changed context-level @language default is witnessed."""
    old = {'@language': 'en', 'label': 'http://example.com/label'}
    new = {'@language': 'de', 'label': 'http://example.com/label'}
    report = compare_contexts(old, new, base=BASE)
    entry = _change(report, '@language')
    assert entry['kinds'] == ['language']
    witness = entry['witness']
    assert witness['old_expansion'] == [
        {'https://example.com/predicate': [{'@value': 'hello', '@language': 'en'}]}
    ]
    assert witness['new_expansion'] == [
        {'https://example.com/predicate': [{'@value': 'hello', '@language': 'de'}]}
    ]
    _assert_witness_replays(report)


def test_vocab_change_is_reported_with_term_witness():
    """A changed @vocab rewrites every vocab-relative term IRI."""
    old = {'@vocab': 'http://old.example/', 'name': None}
    new = {'@vocab': 'http://new.example/', 'name': None}
    report = compare_contexts(old, new, base=BASE)
    entry = _change(report, '@vocab')
    assert entry['kinds'] == ['vocab']
    _assert_witness_replays(report)


def test_inputs_are_not_mutated():
    """Neither context is modified by the comparison."""
    old = {
        'ex': 'http://example.com/',
        'tags': {'@id': 'ex:tags', '@container': '@list'},
        'name': {'@id': 'ex:name', '@protected': True},
    }
    new = {
        'ex': 'http://example.com/',
        'tags': {'@id': 'ex:tags', '@container': '@set'},
        'name': {'@id': 'ex:other'},
    }
    old_snapshot = copy.deepcopy(old)
    new_snapshot = copy.deepcopy(new)
    compare_contexts(old, new, base=BASE)
    assert old == old_snapshot
    assert new == new_snapshot


def test_report_is_json_serializable():
    """The whole report can be serialized as JSON."""
    old = {'tags': {'@id': 'http://example.com/tags', '@container': '@set'}}
    new = {'tags': {'@id': 'http://example.com/tags', '@container': '@list'}}
    report = compare_contexts(old, new, base=BASE)
    json.dumps(report)


def test_base_is_used_for_relative_witness_iris():
    """The fixed base is reflected in the report and expansions."""
    old = {'@base': 'https://old.example/'}
    new = {'@base': 'https://new.example/'}
    report = compare_contexts(old, new, base=BASE)
    assert report['base'] == BASE
    entry = _change(report, '@base')
    assert entry['witness']['old_expansion'][0]['@id'] == 'https://old.example/item'
    assert entry['witness']['new_expansion'][0]['@id'] == 'https://new.example/item'
    _assert_witness_replays(report)
