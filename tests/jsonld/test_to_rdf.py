from rdflib import RDF, XSD, Dataset, Literal, URIRef

import pyld.jsonld as jsonld
from pyld.identifier_issuer import IdentifierIssuer

# PR: https://github.com/digitalbazaar/pyld/pull/202

def test_double_and_float_values():
    """
    String values with @type: "xsd:double" should be converted to float value during to_rdf.
    """
    input = {
        "@context": {"xsd": "http://www.w3.org/2001/XMLSchema#"},
        "@graph": [
            {"@id": "ex:1", "ex:p": {"@type": "xsd:double", "@value": "45"}}
        ],
    }

    expected = """<ex:1> <ex:p> "4.5E1"^^<http://www.w3.org/2001/XMLSchema#double>  .

"""
    nquads = jsonld.to_rdf(input, {"format": "application/n-quads"})
    assert nquads == expected

def test_legacy_mode():
    """
    legacyMode should return the PyLD 3.x RDF.js-like dataset dict.
    """
    input = {
        "@context": {"xsd": "http://www.w3.org/2001/XMLSchema#"},
        "@graph": [
            {"@id": "ex:1", "ex:p": {"@type": "xsd:double", "@value": "45"}}
        ],
    }
    expected = {
        "@default": [
            {
                "subject": {"type": "IRI", "value": "ex:1"},
                "predicate": {"type": "IRI", "value": "ex:p"},
                "object": {
                    "type": "literal",
                    "value": "4.5E1",
                    "datatype": "http://www.w3.org/2001/XMLSchema#double",
                },
            }
        ]
    }

    assert isinstance(jsonld.to_rdf(input), Dataset)
    assert jsonld.to_rdf(input, {"legacyMode": True}) == expected

def test_format_takes_precedence_over_legacy_mode():
    """
    N-Quads format output should still be returned when legacyMode is true.
    """
    input = {
        "@context": {"xsd": "http://www.w3.org/2001/XMLSchema#"},
        "@graph": [
            {"@id": "ex:1", "ex:p": {"@type": "xsd:double", "@value": "45"}}
        ],
    }

    expected = """<ex:1> <ex:p> "4.5E1"^^<http://www.w3.org/2001/XMLSchema#double>  .

"""
    nquads = jsonld.to_rdf(
        input,
        {"format": "application/n-quads", "legacyMode": True},
    )
    assert nquads == expected

def test_to_rdf_skips_relative_vocab_property_that_expands_to_invalid_iri():
    """
    to_rdf should omit property IRIs that expand to invalid RDF IRIs.
    """
    input = {
        "@context": [
            {
                "@version": 1.1,
                "@base": "http://example.com/some/deep/directory/and/file/",
                "@vocab": "http://example.com/vocabulary/",
            },
            {"@vocab": "./rel2#"},
        ],
        "@id": "relativePropertyIris",
        "link": "link",
        "#fragment-works": "#fragment-works",
    }

    nquads = jsonld.to_rdf(input, options={'format': 'application/n-quads'})

    assert (
        '<http://example.com/some/deep/directory/and/file/relativePropertyIris> '
        '<http://example.com/vocabulary/./rel2#link> '
        '"link"^^<http://www.w3.org/2001/XMLSchema#string>  .'
    ) in nquads
    assert '##fragment-works' not in nquads

def test_large_integer_to_rdf_double_conversion_processing_mode():
    """
    In json-ld-1.1 processing mode, large integers should be emitted as xsd:double,
    while in json-ld-1.0 processing mode, they should be kept as xsd:integer.
    """
    input = {
        '@id': 'http://example.com/s',
        'http://example.com/p': 1000000000000000000000,
    }

    nquads = jsonld.to_rdf(input, options={'format': 'application/n-quads'})
    expected = """<http://example.com/s> <http://example.com/p> "1.0E21"^^<http://www.w3.org/2001/XMLSchema#double>  .

"""
    assert nquads == expected

    nquads = jsonld.to_rdf(
        input,
        options={
            'format': 'application/n-quads',
            'processingMode': 'json-ld-1.0',
        },
    )
    expected = """<http://example.com/s> <http://example.com/p> "1000000000000000000000"^^<http://www.w3.org/2001/XMLSchema#integer>  .

"""
    assert nquads == expected

