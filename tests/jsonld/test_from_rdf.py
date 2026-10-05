import pytest

import pyld.jsonld as jsonld


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
            'http://www.w3.org/1999/02/22-rdf-syntax-ns#direction': [
                {'@value': 'rtl'}
            ],
            'http://www.w3.org/1999/02/22-rdf-syntax-ns#value': [
                {'@value': 'shared'}
            ],
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


RDF = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'


def test_list_diagnostics_valid_chain_collapses():
    """
    A well-formed chain collapses and the diagnostic names the folded
    nodes and their graph.
    """
    input = f"""
    <http://example.com/s> <http://example.com/p> _:b1 .
    _:b1 <{RDF}first> "a" .
    _:b1 <{RDF}rest> _:b2 .
    _:b2 <{RDF}first> "b" .
    _:b2 <{RDF}rest> <{RDF}nil> .
    """

    diagnostics = []
    result = jsonld.from_rdf(input, {'listDiagnostics': diagnostics})

    assert result == [
        {
            '@id': 'http://example.com/s',
            'http://example.com/p': [
                {'@list': [{'@value': 'a'}, {'@value': 'b'}]}
            ],
        }
    ]
    assert diagnostics == [
        {
            'graph': '@default',
            'collapsed': True,
            'nodes': ['_:b1', '_:b2'],
            'folded': ['_:b1', '_:b2'],
            'reason': None,
            'message': (
                "folded 2 list node(s) (_:b1, _:b2) in graph "
                "'@default' into @list"
            ),
        }
    ]


def test_list_diagnostics_multiple_first():
    """
    A node with two rdf:first values stays a regular node and reports
    the multiple-first obstacle.
    """
    input = f"""
    <http://example.com/s> <http://example.com/p> _:b1 .
    _:b1 <{RDF}first> "a" .
    _:b1 <{RDF}first> "b" .
    _:b1 <{RDF}rest> <{RDF}nil> .
    """

    diagnostics = []
    result = jsonld.from_rdf(input, {'listDiagnostics': diagnostics})

    node = next(n for n in result if n['@id'] == '_:b1')
    assert sorted(v['@value'] for v in node[f'{RDF}first']) == ['a', 'b']
    assert len(diagnostics) == 1
    entry = diagnostics[0]
    assert entry['collapsed'] is False
    assert entry['reason'] == 'multiple-first'
    assert entry['node'] == '_:b1'
    assert entry['property'] == f'{RDF}first'
    assert entry['graph'] == '@default'
    assert '_:b1' in entry['message']


def test_list_diagnostics_multiple_rest():
    """
    A node with two rdf:rest values stays a regular node and reports
    the multiple-rest obstacle.
    """
    input = f"""
    <http://example.com/s> <http://example.com/p> _:b1 .
    _:b1 <{RDF}first> "a" .
    _:b1 <{RDF}rest> _:b2 .
    _:b2 <{RDF}first> "x" .
    _:b2 <{RDF}rest> _:b3 .
    _:b2 <{RDF}rest> _:b4 .
    _:b3 <{RDF}first> "y" .
    _:b3 <{RDF}rest> <{RDF}nil> .
    """

    diagnostics = []
    result = jsonld.from_rdf(input, {'listDiagnostics': diagnostics})

    node = next(n for n in result if n['@id'] == '_:b2')
    assert node[f'{RDF}first'] == [{'@value': 'x'}]
    assert len(node[f'{RDF}rest']) == 2
    assert len(diagnostics) == 1
    entry = diagnostics[0]
    assert entry['collapsed'] is False
    assert entry['reason'] == 'multiple-rest'
    assert entry['node'] == '_:b2'
    assert entry['property'] == f'{RDF}rest'


