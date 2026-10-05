# :material-import: `jsonld.from_rdf()`

::: pyld.jsonld.from_rdf
    options:
      show_docstring_description: false

## Options

::: pyld.options.FromRdfOptions
    options:
      show_root_heading: false
      show_bases: false
      heading_level: 3

`jsonld.from_rdf()` accepts a
[:material-library: RDFLib](https://rdflib.readthedocs.io/) `rdflib.Dataset`,
an N-Quads string, or the RDF.js-like dataset `dict` returned by PyLD versions
lower than 4. Prefer `rdflib.Dataset` for new in-memory RDF code.

## Examples

### Parsing N-Quads as JSON-LD

{{ example('from_rdf.py', 'json') }}

### Transforming an `rdflib.Dataset` into JSON-LD

{{ example('from_rdf_dataset.py', 'json') }}

### Diagnosing `rdf:List` folding

Set `listDiagnostics` to `True` to learn why a chain that looks like an RDF
list was not folded into `@list`. The return value becomes
`{'output': ..., 'listDiagnostics': ...}`, where `listDiagnostics` contains one
entry per candidate chain located by `graph` and `head`. Each entry reports
`folded`, the original chain `nodes`, and an `obstacles` array for chains that
were kept as ordinary nodes. Obstacles are located by input node and graph
name and use stable codes such as `multipleFirst`, `multipleRest`, `gap`,
`cycle`, `sharedNode`, `extraProperty`, `invalidListType`, and
`crossGraphReference`. Diagnostics never change the JSON-LD output or make the
conversion fail: malformed chains are retained as ordinary nodes, so their
triples survive a roundtrip back to RDF.

```python
result = jsonld.from_rdf(dataset, {'listDiagnostics': True})
for chain in result['listDiagnostics']:
    print(chain['graph'], chain['head'], chain['folded'])
    for obstacle in chain['obstacles']:
        print(' ', obstacle['code'], obstacle['node'])
```
