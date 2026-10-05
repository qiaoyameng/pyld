from pyld import jsonld

doc = {
    "@context": {"ex": "http://example.org/"},
    "@graph": [
        {"@id": "ex:a", "ex:p": "v"},
        {"@id": "ex:a", "ex:p": "v"},
    ],
}

result = jsonld.to_rdf(
    doc,
    {"format": "application/n-quads", "sourceMap": True},
)

for statement, sources in result.sourceMap.items():
    print(statement.strip(), "->", sources)
