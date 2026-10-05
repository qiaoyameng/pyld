"""
Source provenance tracking for ``to_rdf``.

When ``to_rdf`` is called with the ``sourceMap`` option, every object in the
deep-copied expanded document is annotated with the set of JSON Pointers (RFC
6901) of the original input locations that contributed to it. The annotation
rides along through expansion and node map construction without altering
either; once the RDF dataset is serialized, the annotations are used to build
a map of each emitted statement to the source pointers that produced it.
"""

from rdflib.plugins.serializers.nquads import _nq_row

# Annotation key carried on expanded objects. It starts with '@' so that IRI
# expansion treats it like a keyword, and every place that iterates expanded
# objects skips it explicitly.
SOURCE_KEY = '@__pyldSource__'
TYPE_SOURCES_KEY = '@__pyldTypeSources__'
CONTAINER_TAG_KEY = '@__pyldContainerTag__'

# Structural provenance kinds.
LIST_CONTAINER = 'list'
GRAPH_CONTAINER = 'graph'
REVERSE_CONTAINER = 'reverse'
COMPOUND_LITERAL_CONTAINER = 'compound-literal'


def json_pointer(parts):
    """Builds an RFC 6901 JSON Pointer from a list of reference tokens."""
    pointer = ''
    for part in parts:
        token = str(part).replace('~', '~0').replace('/', '~1')
        pointer += '/' + token
    return pointer


def merge_sources(target, *sources):
    """
    Merges source pointer sets (lists of JSON Pointer strings) into ``target``
    in place, preserving order and dropping duplicates.
    """
    for source in sources:
        if not source:
            continue
        for pointer in source:
            if pointer not in target:
                target.append(pointer)
    return target


def source_of(value):
    """Returns the mutable source pointer list attached to an expanded object."""
    if isinstance(value, dict):
        return value.get(SOURCE_KEY)
    return None


class SourceMap:
    """Collects the provenance of the statements emitted by ``to_rdf``."""

    def __init__(self):
        # identity of original scalar values -> source JSON Pointer strings
        self.scalar_sources = {}
        # identity of original arrays -> source JSON Pointer strings
        self.array_sources = {}
        # relabeled blank-node @type identifier -> source pointer strings
        self.identifier_sources = {}
        # types injected by @type/@id index containers, keyed by the object
        # carrying the injected @type -> {type IRI: [source pointers]}
        self.implicit_type_sources = {}
        # n-quads statement line -> list of provenance entry dicts
        self.statements = {}
        # graph name -> source provenance entries of its @graph container
        self.graph_sources = {}

    def annotate(self, element, parts=None):
        """
        Annotates the deep-copied original document. Every object gets a
        source pointer list under ``SOURCE_KEY``; scalar identity is recorded
        separately for leaf values.
        """
        if parts is None:
            parts = []
        if isinstance(element, dict):
            element[SOURCE_KEY] = [json_pointer(parts)]
            for key, value in element.items():
                if key == '@context':
                    continue
                self._annotate_value(value, parts + [key])
        elif isinstance(element, list):
            for index, value in enumerate(element):
                self._annotate_value(value, parts + [index])

    def _annotate_value(self, value, parts):
        if isinstance(value, (dict, list)):
            if isinstance(value, list):
                self.array_sources.setdefault(id(value), []).append(
                    json_pointer(parts)
                )
            self.annotate(value, parts)
        elif value is not None:
            self.scalar_sources.setdefault(id(value), []).append(
                json_pointer(parts)
            )

    def array_pointer(self, value):
        sources = self.array_sources.get(id(value))
        return list(sources) if sources else []

    def scalar_pointer(self, value):
        sources = self.scalar_sources.get(id(value))
        return list(sources) if sources else []

    def remember_identifier(self, new_id, old_id, sources=None):
        if sources is None:
            sources = self.identifier_sources.get(old_id, [])
        merged = self.identifier_sources.setdefault(new_id, [])
        merge_sources(merged, sources)

    def identifier_pointers(self, identifier):
        return list(self.identifier_sources.get(identifier, []))

    def set_graph_sources(self, graph_name, entries):
        self.graph_sources[graph_name] = entries

    def graph_entries(self, graph_name):
        return list(self.graph_sources.get(graph_name, ()))

    def add_statement(self, triple, graph, entries):
        """
        Records the provenance entries for one triple in the given graph.
        Duplicate entries for the same statement are merged, so every input
        location contributing to a statement is retained.
        """
        context = graph if graph is not None else None
        key = _nq_row(triple, context)
        existing = self.statements.setdefault(key, [])
        for entry in entries:
            if entry not in existing:
                existing.append(entry)

    def to_dict(self):
        """Returns a plain ordered ``dict`` mapping statement lines to sources."""
        result = {}
        for key in sorted(self.statements):
            entries = sorted(
                self.statements[key],
                key=lambda entry: (
                    entry.get('pointer', ''),
                    entry.get('container', ''),
                ),
            )
            result[key] = entries
        return result
