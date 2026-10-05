"""
Tests for expansion diagnostics: an optional per-field record of why a
source field did not make it into the expanded output, located by JSON
Pointer and annotated with the context layers in effect.
"""

import pyld.jsonld as jsonld
from pyld.documentloader.base import DocumentLoader


def resolve_pointer(document, pointer):
    """Resolves an RFC 6901 JSON Pointer against a source document."""
    current = document
    if pointer == '':
        return current
    for segment in pointer.lstrip('/').split('/'):
        segment = segment.replace('~1', '/').replace('~0', '~')
        if isinstance(current, list):
            current = current[int(segment)]
        else:
            current = current[segment]
    return current


def source_kinds(diagnostic):
    return [source['kind'] for source in diagnostic['contextSource']]


def test_diagnostics_disabled_by_default():
    """
    Expansion without the diagnostics option neither requires nor
    produces diagnostics, and the return value is unchanged.
    """
    input = {'unknown': 'dropped'}
    assert jsonld.expand(input) == []
    assert jsonld.expand(input, {}) == []


def test_diagnostics_do_not_change_expansion_result():
    """
    Enabling diagnostics must not change the expanded output, including
    the existing handling of null values and relative IRIs.
    """
    input = {
        '@context': {'ex': 'http://example.com/', 'name': 'ex:name'},
        'name': 'kept',
        'nothing': None,
        'unknown': 'dropped',
    }
    expected = jsonld.expand(input)
    diagnostics = []
    got = jsonld.expand(input, {'diagnostics': diagnostics})
    assert got == expected
    assert {d['pointer'] for d in diagnostics} == {'/nothing', '/unknown'}


def test_diagnostics_keep_on_property_dropped_callback():
    """
    The legacy on_property_dropped callback still fires when diagnostics
    are enabled.
    """
    dropped = []
    diagnostics = []
    jsonld.expand(
        {'unknown': 'dropped'},
        {'diagnostics': diagnostics},
        on_property_dropped=dropped.append,
    )
    assert dropped == ['unknown']
    assert [d['key'] for d in diagnostics] == ['unknown']


def test_diagnostics_pointer_escapes_keys():
    """
    Keys containing '~' or '/' are escaped as '~0' and '~1' so the
    pointer resolves back to the exact source field.
    """
    input = {
        '@context': {'ex': 'http://example.com/', 'nested': 'ex:nested'},
        'tilde~key': 1,
        'slash/key': 2,
        'nested': {'deep/tilde~': 3},
    }
    diagnostics = []
    jsonld.expand(input, {'diagnostics': diagnostics})
    pointers = {d['pointer'] for d in diagnostics}
    assert pointers == {'/tilde~0key', '/slash~1key', '/nested/deep~1tilde~0'}
    for diagnostic in diagnostics:
        resolve_pointer(input, diagnostic['pointer'])


def test_diagnostics_reason_undefined_term():
    """
    A key with no term definition and no @vocab is reported as an
    undefined term.
    """
    diagnostics = []
    jsonld.expand({'unknown': 'dropped'}, {'diagnostics': diagnostics})
    assert diagnostics[0]['reason'] == 'undefined term'
    assert diagnostics[0]['expandedProperty'] == 'unknown'


def test_diagnostics_reason_not_an_absolute_iri():
    """
    A key whose vocabulary expansion is not an absolute IRI is reported
    as not an absolute IRI, distinctly from an undefined term.
    """
    input = {
        '@context': {'@vocab': 'http://example.com/'},
        'bad key': 'dropped',
    }
    diagnostics = []
    jsonld.expand(input, {'diagnostics': diagnostics})
    assert diagnostics[0]['reason'] == 'not an absolute IRI'
    assert diagnostics[0]['expandedProperty'] == 'http://example.com/bad key'


def test_diagnostics_reason_null_value():
    """
    A defined term with a null value is reported as a null value drop.
    """
    input = {
        '@context': {'ex': 'http://example.com/', 'name': 'ex:name'},
        'name': None,
    }
    diagnostics = []
    assert jsonld.expand(input, {'diagnostics': diagnostics}) == []
    assert diagnostics[0]['reason'] == 'null value'
    assert diagnostics[0]['pointer'] == '/name'


def test_diagnostics_pointer_through_arrays_and_lists():
    """
    Pointers track array indices, including inside @list containers.
    """
    input = {
        '@context': {
            'ex': 'http://example.com/',
            'known': 'ex:known',
            'items': {'@id': 'ex:items', '@container': '@list'},
        },
        'items': [
            {'unknown-first': 1},
            {'known': 'kept', 'unknown-second': 2},
        ],
    }
    diagnostics = []
    jsonld.expand(input, {'diagnostics': diagnostics})
    pointers = [d['pointer'] for d in diagnostics]
    assert pointers == ['/items/0/unknown-first', '/items/1/unknown-second']
    assert resolve_pointer(input, pointers[0]) == 1
    assert resolve_pointer(input, pointers[1]) == 2


