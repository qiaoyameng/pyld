import warnings

import pytest
from rdflib import ConjunctiveGraph

import pyld.jsonld as jsonld

RDF = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
RDF_FIRST = f'{RDF}first'
RDF_REST = f'{RDF}rest'
RDF_NIL = f'{RDF}nil'


def _diagnostics(input, **options):
    result = jsonld.from_rdf(input, {'listDiagnostics': True, **options})
    assert set(result) == {'output', 'listDiagnostics'}
    return result


def _isomorphic(input, output):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', DeprecationWarning)
        original = ConjunctiveGraph()
        original.parse(data=input, format='nquads')
        roundtrip = ConjunctiveGraph()
        serialized = jsonld.to_rdf(output, {'format': 'application/n-quads'})
        roundtrip.parse(data=serialized, format='nquads')
        return original.isomorphic(roundtrip)


def _by_head(diagnostics):
    return {entry['head']: entry for entry in diagnostics}


def test_list_diagnostics_valid_chain_folded():
    """
    A well-formed rdf:List chain is reported as folded with an empty
    obstacle list and references the original input nodes.
    """
    input = f"""
    <http://example.com/a> <http://example.org/p> _:l0 .
    _:l0 <{RDF_FIRST}> "a" .
    _:l0 <{RDF_REST}> _:l1 .
    _:l1 <{RDF_FIRST}> "b" .
    _:l1 <{RDF_REST}> <{RDF_NIL}> .
    """

    result = _diagnostics(input)

    assert result['output'] == [
        {
            '@id': 'http://example.com/a',
            'http://example.org/p': [{'@list': [{'@value': 'a'}, {'@value': 'b'}]}],
        }
    ]
    assert len(result['listDiagnostics']) == 1
    entry = result['listDiagnostics'][0]
    assert entry['graph'] == '@default'
    assert entry['head'] == '_:l0'
    assert entry['folded'] is True
    assert entry['nilTerminated'] is True
    assert entry['nodes'] == ['_:l0', '_:l1']
    assert entry['foldedNodes'] == ['_:l0', '_:l1']
    assert entry['retainedNodes'] == []
    assert entry['obstacles'] == []


def test_list_diagnostics_disabled_returns_plain_output():
    """Without the option, from_rdf keeps its plain-array return value."""
    input = f"""
    <http://example.com/a> <http://example.org/p> _:l0 .
    _:l0 <{RDF_FIRST}> "a" .
    _:l0 <{RDF_REST}> <{RDF_NIL}> .
    """

    assert isinstance(jsonld.from_rdf(input), list)
    assert isinstance(jsonld.from_rdf(input, {'listDiagnostics': False}), list)


def test_list_diagnostics_multiple_first_and_rest():
    """Chains with repeated rdf:first/rdf:first values are not folded."""
    input = f"""
    <http://example.com/s> <http://example.org/p> _:m0 .
    _:m0 <{RDF_FIRST}> "a" .
    _:m0 <{RDF_FIRST}> "b" .
    _:m0 <{RDF_REST}> <{RDF_NIL}> .
    <http://example.com/t> <http://example.org/p> _:n0 .
    _:n0 <{RDF_FIRST}> "c" .
    _:n0 <{RDF_REST}> <{RDF_NIL}> .
    _:n0 <{RDF_REST}> _:n1 .
    _:n1 <{RDF_FIRST}> "d" .
    _:n1 <{RDF_REST}> <{RDF_NIL}> .
    """

    result = _diagnostics(input)
    entries = _by_head(result['listDiagnostics'])

    assert entries['_:m0']['folded'] is False
    codes = [obstacle['code'] for obstacle in entries['_:m0']['obstacles']]
    assert codes == ['multipleFirst']
    obstacle = entries['_:m0']['obstacles'][0]
    assert obstacle['graph'] == '@default'
    assert obstacle['node'] == '_:m0'
    assert obstacle['details']['count'] == 2

    assert entries['_:n0']['folded'] is False
    codes = [obstacle['code'] for obstacle in entries['_:n0']['obstacles']]
    assert codes == ['multipleRest']
    assert entries['_:n0']['obstacles'][0]['details']['count'] == 2