def test_list_diagnostics_missing_first_gap():
    """
    A chain node without rdf:first is a gap; the well-formed tail still
    folds into the gap node's rdf:rest value.
    """
    input = f"""
    <http://example.com/s> <http://example.com/p> _:b1 .
    _:b1 <{RDF}rest> _:b2 .
    _:b2 <{RDF}first> "b" .
    _:b2 <{RDF}rest> <{RDF}nil> .
    """

    diagnostics = []
    result = jsonld.from_rdf(input, {'listDiagnostics': diagnostics})

    node = next(n for n in result if n['@id'] == '_:b1')
    assert node[f'{RDF}rest'] == [{'@list': [{'@value': 'b'}]}]
    assert len(diagnostics) == 1
    entry = diagnostics[0]
    assert entry['collapsed'] is False
    assert entry['reason'] == 'missing-first'
    assert entry['node'] == '_:b1'
    assert entry['folded'] == ['_:b2']


def test_list_diagnostics_shared_tail():
    """
    A tail shared by two chains is not folded; the diagnostic reports
    the shared node.
    """
    input = f"""
    <http://example.com/s1> <http://example.com/p> _:h1 .
    _:h1 <{RDF}first> "a" .
    _:h1 <{RDF}rest> _:t .
    <http://example.com/s2> <http://example.com/p> _:h2 .
    _:h2 <{RDF}first> "b" .
    _:h2 <{RDF}rest> _:t .
    _:t <{RDF}first> "shared" .
    _:t <{RDF}rest> <{RDF}nil> .
    """

    diagnostics = []
    result = jsonld.from_rdf(input, {'listDiagnostics': diagnostics})

    tail = next(n for n in result if n['@id'] == '_:t')
    assert tail[f'{RDF}first'] == [{'@value': 'shared'}]
    assert len(diagnostics) == 1
    entry = diagnostics[0]
    assert entry['collapsed'] is False
    assert entry['reason'] == 'shared'
    assert entry['node'] == '_:t'
    assert entry['graph'] == '@default'


def test_list_diagnostics_extra_properties():
    """
    A node with properties beyond rdf:first/rdf:rest stays a regular
    node and reports the extra-properties obstacle.
    """
    input = f"""
    <http://example.com/s> <http://example.com/p> _:b1 .
    _:b1 <{RDF}first> "a" .
    _:b1 <{RDF}rest> <{RDF}nil> .
    _:b1 <http://example.com/extra> "e" .
    """

    diagnostics = []
    result = jsonld.from_rdf(input, {'listDiagnostics': diagnostics})

    node = next(n for n in result if n['@id'] == '_:b1')
    assert node['http://example.com/extra'] == [{'@value': 'e'}]
    assert len(diagnostics) == 1
    entry = diagnostics[0]
    assert entry['collapsed'] is False
    assert entry['reason'] == 'extra-properties'
    assert entry['node'] == '_:b1'
    assert entry['property'] == 'http://example.com/extra'
    assert 'http://example.com/extra' in entry['message']


def test_list_diagnostics_cycle():
    """
    A detached rdf:rest cycle has no rdf:nil terminator; it is reported
    as a cycle and left as regular nodes.
    """
    input = f"""
    _:c1 <{RDF}first> "1" .
    _:c1 <{RDF}rest> _:c2 .
    _:c2 <{RDF}first> "2" .
    _:c2 <{RDF}rest> _:c1 .
    """

    diagnostics = []
    result = jsonld.from_rdf(input, {'listDiagnostics': diagnostics})

    assert len(result) == 2
    assert len(diagnostics) == 1
    entry = diagnostics[0]
    assert entry['collapsed'] is False
    assert entry['reason'] == 'cycle'
    assert sorted(entry['nodes']) == ['_:c1', '_:c2']
    assert entry['property'] == f'{RDF}rest'
    assert '_:c1' in entry['message'] and '_:c2' in entry['message']


