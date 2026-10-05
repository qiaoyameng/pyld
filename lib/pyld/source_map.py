"""
Source map support for JSON-LD to RDF conversion.

Tracks JSON Pointer (RFC 6901) locations in the JSON-LD input document and
associates them with the RDF statements they produce, without altering
blank node allocation or statement content.
"""

__all__ = ['SourceTracker', 'escape_pointer_token', 'join_pointer']


def escape_pointer_token(token):
    """
    Escapes a single JSON Pointer reference token (RFC 6901).

    :param token: the reference token (object key or array index).

    :return: the escaped token.
    """
    return str(token).replace('~', '~0').replace('/', '~1')


def join_pointer(pointer, token):
    """
    Appends a reference token to a JSON Pointer.

    :param pointer: the parent JSON Pointer ('' for the document root).
    :param token: the reference token to append.

    :return: the extended JSON Pointer.
    """
    return pointer + '/' + escape_pointer_token(token)


class SourceTracker:
    """
    Collects source pointers during JSON-LD expansion, node map creation,
    and RDF generation.

    Expanded and node map objects are tracked by identity; references to
    tracked objects are retained so that object ids cannot be recycled by
    the garbage collector while provenance is still being gathered.
    """

    def __init__(self):
        # id(obj) -> set of JSON Pointers in the input document
        self._sources = {}
        # id(node) -> {type IRI: set of JSON Pointers}
        self._type_sources = {}
        # id(obj) -> obj, keeps tracked objects alive
        self._objects = {}
        # (graph name, subject, predicate, object) -> set of JSON Pointers
        self.statements = {}

    def add(self, obj, pointer):
        """
        Records a single source pointer for an object.

        :param obj: the expanded or node map object.
        :param pointer: the JSON Pointer into the input document.
        """
        if obj is None:
            return
        self._objects.setdefault(id(obj), obj)
        self._sources.setdefault(id(obj), set()).add(pointer)

    def add_all(self, obj, pointers):
        """
        Records a set of source pointers for an object.

        :param obj: the expanded or node map object.
        :param pointers: an iterable of JSON Pointers.
        """
        if obj is None or not pointers:
            return
        self._objects.setdefault(id(obj), obj)
        self._sources.setdefault(id(obj), set()).update(pointers)

    def sources_of(self, obj):
        """
        Gets the source pointers recorded for an object.

        :param obj: the expanded or node map object.

        :return: the set of JSON Pointers for the object (possibly empty).
        """
        return self._sources.get(id(obj), frozenset())

    def add_type(self, node, type_, pointers):
        """
        Records source pointers for an @type entry of a node.

        :param node: the expanded or node map node object.
        :param type_: the @type IRI.
        :param pointers: an iterable of JSON Pointers.
        """
        if not pointers:
            return
        self._objects.setdefault(id(node), node)
        types = self._type_sources.setdefault(id(node), {})
        types.setdefault(type_, set()).update(pointers)

    def type_sources_of(self, node, type_):
        """
        Gets the source pointers recorded for an @type entry of a node.

        :param node: the expanded or node map node object.
        :param type_: the @type IRI.

        :return: the set of JSON Pointers for the @type (possibly empty).
        """
        return self._type_sources.get(id(node), {}).get(type_, frozenset())

    def record(self, graph, subject, predicate, object_, pointers):
        """
        Records the source pointers for a generated RDF statement.

        :param graph: the name of the graph the statement belongs to.
        :param subject: the RDF subject.
        :param predicate: the RDF predicate.
        :param object_: the RDF object.
        :param pointers: an iterable of JSON Pointers.
        """
        key = (graph, subject, predicate, object_)
        self.statements.setdefault(key, set()).update(pointers)