def test_to_rdf_uses_identifier_issuer_option():
    input = {'http://example.org/p': [{'@list': ['a', 'b']}]}
    issuer = IdentifierIssuer('_:custom')

    expected = """_:custom0 <http://example.org/p> _:custom1  .
_:custom1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#first> "a"^^<http://www.w3.org/2001/XMLSchema#string>  .
_:custom1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#rest> _:custom2  .
_:custom2 <http://www.w3.org/1999/02/22-rdf-syntax-ns#first> "b"^^<http://www.w3.org/2001/XMLSchema#string>  .
_:custom2 <http://www.w3.org/1999/02/22-rdf-syntax-ns#rest> <http://www.w3.org/1999/02/22-rdf-syntax-ns#nil>  .

"""

    nquads = jsonld.to_rdf(
        input,
        options={'format': 'application/n-quads', 'identifierIssuer': issuer},
    )

    assert sorted(nquads.splitlines()) == sorted(expected.splitlines())

def test_compound_literal_direction_without_language():
    """
    Values with @direction should become compound literals during to_rdf
    when rdfDirection is compound-literal.
    """
    input = {
        'http://example.org/label': {
            '@value': 'no language',
            '@direction': 'rtl',
        }
    }

    expected = """_:b0 <http://example.org/label> _:b1  .
_:b1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#direction> "rtl"^^<http://www.w3.org/2001/XMLSchema#string>  .
_:b1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#value> "no language"^^<http://www.w3.org/2001/XMLSchema#string>  .

"""

    nquads = jsonld.to_rdf(
        input,
        options={
            'format': 'application/n-quads',
            'rdfDirection': 'compound-literal',
        },
    )

    assert sorted(nquads.splitlines()) == sorted(expected.splitlines())

def test_compound_literal_direction_with_language():
    """
    Values with @language should preserve it in compound literals during
    to_rdf when rdfDirection is compound-literal.
    """
    input = {
        'http://example.org/label': {
            '@value': 'en-US',
            '@language': 'en-US',
            '@direction': 'rtl',
        }
    }

    expected = """_:b0 <http://example.org/label> _:b1  .
_:b1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#direction> "rtl"^^<http://www.w3.org/2001/XMLSchema#string>  .
_:b1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#language> "en-us"^^<http://www.w3.org/2001/XMLSchema#string>  .
_:b1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#value> "en-US"^^<http://www.w3.org/2001/XMLSchema#string>  .

"""

    nquads = jsonld.to_rdf(
        input,
        options={
            'format': 'application/n-quads',
            'rdfDirection': 'compound-literal',
        },
    )

    assert sorted(nquads.splitlines()) == sorted(expected.splitlines())

def test_invalid_language_tag_is_skipped():
    """
    Conversion to RDF should skip values with invalid language tags.
    """
    input = {
        '@id': 'http://example.com/foo',
        'http://example.com/bar': {
            '@value': 'bar',
            '@language': 'a b',
        },
    }

    nquads = jsonld.to_rdf(input, options={'format': 'application/n-quads'})
    assert nquads == '\n'

# Issue 204
def test_conflicting_property_names():
    """
    Conversion to RDF should allow a node in the root @context with
    a conflicting property name in its own @context
    """
    input = {
        "@context": {
            "dublinCore": {
                "@id": "http://foo.bar/dc",
                "@context": {"title": "http://purl.org/dc/terms/title"},
            },
            "title": "http://foo.bar/title",
        },
        "@id": "http://foo.bar/obj/test",
        "title": "test",
        "dublinCore": {"title": "Chapter 1: Jonathan Harker's Journal"},
    }

    expected = """<http://foo.bar/obj/test> <http://foo.bar/title> "test"^^<http://www.w3.org/2001/XMLSchema#string>  .
<http://foo.bar/obj/test> <http://foo.bar/dc> _:b0  .
_:b0 <http://purl.org/dc/terms/title> "Chapter 1: Jonathan Harker's Journal"^^<http://www.w3.org/2001/XMLSchema#string>  .

"""

    nquads = jsonld.to_rdf(input, options={'format': 'application/n-quads'})
    # TODO: move this into a helper function for comparing nquads
    assert sorted(nquads.splitlines()) == sorted(expected.splitlines())