def test_diagnostics_pointer_through_nest():
    """
    Pointers locate fields dropped inside @nest values, including @nest
    arrays, without rewriting the path to expanded keywords.
    """
    input = {
        '@context': {'ex': 'http://example.com/', 'nest': '@nest'},
        'nest': [{'unknown-a': 1}, {'unknown-b': 2}],
    }
    diagnostics = []
    jsonld.expand(input, {'diagnostics': diagnostics})
    pointers = [d['pointer'] for d in diagnostics]
    assert pointers == ['/nest/0/unknown-a', '/nest/1/unknown-b']
    for diagnostic in diagnostics:
        resolve_pointer(input, diagnostic['pointer'])


def test_diagnostics_pointer_through_index_map():
    """
    Pointers locate fields dropped inside @index maps using the original
    map keys, with escaping applied.
    """
    input = {
        '@context': {
            'ex': 'http://example.com/',
            'byid': {'@id': 'ex:byid', '@container': '@index'},
        },
        'byid': {'key/1': {'unknown': 'dropped'}},
    }
    diagnostics = []
    jsonld.expand(input, {'diagnostics': diagnostics})
    assert diagnostics[0]['pointer'] == '/byid/key~11/unknown'
    assert resolve_pointer(input, diagnostics[0]['pointer']) == 'dropped'


def test_diagnostics_type_map_adds_type_scoped_source():
    """
    Fields dropped inside a @type map record the type-scoped context
    layer of the map key.
    """
    input = {
        '@context': {
            'ex': 'http://example.com/',
            'bytype': {'@id': 'ex:bytype', '@container': '@type'},
            'T': {'@id': 'ex:T', '@context': {'known': 'ex:known'}},
        },
        'bytype': {'T': {'known': 'kept', 'unknown': 'dropped'}},
    }
    diagnostics = []
    jsonld.expand(input, {'diagnostics': diagnostics})
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic['pointer'] == '/bytype/T/unknown'
    assert source_kinds(diagnostic) == ['initial', 'local', 'type-scoped']
    assert diagnostic['contextSource'][-1] == {'kind': 'type-scoped', 'type': 'T'}


def test_diagnostics_type_scoped_context_distinguishes_same_key():
    """
    The same key defined in one type-scoped context but not in the
    surrounding context is kept in the former and reported in the
    latter, with the type-scoped layer identifying the difference.
    """
    input = {
        '@context': {
            'ex': 'http://example.com/',
            'Thing': {'@id': 'ex:Thing', '@context': {'label': 'ex:label'}},
            'thing': 'ex:thing',
            'other': 'ex:other',
        },
        'thing': {'@type': 'Thing', 'label': 'kept'},
        'other': {'label': 'dropped'},
    }
    diagnostics = []
    expanded = jsonld.expand(input, {'diagnostics': diagnostics})
    # the scoped label expanded; only the unscoped one is reported
    assert expanded[0]['http://example.com/thing'] == [
        {
            '@type': ['http://example.com/Thing'],
            'http://example.com/label': [{'@value': 'kept'}],
        }
    ]
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic['pointer'] == '/other/label'
    assert 'type-scoped' not in source_kinds(diagnostic)


def test_diagnostics_property_scoped_context_source():
    """
    A field dropped under a property-scoped context records the term
    that introduced the scoped context, both as the property-scoped
    layer applied to the node and as the term-scoped layer applied to
    its value.
    """
    input = {
        '@context': {
            'ex': 'http://example.com/',
            'nested': {
                '@id': 'ex:nested',
                '@context': {'inner': 'ex:inner'},
            },
        },
        'nested': {'inner': 'kept', 'unknown': 'dropped'},
    }
    diagnostics = []
    jsonld.expand(input, {'diagnostics': diagnostics})
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic['pointer'] == '/nested/unknown'
    assert source_kinds(diagnostic) == [
        'initial',
        'local',
        'term-scoped',
        'property-scoped',
    ]
    assert diagnostic['contextSource'][-2] == {
        'kind': 'term-scoped',
        'term': 'nested',
    }
    assert diagnostic['contextSource'][-1] == {
        'kind': 'property-scoped',
        'term': 'nested',
    }