def test_list_diagnostics_gap_and_cycle():
    """
    Chains that never reach rdf:nil because of a gap or a cycle stay as
    ordinary nodes with a located obstacle.
    """
    input = f"""
    <http://example.com/s> <http://example.org/p> _:q0 .
    _:q0 <{RDF_FIRST}> "a" .
    _:q0 <{RDF_REST}> <http://example.com/plain> .
    <http://example.com/t> <http://example.org/p> _:c0 .
    _:c0 <{RDF_FIRST}> "b" .
    _:c0 <{RDF_REST}> _:c1 .
    _:c1 <{RDF_FIRST}> "c" .
    _:c1 <{RDF_REST}> _:c0 .
    """

    result = _diagnostics(input)
    entries = _by_head(result['listDiagnostics'])

    gap = entries['_:q0']
    assert gap['folded'] is False
    assert gap['nilTerminated'] is False
    assert gap['obstacles'][0]['code'] == 'gap'
    assert gap['obstacles'][0]['node'] == 'http://example.com/plain'
    assert gap['obstacles'][0]['graph'] == '@default'

    cycle = entries['_:c0']
    assert cycle['folded'] is False
    assert cycle['nilTerminated'] is False
    codes = [obstacle['code'] for obstacle in cycle['obstacles']]
    assert 'cycle' in codes
    cycle_obstacle = next(
        obstacle for obstacle in cycle['obstacles'] if obstacle['code'] == 'cycle'
    )
    assert cycle_obstacle['node'] == '_:c0'
    assert cycle_obstacle['details']['source'] == '_:c1'


def test_list_diagnostics_shared_tail_does_not_block_independent_chain():
    """
    Two lists sharing a suffix are both retained, while a separate
    well-formed list in the same graph is still folded.
    """
    input = f"""
    <http://example.com/s4> <http://example.org/p> _:t0 .
    <http://example.com/s5> <http://example.org/p> _:t1 .
    _:t0 <{RDF_FIRST}> "a" .
    _:t0 <{RDF_REST}> _:t2 .
    _:t1 <{RDF_FIRST}> "b" .
    _:t1 <{RDF_REST}> _:t2 .
    _:t2 <{RDF_FIRST}> "c" .
    _:t2 <{RDF_REST}> <{RDF_NIL}> .
    <http://example.com/s6> <http://example.org/p> _:g0 .
    _:g0 <{RDF_FIRST}> "z" .
    _:g0 <{RDF_REST}> <{RDF_NIL}> .
    """

    result = _diagnostics(input)
    entries = _by_head(result['listDiagnostics'])

    assert entries['_:t0']['folded'] is False
    assert entries['_:t1']['folded'] is False
    heads = [entry['head'] for entry in result['listDiagnostics']]
    assert '_:t2' not in heads
    for head in ('_:t0', '_:t1'):
        obstacle = next(
            obstacle
            for obstacle in entries[head]['obstacles']
            if obstacle['code'] == 'sharedNode'
        )
        assert obstacle['node'] == '_:t2'
        assert obstacle['graph'] == '@default'

    # the independent good chain folds despite the broken neighboring chains
    assert entries['_:g0']['folded'] is True
    assert entries['_:g0']['obstacles'] == []


def test_list_diagnostics_extra_property_preserved_through_roundtrip():
    """
    A list node carrying an extra property is retained as a normal node,
    and converting the output back to RDF keeps every fact.
    """
    input = f"""
    <http://example.com/b> <http://example.org/bad> _:b0 .
    _:b0 <{RDF_FIRST}> "x" .
    _:b0 <{RDF_REST}> <{RDF_NIL}> .
    _:b0 <http://example.org/extra> "e" .
    """

    result = _diagnostics(input)
    entries = _by_head(result['listDiagnostics'])

    assert entries['_:b0']['folded'] is False
    obstacle = entries['_:b0']['obstacles'][0]
    assert obstacle['code'] == 'extraProperty'
    assert obstacle['details']['properties'] == ['http://example.org/extra']

    assert _isomorphic(input, result['output'])


