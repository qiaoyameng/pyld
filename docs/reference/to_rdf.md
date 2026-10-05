# :material-export: `jsonld.to_rdf()`

::: pyld.jsonld.to_rdf
    options:
      show_docstring_description: false

## Options

::: pyld.options.ToRdfOptions
    options:
      show_root_heading: false
      show_bases: false
      heading_level: 3

When `format` is not set, `jsonld.to_rdf()` returns a
[:material-library: RDFLib](https://rdflib.readthedocs.io/) `rdflib.Dataset`.
Set `legacyMode` to `True` to return the RDF.js-like dataset `dict` used by
PyLD versions lower than 4.

`legacyMode` only affects the unformatted return value. If `format` is set,
`jsonld.to_rdf()` returns the requested serialization.

Set `sourceMap` to `True` to trace generated statements back to the input:
`jsonld.to_rdf()` then returns a `(result, source_map)` tuple. The source
map maps each statement, keyed by `(subject, predicate, object, graph)`
(`graph` is `None` for the default graph), to the set of JSON Pointers
(RFC 6901) into the input document the statement originates from. A
statement synthesized from several input positions maps to all of them, and
structural statements generated for `@list` containers are attributed to
the container.

## Examples

### Serializing JSON-LD to N-Quads

{{ example('to_rdf.py') }}

### Transforming JSON-LD into an `rdflib.Dataset`

{{ example('to_rdf_dataset.py') }}

### Transforming JSON-LD into an legacy RDF.js-like dict

{{ example('to_rdf_legacy.py', 'json') }}

### Mapping statements to input positions

{{ example('to_rdf_source_map.py') }}