def test_diagnostics_term_scoped_context_source():
    """
    A field dropped under a term-scoped context records the term that
    introduced the scoped context.
    """
    input = {
        '@context': {
            'ex': 'http://example.com/',
            'nest': {'@id': '@nest', '@context': {'inner': 'ex:inner'}},
        },
        'nest': {'inner': 'kept', 'unknown': 'dropped'},
    }
    diagnostics = []
    jsonld.expand(input, {'diagnostics': diagnostics})
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic['pointer'] == '/nest/unknown'
    assert diagnostic['contextSource'][-1] == {'kind': 'term-scoped', 'term': 'nest'}


def test_diagnostics_local_context_source_pointer():
    """
    An inline @context records a local layer pointing at the @context
    member in the source document.
    """
    input = {
        '@context': {'ex': 'http://example.com/', 'node': 'ex:node'},
        'node': {
            '@context': {'inner': 'ex:inner'},
            'unknown': 'dropped',
        },
    }
    diagnostics = []
    jsonld.expand(input, {'diagnostics': diagnostics})
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic['pointer'] == '/node/unknown'
    local_layers = [
        source for source in diagnostic['contextSource'] if source['kind'] == 'local'
    ]
    assert local_layers[-1]['pointer'] == '/node/@context'


def test_diagnostics_expand_context_source():
    """
    The expandContext option is recorded as a context layer.
    """
    diagnostics = []
    jsonld.expand(
        {'unknown': 'dropped'},
        {
            'diagnostics': diagnostics,
            'expandContext': {'ex': 'http://example.com/'},
        },
    )
    assert source_kinds(diagnostics[0]) == ['initial', 'expandContext']


def test_diagnostics_remote_context_via_document_loader():
    """
    Remote contexts are loaded only through the configured DocumentLoader
    and recorded as remote layers with their resolved URL.
    """
    loaded = []

    class FakeDocumentLoader(DocumentLoader):
        def __call__(self, url, options=None):
            loaded.append(url)
            return {
                'contentType': 'application/ld+json',
                'contextUrl': None,
                'documentUrl': url,
                'document': {
                    '@context': {
                        'ex': 'http://example.com/',
                        'name': 'ex:name',
                    }
                },
            }

    input = {
        '@context': 'http://example.com/contexts/root.jsonld',
        'name': 'kept',
        'unknown': 'dropped',
    }
    diagnostics = []
    expanded = jsonld.expand(
        input,
        {
            'diagnostics': diagnostics,
            'documentLoader': FakeDocumentLoader(),
        },
    )
    assert loaded == ['http://example.com/contexts/root.jsonld']
    assert expanded == [{'http://example.com/name': [{'@value': 'kept'}]}]
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic['pointer'] == '/unknown'
    assert diagnostic['contextSource'][-1] == {
        'kind': 'remote',
        'url': 'http://example.com/contexts/root.jsonld',
    }


def test_diagnostics_language_map_null_values():
    """
    Null entries in language maps are reported with the language key and
    array index where present.
    """
    input = {
        '@context': {
            'ex': 'http://example.com/',
            'label': {'@id': 'ex:label', '@container': '@language'},
        },
        'label': {'en': None, 'fr': ['kept', None]},
    }
    diagnostics = []
    jsonld.expand(input, {'diagnostics': diagnostics})
    by_pointer = {d['pointer']: d for d in diagnostics}
    assert set(by_pointer) == {'/label/en', '/label/fr/1'}
    assert all(d['reason'] == 'null value' for d in diagnostics)
    assert resolve_pointer(input, '/label/fr/1') is None


def test_diagnostics_valid_fields_are_not_reported():
    """
    A document mixing valid and dropped fields reports only the dropped
    ones, and every pointer resolves into the source document.
    """
    input = {
        '@context': {
            'ex': 'http://example.com/',
            'name': 'ex:name',
            'items': {'@id': 'ex:items', '@container': '@list'},
            'nest': '@nest',
        },
        '@id': 'ex:root',
        'name': 'kept',
        'unknown~key': 'dropped',
        'items': ['kept', {'also/unknown': 'dropped'}],
        'nest': {'name': 'nested-kept', 'nested-unknown': None},
    }
    diagnostics = []
    expanded = jsonld.expand(input, {'diagnostics': diagnostics})
    # valid fields all made it into the expansion
    assert expanded == [
        {
            '@id': 'http://example.com/root',
            'http://example.com/name': [
                {'@value': 'kept'},
                {'@value': 'nested-kept'},
            ],
            'http://example.com/items': [
                {'@list': [{'@value': 'kept'}, {}]}
            ],
        }
    ]
    pointers = {d['pointer'] for d in diagnostics}
    assert pointers == {
        '/unknown~0key',
        '/items/1/also~1unknown',
        '/nest/nested-unknown',
    }
    for diagnostic in diagnostics:
        resolve_pointer(input, diagnostic['pointer'])