def test_conflicting_property_names_in_nested_node():
    """
    Conversion to RDF should not ignore a @nest'ed node in the root @context
    a conflicting property name in its own @context
    """
    input = {
        "@context": {
            "dublinCore": {
                "@id": "@nest",
                "@context": {"title": "http://purl.org/dc/terms/title"},
            },
            "title": "http://foo.bar/title",
        },
        "@id": "http://foo.bar/obj/test",
        "title": "test",
        "dublinCore": {"title": "Chapter 1: Jonathan Harker's Journal"},
    }

    expected = """<http://foo.bar/obj/test> <http://foo.bar/title> "test"^^<http://www.w3.org/2001/XMLSchema#string>  .
<http://foo.bar/obj/test> <http://purl.org/dc/terms/title> "Chapter 1: Jonathan Harker's Journal"^^<http://www.w3.org/2001/XMLSchema#string>  .

"""

    nquads = jsonld.to_rdf(input, options={'format': 'application/n-quads'})
    # TODO: move this into a helper function for comparing nquads
    assert sorted(nquads.splitlines()) == sorted(expected.splitlines())

# Issue 177
def test_fractional():
    """
    Number with 0 fractional part should parse to an xsd:integer
    """
    input = { "ex:value": 42.0 }

    expected = """_:b0 <ex:value> "42"^^<http://www.w3.org/2001/XMLSchema#integer>  .

"""

    nquads = jsonld.to_rdf(input, options={'format': 'application/n-quads'})
    assert nquads == expected

# Issue 175
def test_truncate_zeros_with_negative_exponent_numbers():
    """
    Numeric values with negative exponent should truncate zeros
    """
    input = { "ex:value": 0.97 }

    expected = """_:b0 <ex:value> "9.7E-1"^^<http://www.w3.org/2001/XMLSchema#double>  .

"""

    nquads = jsonld.to_rdf(input, options={'format': 'application/n-quads'})
    assert nquads == expected

def test_list_skips_invalid_iri_items():
    """
    Conversion to RDF should skip invalid list item IRIs without dropping
    the list node.
    """
    input = {
        "@context": {
            "@base": "http://invalid/<>/",
            "list": {
                "@id": "foo:bar",
                "@container": "@list",
                "@type": "@id",
            },
        },
        "list": ["test"],
    }

    expected = """_:b0 <foo:bar> _:b1  .
_:b1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#rest> <http://www.w3.org/1999/02/22-rdf-syntax-ns#nil>  .

"""

    nquads = jsonld.to_rdf(input, options={'format': 'application/n-quads'})
    assert sorted(nquads.splitlines()) == sorted(expected.splitlines())

def test_source_map_merges_sources_from_multiple_positions():
    """
    A statement synthesized from two different input positions should map to
    the complete set of source pointers, not just the last one written.
    """
    input = {
        "@context": {"ex": "http://example.com/"},
        "@graph": [
            {"@id": "ex:s", "ex:p": {"@id": "ex:o"}},
            {"@id": "ex:s", "ex:p": [{"@id": "ex:o"}]},
        ],
    }

    dataset, source_map = jsonld.to_rdf(input, {"sourceMap": True})

    key = (
        URIRef("http://example.com/s"),
        URIRef("http://example.com/p"),
        URIRef("http://example.com/o"),
        None,
    )
    assert len(dataset) == 1
    assert source_map[key] == {"/@graph/0/ex:p", "/@graph/1/ex:p/0"}

def test_source_map_list_duplicate_objects():
    """
    Duplicate objects in a @list should each keep their own source pointer,
    and the structural first/rest statements should be attributed to the
    list container that generated them.
    """
    input = {
        "@context": {"ex": "http://example.com/"},
        "@id": "ex:s",
        "ex:p": {"@list": ["a", "a"]},
    }

    dataset, source_map = jsonld.to_rdf(input, {"sourceMap": True})

    firsts = [
        pointers
        for (s, p, o, g), pointers in source_map.items()
        if p == RDF.first
    ]
    rests = [
        pointers
        for (s, p, o, g), pointers in source_map.items()
        if p == RDF.rest
    ]
    # each duplicate list item keeps its own position
    assert len(firsts) == 2
    assert {"/ex:p/@list/0", "/ex:p"} in firsts
    assert {"/ex:p/@list/1", "/ex:p"} in firsts
    # structural rest statements are attributed to the list container
    assert len(rests) == 2
    assert all(pointers == {"/ex:p"} for pointers in rests)

