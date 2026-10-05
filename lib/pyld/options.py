"""
TypedDict types for JSON-LD API options.

.. module:: options
  :synopsis: Option dict types for JSON-LD API functions
"""

from collections.abc import Callable
from typing import Any, Literal, TypedDict

from .documentloader.base import DocumentLoader, RemoteDocument
from .identifier_issuer import IdentifierIssuer

ContextObject = dict[str, Any]
Context = str | ContextObject | list[str | ContextObject]
"""JSON-LD context value: remote URL, inline object, or ordered stack."""

DocumentLoaderCallable = Callable[[str, dict[str, Any]], RemoteDocument]


class ContextSource(TypedDict, total=False):
    """One layer of the active context in effect when a diagnostic was recorded."""

    kind: Literal[
        'initial',
        'expandContext',
        'remote',
        'local',
        'property-scoped',
        'term-scoped',
        'type-scoped',
    ]
    """How the context layer was introduced: the `initial` context, the `expandContext`
    option, a `remote` context from an HTTP Link header, a `local` `@context` in the
    document, or a `property-scoped`, `term-scoped`, or `type-scoped` context."""

    url: str
    """The remote context URL, for `remote` layers."""

    pointer: str
    """JSON Pointer (RFC 6901) to the `@context` member in the source document, for
    `local` layers."""

    term: str
    """The term whose definition carries the scoped context, for `property-scoped`
    and `term-scoped` layers."""

    type: str
    """The `@type` value whose term definition carries the scoped context, for
    `type-scoped` layers."""


class ExpansionDiagnostic(TypedDict):
    """A diagnostic describing a source field dropped during expansion."""

    pointer: str
    """JSON Pointer (RFC 6901) to the dropped field in the source document. Keys
    containing `~` or `/` are escaped as `~0` and `~1`."""

    key: str | None
    """The original JSON key as it appears in the source document (never the
    expanded IRI), or `None` for a dropped array item."""

    reason: Literal['undefined term', 'not an absolute IRI', 'null value']
    """Why the field was dropped: the key is not defined in the active context
    (`undefined term`), the key expands to a relative IRI (`not an absolute IRI`),
    or the value is null (`null value`)."""

    expandedProperty: str | None
    """The result of expanding the key against the active context: `None` for
    undefined terms, otherwise the (relative) IRI that was rejected."""

    contextSource: list[ContextSource]
    """The layered origin of the active context in effect when the field was
    dropped, outermost layer first."""


class DocumentLoaderOptions(TypedDict, total=False):
    """Options shared by APIs that load remote contexts."""

    documentLoader: DocumentLoader | DocumentLoaderCallable
    """The document loader (default: the global default document loader)."""


class ProcessingOptions(DocumentLoaderOptions, total=False):
    """Options shared by JSON-LD processing APIs."""

    base: str
    """The base IRI to use."""

    extractAllScripts: bool
    """`True` to extract all JSON-LD script elements from HTML, `False` to extract just the first (default: `False`)."""

    processingMode: Literal['json-ld-1.0', 'json-ld-1.1']
    """Either `json-ld-1.0` or `json-ld-1.1` (default: `json-ld-1.1`)."""


class ExpandContextOptions(ProcessingOptions, total=False):
    """Processing options that accept an expand context."""

    expandContext: Context
    """A context to expand with."""


class CompactOptions(ExpandContextOptions, total=False):
    documentLoader: DocumentLoader | DocumentLoaderCallable
    """The document loader (default: the global default document loader)."""

    base: str
    """The base IRI to use."""

    extractAllScripts: bool
    """`True` to extract all JSON-LD script elements from HTML, `False` to extract just the first (default: `False`)."""

    processingMode: Literal['json-ld-1.0', 'json-ld-1.1']
    """Either `json-ld-1.0` or `json-ld-1.1` (default: `json-ld-1.1`)."""

    expandContext: Context
    """A context to expand with."""

    compactArrays: bool
    """`True` to compact arrays to single values when appropriate, `False` not to (default: `True`)."""

    graph: bool
    """`True` to always output a top-level graph (default: `False`)."""


class ExpandOptions(ExpandContextOptions, total=False):
    documentLoader: DocumentLoader | DocumentLoaderCallable
    """The document loader (default: the global default document loader)."""

    base: str
    """The base IRI to use."""

    diagnostics: list[ExpansionDiagnostic]
    """A list to be populated with a diagnostic for each source field dropped
    during expansion (default: `None`, diagnostics disabled). Expansion results
    are unchanged whether or not diagnostics are collected."""

    extractAllScripts: bool
    """`True` to extract all JSON-LD script elements from HTML, `False` to extract just the first (default: `False`)."""

    processingMode: Literal['json-ld-1.0', 'json-ld-1.1']
    """Either `json-ld-1.0` or `json-ld-1.1` (default: `json-ld-1.1`)."""

    expandContext: Context
    """A context to expand with."""