def test_list_diagnostics_invalid_list_type():
    """An rdf:List node typed otherwise is not folded."""
    input = f"""
    <http://example.com/s> <http://example.org/p> _:i0 .
    _:i0 <{RDF_FIRST}> "a" .
    _:i0 <{RDF_REST}> <{RDF_NIL}> .
    _:i0 <{RDF}type> <http://example.com/Other> .
    """

    result = _diagnostics(input)
    entry = result['listDiagnostics'][0]

    assert entry['folded'] is False
    obstacle = entry['obstacles'][0]
    assert obstacle['code'] == 'invalidListType'
    assert obstacle['node'] == '_:i0'
    assert obstacle['details']['types'] == ['http://example.com/Other']


def test_list_diagnostics_cross_named_graph_reference():
    """
    A chain split across named graphs is not folded and the obstacle
    identifies both graph names; conversion still succeeds.
    """
    input = f"""
    <http://example.com/s> <http://example.org/p> _:x0 <http://example.org/G> .
    _:x0 <{RDF_FIRST}> "a" <http://example.org/G> .
    _:x0 <{RDF_REST}> _:x1 <http://example.org/G> .
    _:x1 <{RDF_FIRST}> "b" .
    _:x1 <{RDF_REST}> <{RDF_NIL}> .
    """

    result = _diagnostics(input)
    entries = {
        (entry['graph'], entry['head']): entry for entry in result['listDiagnostics']
    }

    named = entries[('http://example.org/G', '_:x0')]
    assert named['folded'] is False
    edge = next(
        obstacle
        for obstacle in named['obstacles']
        if obstacle['code'] == 'crossGraphReference'
    )
    assert edge['node'] == '_:x1'
    assert edge['graph'] == 'http://example.org/G'
    assert edge['details']['targetGraph'] == '@default'

    default = entries[('@default', '_:x1')]
    assert default['folded'] is False
    incoming = next(
        obstacle
        for obstacle in default['obstacles']
        if obstacle['code'] == 'crossGraphReference'
    )
    assert incoming['details']['references'] == [
        {
            'graph': 'http://example.org/G',
            'node': '_:x0',
            'property': RDF_REST,
        }
    ]


def test_list_diagnostics_malformed_chain_never_raises():
    """
    A nil usage that reaches a node defined in another graph must not
    crash the conversion; diagnostics still describe the chain.
    """
    input = f"""
    <http://example.com/s> <http://example.org/p> _:x0 <http://example.org/G> .
    _:x0 <{RDF_REST}> <{RDF_NIL}> <http://example.org/G> .
    _:x0 <{RDF_FIRST}> "a" .
    _:x0 <{RDF_REST}> _:x1 .
    _:x1 <{RDF_FIRST}> "b" .
    _:x1 <{RDF_REST}> <{RDF_NIL}> .
    """

    result = _diagnostics(input)

    assert isinstance(result['output'], list)
    assert result['listDiagnostics']


def test_list_diagnostics_shared_tail_roundtrip_is_lossless():
    """
    Facts kept because of a shared tail survive a full RDF roundtrip.
    """
    input = f"""
    <http://example.com/s4> <http://example.org/p> _:t0 .
    <http://example.com/s5> <http://example.org/p> _:t1 .
    _:t0 <{RDF_FIRST}> "a" .
    _:t0 <{RDF_REST}> _:t2 .
    _:t1 <{RDF_FIRST}> "b" .
    _:t1 <{RDF_REST}> _:t2 .
    _:t2 <{RDF_FIRST}> "c" .
    _:t2 <{RDF_REST}> <{RDF_NIL}> .
    """

    result = _diagnostics(input)

    assert _isomorphic(input, result['output'])