def test_source_map_reverse_keyword():
    """
    A statement generated through @reverse should be attributed to the
    position of the reversed value in the input.
    """
    input = {
        "@context": {"ex": "http://example.com/"},
        "@id": "ex:o",
        "@reverse": {"ex:p": {"@id": "ex:s"}},
    }

    dataset, source_map = jsonld.to_rdf(input, {"sourceMap": True})

    key = (
        URIRef("http://example.com/s"),
        URIRef("http://example.com/p"),
        URIRef("http://example.com/o"),
        None,
    )
    assert source_map[key] == {"/@reverse/ex:p"}

def test_source_map_reverse_term():
    """
    A statement generated through a term with a reverse mapping should be
    attributed to the position of the term value in the input.
    """
    input = {
        "@context": {
            "ex": "http://example.com/",
            "knownBy": {"@reverse": "ex:knows"},
        },
        "@id": "ex:o",
        "knownBy": {"@id": "ex:s"},
    }

    dataset, source_map = jsonld.to_rdf(input, {"sourceMap": True})

    key = (
        URIRef("http://example.com/s"),
        URIRef("http://example.com/knows"),
        URIRef("http://example.com/o"),
        None,
    )
    assert source_map[key] == {"/knownBy"}

def test_source_map_named_graph():
    """
    Statements in a named graph should be keyed by their graph and keep
    source pointers into the @graph member of the input.
    """
    input = {
        "@context": {"ex": "http://example.com/"},
        "@id": "ex:g",
        "@graph": {"@id": "ex:s", "ex:p": "v"},
    }

    dataset, source_map = jsonld.to_rdf(input, {"sourceMap": True})

    key = (
        URIRef("http://example.com/s"),
        URIRef("http://example.com/p"),
        Literal("v", datatype=XSD.string),
        URIRef("http://example.com/g"),
    )
    assert source_map[key] == {"/@graph/ex:p"}

def test_source_map_types():
    """
    Type statements should be attributed to the @type positions in the
    input, merging sources for equal types.
    """
    input = {
        "@context": {"ex": "http://example.com/"},
        "@graph": [
            {"@id": "ex:s", "@type": ["ex:A", "ex:B"]},
            {"@id": "ex:s", "@type": "ex:A"},
        ],
    }

    dataset, source_map = jsonld.to_rdf(input, {"sourceMap": True})

    type_a = (
        URIRef("http://example.com/s"),
        RDF.type,
        URIRef("http://example.com/A"),
        None,
    )
    type_b = (
        URIRef("http://example.com/s"),
        RDF.type,
        URIRef("http://example.com/B"),
        None,
    )
    assert source_map[type_a] == {"/@graph/0/@type/0", "/@graph/1/@type"}
    assert source_map[type_b] == {"/@graph/0/@type/1"}

def test_source_map_does_not_change_dataset():
    """
    Source map tracking should not change blank node allocation or
    statement content.
    """
    input = {
        "@context": {
            "ex": "http://example.com/",
            "knownBy": {"@reverse": "ex:knows"},
        },
        "@graph": [
            {"@id": "ex:s", "ex:p": {"@list": ["a", {"@id": "ex:o"}]}},
            {"@id": "ex:o", "knownBy": {"@id": "ex:s"}},
            {
                "@id": "ex:g",
                "@graph": {"@id": "ex:t", "@type": "ex:T", "ex:q": "v"},
            },
        ],
    }

    plain = jsonld.to_rdf(input)
    tracked, source_map = jsonld.to_rdf(input, {"sourceMap": True})

    assert set(plain.quads()) == set(tracked.quads())
    assert len(source_map) == len(set(tracked.quads()))

def test_source_map_result_format():
    """
    The main result should keep its original format when a source map is
    requested.
    """
    input = {
        "@context": {"ex": "http://example.com/"},
        "@id": "ex:s",
        "ex:p": "v",
    }

    # without the option, the result is returned as before
    assert isinstance(jsonld.to_rdf(input), Dataset)

    dataset, source_map = jsonld.to_rdf(input, {"sourceMap": True})
    assert isinstance(dataset, Dataset)
    assert isinstance(source_map, dict)

    nquads, source_map = jsonld.to_rdf(
        input, {"sourceMap": True, "format": "application/n-quads"}
    )
    assert isinstance(nquads, str)
    assert isinstance(source_map, dict)