class FlattenOptions(ExpandContextOptions, total=False):
    documentLoader: DocumentLoader | DocumentLoaderCallable
    """The document loader (default: the global default document loader)."""

    base: str
    """The base IRI to use."""

    extractAllScripts: bool
    """`True` to extract all JSON-LD script elements from HTML, `False` to extract just the first (default: `True`)."""

    processingMode: Literal['json-ld-1.0', 'json-ld-1.1']
    """Either `json-ld-1.0` or `json-ld-1.1` (default: `json-ld-1.1`)."""

    expandContext: Context
    """A context to expand with."""

    identifierIssuer: IdentifierIssuer
    """An identifier issuer to use for blank node identifiers (default: `IdentifierIssuer('_:b')`)."""


class FrameOptions(ExpandContextOptions, total=False):
    documentLoader: DocumentLoader | DocumentLoaderCallable
    """The document loader (default: the global default document loader)."""

    base: str
    """The base IRI to use."""

    extractAllScripts: bool
    """`True` to extract all JSON-LD script elements from HTML, `False` to extract just the first (default: `False`)."""

    processingMode: Literal['json-ld-1.0', 'json-ld-1.1']
    """Either `json-ld-1.0` or `json-ld-1.1` (default: `json-ld-1.1`)."""

    expandContext: Context
    """A context to expand with."""

    embed: Literal['@once', '@last', '@always', '@never', '@link']
    """Default `@embed` flag (default: `@once`)."""

    explicit: bool
    """Default `@explicit` flag (default: `False`)."""

    omitDefault: bool
    """Default `@omitDefault` flag (default: `False`)."""

    pruneBlankNodeIdentifiers: bool
    """Remove unnecessary blank node identifiers (default: `True`)."""

    requireAll: bool
    """Default `@requireAll` flag (default: `False`)."""

    identifierIssuer: IdentifierIssuer
    """An identifier issuer to use for blank node identifiers (default: `IdentifierIssuer('_:b')`)."""


class NormalizeOptions(ProcessingOptions, total=False):
    documentLoader: DocumentLoader | DocumentLoaderCallable
    """The document loader (default: the global default document loader)."""

    base: str
    """The base IRI to use."""

    extractAllScripts: bool
    """`True` to extract all JSON-LD script elements from HTML, `False` to extract just the first (default: `False`)."""

    processingMode: Literal['json-ld-1.0', 'json-ld-1.1']
    """Either `json-ld-1.0` or `json-ld-1.1` (default: `json-ld-1.1`)."""

    algorithm: Literal['URDNA2015', 'URGNA2012', 'RDFC10']
    """The algorithm to use (default: `RDFC10`)."""

    hashAlgorithm: str
    """The hashing algorithm for `RDFC10` (default: `SHA256`)."""

    inputFormat: Literal['application/n-quads']
    """The format if input is not JSON-LD: `application/n-quads` for N-Quads."""

    format: Literal['application/n-quads']
    """The format if output is a string: `application/n-quads` for N-Quads."""

    outputMap: bool
    """`True` to return a blank node identifier map instead of the normalized dataset (default: `False`)."""

    maxPermutations: int | None
    """Maximum `Hash N-Degree Quads` permutations before aborting canonicalization to prevent dataset poisoning, or `None` for no limit (default: `100000`)."""


class ToRdfOptions(ProcessingOptions, total=False):
    documentLoader: DocumentLoader | DocumentLoaderCallable
    """The document loader (default: the global default document loader)."""

    base: str
    """The base IRI to use."""

    extractAllScripts: bool
    """`True` to extract all JSON-LD script elements from HTML, `False` to extract just the first (default: `True`)."""

    processingMode: Literal['json-ld-1.0', 'json-ld-1.1']
    """Either `json-ld-1.0` or `json-ld-1.1` (default: `json-ld-1.1`)."""

    format: Literal['application/n-quads']
    """The format to use to output a string: `application/n-quads` for N-Quads."""

    produceGeneralizedRdf: bool
    """`True` to output generalized RDF, `False` to produce only standard RDF (default: `False`)."""

    identifierIssuer: IdentifierIssuer
    """An identifier issuer to use for blank node identifiers (default: `IdentifierIssuer('_:b')`)."""

    rdfDirection: Literal['i18n-datatype', 'compound-literal']
    """Either `i18n-datatype` or `compound-literal` is supported (default: `None`)."""

    legacyMode: bool
    """`True` to return the RDF.js-like dataset `dict` used by PyLD versions lower than 4 instead of an `rdflib.Dataset` when `format` is not set (default: `False`)."""


class FromRdfOptions(TypedDict, total=False):
    format: Literal['application/n-quads']
    """The format if input is a string: `application/n-quads` for N-Quads (default: `application/n-quads`)."""

    useRdfType: bool
    """`True` to use `rdf:type`, `False` to use `@type` (default: `False`)."""

    useNativeTypes: bool
    """`True` to convert XSD types into native types (boolean, integer, double), `False` not to (default: `False`)."""

    rdfDirection: Literal['i18n-datatype', 'compound-literal']
    """Either `i18n-datatype` or `compound-literal` is supported (default: `None`)."""