def test_list_diagnostics_cross_graph_reference():
    """
    A chain whose structure spans named graphs is not folded and
    reports the cross-graph reference without failing the conversion.
    """
    input = f"""
    _:a <{RDF}rest> _:b <http://example.com/g1> .
    _:b <{RDF}first> "x" <http://example.com/g2> .
    _:b <{RDF}rest> <{RDF}nil> <http://example.com/g2> .
    """

    diagnostics = []
    result = jsonld.from_rdf(input, {'listDiagnostics': diagnostics})

    graph2 = next(n for n in result if n['@id'] == 'http://example.com/g2')
    node = next(n for n in graph2['@graph'] if n['@id'] == '_:b')
    assert node[f'{RDF}first'] == [{'@value': 'x'}]
    assert len(diagnostics) == 1
    entry = diagnostics[0]
    assert entry['collapsed'] is False
    assert entry['reason'] == 'cross-graph-reference'
    assert entry['graph'] == 'http://example.com/g2'
    assert entry['node'] == '_:a'
    assert 'http://example.com/g2' in entry['message']


def test_list_diagnostics_independent_chains_not_blocked():
    """
    An invalid chain connected to the same subject does not stop an
    independent valid chain from collapsing.
    """
    input = f"""
    <http://example.com/s> <http://example.com/good> _:g1 .
    _:g1 <{RDF}first> "a" .
    _:g1 <{RDF}rest> _:g2 .
    _:g2 <{RDF}first> "b" .
    _:g2 <{RDF}rest> <{RDF}nil> .
    <http://example.com/s> <http://example.com/bad> _:b1 .
    _:b1 <{RDF}first> "x" .
    _:b1 <{RDF}rest> _:b2 .
    _:b2 <{RDF}first> "y" .
    _:b2 <{RDF}rest> <{RDF}nil> .
    _:b2 <http://example.com/extra> "e" .
    """

    diagnostics = []
    result = jsonld.from_rdf(input, {'listDiagnostics': diagnostics})

    subject = next(n for n in result if n['@id'] == 'http://example.com/s')
    assert subject['http://example.com/good'] == [
        {'@list': [{'@value': 'a'}, {'@value': 'b'}]}
    ]
    assert subject['http://example.com/bad'] == [{'@id': '_:b1'}]
    by_reason = {entry['reason'] for entry in diagnostics}
    assert by_reason == {None, 'extra-properties'}
    collapsed = next(e for e in diagnostics if e['collapsed'])
    assert collapsed['nodes'] == ['_:g1', '_:g2']


def test_list_diagnostics_round_trip_recovers_shared_and_extra_facts():
    """
    Converting the diagnostics output back to RDF recovers the facts
    kept as regular nodes because of sharing and extra properties.
    """
    input = f"""
    <http://example.com/s1> <http://example.com/p> _:h1 .
    _:h1 <{RDF}first> "a" .
    _:h1 <{RDF}rest> _:t .
    <http://example.com/s2> <http://example.com/p> _:h2 .
    _:h2 <{RDF}first> "b" .
    _:h2 <{RDF}rest> _:t .
    _:t <{RDF}first> "shared" .
    _:t <{RDF}rest> <{RDF}nil> .
    _:t <http://example.com/extra> "e" .
    """

    diagnostics = []
    result = jsonld.from_rdf(input, {'listDiagnostics': diagnostics})
    dataset = jsonld.to_rdf(result)

    quads = list(dataset.quads((None, None, None, None)))
    triples = {(str(s), str(p), str(o)) for s, p, o, _ in quads}

    # the extra property fact survives the round trip
    assert any(p == 'http://example.com/extra' and o == 'e'
               for _, p, o in triples)

    # the shared tail is still shared: exactly one node has the
    # 'shared' first value and two rest references point at it
    shared_first = [s for s, p, o in triples
                    if p == f'{RDF}first' and o == 'shared']
    assert len(shared_first) == 1
    shared_rest = [s for s, p, o in triples
                   if p == f'{RDF}rest' and o == shared_first[0]]
    assert len(shared_rest) == 2

    # no fact was lost: every input triple round-trips
    assert len(quads) == 9