def test_compound_literal_direction_without_language():
    """
    Compound literals with rdf:direction should become JSON-LD value
    objects when rdfDirection is compound-literal.
    """
    input = """
    <http://example.com/a> <http://example.org/label> _:cl1 .
    _:cl1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#value> "no language" .
    _:cl1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#direction> "rtl" .
    """

    expected = [
        {
            '@id': 'http://example.com/a',
            'http://example.org/label': [
                {'@value': 'no language', '@direction': 'rtl'}
            ],
        }
    ]

    result = jsonld.from_rdf(input, {'rdfDirection': 'compound-literal'})

    assert result == expected


def test_compound_literal_direction_with_language():
    """
    Compound literals with rdf:language should preserve the language
    when rdfDirection is compound-literal.
    """
    input = """
    <http://example.com/a> <http://example.org/label> _:cl1 .
    _:cl1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#value> "en-US" .
    _:cl1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#language> "en-us" .
    _:cl1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#direction> "rtl" .
    """

    expected = [
        {
            '@id': 'http://example.com/a',
            'http://example.org/label': [
                {
                    '@value': 'en-US',
                    '@language': 'en-us',
                    '@direction': 'rtl',
                }
            ],
        }
    ]

    result = jsonld.from_rdf(input, {'rdfDirection': 'compound-literal'})

    assert result == expected


def test_shared_compound_literal_blank_node_remains_node():
    """
    Compound literal blank nodes must only be decoded once when referenced.
    """
    input = """
    <http://example.com/a> <http://example.org/label> _:cl1 .
    <http://example.com/b> <http://example.org/label> _:cl1 .
    _:cl1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#value> "shared" .
    _:cl1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#direction> "rtl" .
    """

    expected = [
        {
            '@id': '_:cl1',
            'http://www.w3.org/1999/02/22-rdf-syntax-ns#direction': [{'@value': 'rtl'}],
            'http://www.w3.org/1999/02/22-rdf-syntax-ns#value': [{'@value': 'shared'}],
        },
        {
            '@id': 'http://example.com/a',
            'http://example.org/label': [{'@id': '_:cl1'}],
        },
        {
            '@id': 'http://example.com/b',
            'http://example.org/label': [{'@id': '_:cl1'}],
        },
    ]

    result = jsonld.from_rdf(input, {'rdfDirection': 'compound-literal'})

    assert result == expected


def test_compound_literal_invalid_direction_fails():
    """
    Invalid rdf:direction values in compound literals must fail.
    """
    input = """
    <http://example.com/a> <http://example.org/label> _:cl1 .
    _:cl1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#value> "bad" .
    _:cl1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#direction> "up" .
    """

    with pytest.raises(jsonld.JsonLdError) as exc:
        jsonld.from_rdf(input, {'rdfDirection': 'compound-literal'})

    assert exc.value.code == 'invalid base direction'


def test_compound_literal_invalid_value_fails():
    """
    Invalid rdf:value entries in compound literals must fail.
    """
    input = """
    <http://example.com/a> <http://example.org/label> _:cl1 .
    _:cl1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#value> "one" .
    _:cl1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#value> "two" .
    _:cl1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#direction> "rtl" .
    """

    with pytest.raises(jsonld.JsonLdError) as exc:
        jsonld.from_rdf(input, {'rdfDirection': 'compound-literal'})

    assert exc.value.code == 'invalid value object'


def test_compound_literal_invalid_language_fails():
    """
    Invalid rdf:language values in compound literals must fail.
    """
    input = """
    <http://example.com/a> <http://example.org/label> _:cl1 .
    _:cl1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#value> "bad lang" .
    _:cl1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#language> "bad_lang" .
    _:cl1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#direction> "rtl" .
    """

    with pytest.raises(jsonld.JsonLdError) as exc:
        jsonld.from_rdf(input, {'rdfDirection': 'compound-literal'})

    assert exc.value.code == 'invalid language-tagged string'
