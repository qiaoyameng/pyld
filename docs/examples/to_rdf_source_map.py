from pyld import jsonld

doc = {
    "@context": {"ex": "http://example.com/"},
    "@graph": [
        {"@id": "ex:s", "ex:p": {"@id": "ex:o"}},
        {"@id": "ex:s", "ex:p": [{"@id": "ex:o"}]},
    ],
}

dataset, source_map = jsonld.to_rdf(doc, {"sourceMap": True})

for (subject, predicate, object_, graph), pointers in sorted(
    source_map.items(), key=lambda item: str(item[0])
):
    print(f"{subject.n3()} {predicate.n3()} {object_.n3()}")
    for pointer in sorted(pointers):
        print(f"  {pointer}")
