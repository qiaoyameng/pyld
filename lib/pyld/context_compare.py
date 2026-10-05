"""
Context comparison tool for JSON-LD.

Given an old and a new JSON-LD ``@context`` (inline objects/arrays or
context URLs) and a fixed base IRI, :func:`compare_contexts` reports how
existing inputs would be re-interpreted when switching from the old context
to the new one.  The comparison covers term IRI mappings, type and language
coercion, container declarations (with ``@set``/``@list`` distinguished
semantically), reverse properties and protected definitions.

For every difference for which an input can be constructed, the report
includes a *witness*: a complete, replay-ready JSON-LD document plus its
expansion under both the old and the new context.  Witnesses embed deep
copies of the context they are replayed with, so they can be handed
directly to :func:`pyld.jsonld.expand`.  Remote contexts are fetched
through the supplied :class:`~pyld.documentloader.base.DocumentLoader`.

Combinations that cannot be decided mechanically are reported under
``undetermined`` rather than guessed at.  Neither input context is ever
mutated.
"""

import copy
import json
import re
from typing import Any, TypedDict

from .context_resolver import ContextResolver
from .documentloader.base import DocumentLoader
from .jsonld import JsonLdError, JsonLdProcessor, _resolved_context_cache

# Reported facet names.
IRI = 'iri'
TYPE = 'type'
LANGUAGE = 'language'
DIRECTION = 'direction'
CONTAINER = 'container'
REVERSE = 'reverse'
PROTECTED = 'protected'
PREFIX = 'prefix'

# Term-definition keys that affect interpretation but for which this tool
# does not synthesize a witness; their raw before/after values are reported
# and the term is marked undetermined.
_UNWITNESSED_KEYS = ('@nest', '@context', '@index')

_BNODE_RE = re.compile(r'_:[A-Za-z0-9]+')
_VALUE = 'sample'
_WITNESS_IRI = 'http://example.org/context-comparison/witness'
_MISSING = object()


class ContextComparisonOptions(TypedDict, total=False):
    """Options for :func:`compare_contexts`."""

    documentLoader: DocumentLoader
    """The :class:`DocumentLoader` used to fetch remote contexts. Required
    when either context references a remote document directly or
    transitively."""

    base: str
    """Base IRI used while processing both contexts and replaying
    witnesses."""

    processingMode: str
    """Either ``json-ld-1.0`` or ``json-ld-1.1`` (default
    ``json-ld-1.1``)."""


class Witness(TypedDict, total=False):
    """A replayable witness for a term or context-scope difference."""

    witness: dict
    """JSON-LD input document, embedding the relevant context in its own
    ``@context``.  Replay with :func:`pyld.jsonld.expand`, the same
    ``base`` and the same document loader."""

    old_expanded: Any
    """Expansion under the old context; ``None`` when expansion failed."""

    new_expanded: Any
    """Expansion under the new context; ``None`` when expansion failed."""

    old_error: str | None
    """Error ``code`` raised under the old context, if any."""

    new_error: str | None
    """Error ``code`` raised under the new context, if any."""


class TermDifference(Witness, total=False):
    """Reported change for one term or context-scope facet."""

    facets: dict[str, dict[str, Any]]
    """Changed facets; each maps to ``{'old': value, 'new': value}``.
    Absent when the whole context itself could not be processed."""

    reason: str
    """Why the change could not be witnessed (``undetermined`` only)."""


class ContextComparison(TypedDict, total=False):
    """Result of :func:`compare_contexts`."""

    differences: dict[str, TermDifference]
    """Witnessed changes keyed by term, or by ``@vocab``, ``@language``,
    ``@direction`` or ``@base`` for context-scope changes."""

    undetermined: dict[str, TermDifference]
    """Changes that could not be decided automatically, including context
    processing failures."""


def compare_contexts(
    old_context: Any,
    new_context: Any,
    options: ContextComparisonOptions | None = None,
) -> ContextComparison:
    """Compare two JSON-LD contexts and construct replayable witnesses.

    :param old_context: the currently deployed context. May be a context
        object, the value of an ``@context`` key, an array of either, or a
        context URL.
    :param new_context: the context to upgrade to; same accepted shapes.
    :param options: ``documentLoader`` (a :class:`DocumentLoader` instance),
        ``base`` and ``processingMode``.

    :return: a :class:`ContextComparison` with witnessed ``differences`` and
        an ``undetermined`` section for combinations that could not be
        decided. The two input contexts are never modified.
    """
    options = dict(options or {})
    base = options.get('base', '')
    loader = options.get('documentLoader')
    if loader is not None and not isinstance(loader, DocumentLoader):
        raise TypeError(
            'documentLoader must be a DocumentLoader instance, not a plain '
            'callable.'
        )
    processing_mode = options.get('processingMode', 'json-ld-1.1')

    # Context processing mutates the local context it walks, so operate on
    # deep copies and keep the user-supplied contexts untouched.
    old_input = copy.deepcopy(old_context)
    new_input = copy.deepcopy(new_context)

    reporter = _Reporter(
        base=base, loader=loader, processing_mode=processing_mode
    )
    old_active = reporter.process('old', old_input)
    new_active = reporter.process('new', new_input)

    differences: dict[str, TermDifference] = {}
    undetermined: dict[str, TermDifference] = {}

    if old_active is None or new_active is None:
        if old_active is not None or new_active is not None:
            side = 'new' if old_active is not None else 'old'
            error = reporter.errors[side]
            undetermined['@context'] = {
                'reason': (
                    f'the {side} context could not be processed '
                    f'({error["code"]}); term-level differences cannot be '
                    'computed safely.'
                ),
                f'{side}_error': error['code'],
            }
        return {'differences': differences, 'undetermined': undetermined}

    old_terms = dict(old_active['mappings'])
    new_terms = dict(new_active['mappings'])

    for term in sorted(set(old_terms) | set(new_terms)):
        _report_term(
            reporter,
            term,
            old_terms.get(term),
            new_terms.get(term),
            old_input,
            new_input,
            differences,
            undetermined,
        )

    for facet_key, facet in (
        ('@vocab', IRI),
        ('@language', LANGUAGE),
        ('@direction', DIRECTION),
        ('@base', 'base'),
    ):
        old_value = old_active.get(facet_key, _MISSING)
        new_value = new_active.get(facet_key, _MISSING)
        if _values_differ(old_value, new_value):
            _report_scope_facet(
                reporter, facet_key, facet, old_value, new_value,
                old_input, new_input, differences, undetermined,
            )

    return {'differences': differences, 'undetermined': undetermined}


def _no_loader(url, options):
    raise JsonLdError(
        'A remote context was referenced but no DocumentLoader was provided.',
        'jsonld.LoadDocumentError',
        {'url': url},
        code='loading remote context failed',
    )


class _Reporter:
    """Holds processing/replay configuration and context processing errors."""

    def __init__(self, base: str, loader, processing_mode: str):
        self.base = base
        self.loader = loader
        self.processing_mode = processing_mode
        self.processor = JsonLdProcessor()
        self.errors: dict[str, dict] = {}
        # A private resolved-context cache isolates this comparison from the
        # module-level shared cache used by regular API calls.
        self._context_cache: dict = {}

    def processor_options(self) -> dict:
        loader = self.loader or _no_loader
        return {
            'base': self.base,
            'processingMode': self.processing_mode,
            'documentLoader': loader,
            'contextResolver': ContextResolver(self._context_cache, loader),
        }

    def expand_options(self) -> dict:
        options = {
            'base': self.base,
            'processingMode': self.processing_mode,
        }
        if self.loader is not None:
            options['documentLoader'] = self.loader
        return options

    def process(self, side: str, context: Any):
        """Process one side; return its active context, or ``None`` on error."""
        local = context
        if isinstance(context, dict) and '@context' in context:
            local = context['@context']
        options = self.processor_options()
        active = self.processor._get_initial_context(options)
        try:
            return self.processor.process_context(active, local, options)
        except JsonLdError as error:
            self.errors[side] = {
                'code': error.code or 'jsonld.JsonLdError',
                'message': str(error),
            }
            return None

    def replay(self, document: dict):
        """Expand a witness document.

        :return: ``(expanded, error_code)`` where exactly one is non-``None``.
        """
        try:
            expanded = self.processor.expand(document, self.expand_options())
            return expanded, None
        except JsonLdError as error:
            return None, error.code or 'jsonld.JsonLdError'


def _container_facet(mapping: dict | None):
    """Normalize a processed container declaration for comparison.

    Expansion treats a missing ``@container`` and ``@set`` identically, so
    ``@set`` on its own is normalized away (and never reported as a change).
    The combination ``@set`` + ``@index`` does matter, but a plain
    ``@set`` switch produces no re-interpretation.
    """
    if mapping is None:
        return _MISSING
    container = mapping.get('@container')
    if not container:
        return frozenset()
    return frozenset(container) - {'@set'}


def _term_facets(mapping: dict | None) -> dict[str, Any]:
    """Extract the comparable facets of one processed term mapping."""
    if mapping is None:
        return {
            IRI: _MISSING,
            TYPE: _MISSING,
            LANGUAGE: _MISSING,
            DIRECTION: _MISSING,
            CONTAINER: _MISSING,
            REVERSE: _MISSING,
            PROTECTED: _MISSING,
            PREFIX: _MISSING,
        }
    return {
        IRI: mapping.get('@id', _MISSING),
        TYPE: mapping['@type'] if '@type' in mapping else None,
        LANGUAGE: mapping['@language'] if '@language' in mapping else _MISSING,
        DIRECTION: mapping['@direction'] if '@direction' in mapping
        else _MISSING,
        CONTAINER: _container_facet(mapping),
        REVERSE: bool(mapping.get('reverse')),
        PROTECTED: bool(mapping.get('protected')),
        PREFIX: bool(mapping.get('_prefix')),
    }


def _values_differ(old_value, new_value) -> bool:
    if isinstance(old_value, frozenset) or isinstance(new_value, frozenset):
        return old_value != new_value
    return old_value != new_value


def _facet_diff(old_facets, new_facets):
    """Return the facets that differ between two term facet snapshots."""
    diff = {}
    for facet in (
        IRI, TYPE, LANGUAGE, DIRECTION, CONTAINER, REVERSE, PROTECTED, PREFIX,
    ):
        old_value = old_facets[facet]
        new_value = new_facets[facet]
        if _values_differ(old_value, new_value):
            diff[facet] = {'old': old_value, 'new': new_value}
    return diff


def _present(value) -> bool:
    return value is not _MISSING


def _unwitnessed_diff(old_mapping, new_mapping):
    """Return raw key changes this tool does not synthesize witnesses for."""
    diff = {}
    old_mapping = old_mapping or {}
    new_mapping = new_mapping or {}
    for key in _UNWITNESSED_KEYS:
        old_value = old_mapping.get(key, _MISSING)
        new_value = new_mapping.get(key, _MISSING)
        if _values_differ(old_value, new_value):
            diff[key] = {'old': old_value, 'new': new_value}
    return diff


def _facet_json(value):
    """Render a facet value (possibly ``_MISSING``/frozenset) for reports."""
    if value is _MISSING:
        return None
    if isinstance(value, frozenset):
        return sorted(value)
    return value


def _reportable_facets(diff: dict) -> dict:
    return {
        facet: {'old': _facet_json(v['old']), 'new': _facet_json(v['new'])}
        for facet, v in diff.items()
    }


def _report_term(
    reporter, term, old_mapping, new_mapping,
    old_input, new_input, differences, undetermined,
):
    old_facets = _term_facets(old_mapping)
    new_facets = _term_facets(new_mapping)
    facet_diff = _facet_diff(old_facets, new_facets)
    raw_diff = _unwitnessed_diff(old_mapping, new_mapping)

    if not facet_diff and not raw_diff:
        return

    facets = _reportable_facets(facet_diff)
    for key, change in raw_diff.items():
        facets[key] = {
            'old': _facet_json(change['old']),
            'new': _facet_json(change['new']),
        }

    entry: TermDifference = {'facets': facets}

    if raw_diff:
        entry['reason'] = (
            'differences in '
            + ', '.join(sorted(raw_diff))
            + ' cannot be witnessed automatically'
        )
        undetermined[term] = entry
        return

    # A protected-only flip carries no expansion re-interpretation; it only
    # affects whether later contexts may override the term, which is probed
    # separately below when possible.
    semantic_facets = set(facet_diff) - {PROTECTED}
    witness = None
    if semantic_facets:
        witness = _build_semantic_witness(
            reporter, term, old_facets, new_facets,
            old_input, new_input,
        )

    protected = _build_protected_witness(
        reporter, term, old_facets, new_facets,
        old_input, new_input,
    )

    if witness is None and protected is None:
        if not semantic_facets and PROTECTED in facet_diff:
            # No override probe could distinguish the sides; the flip itself
            # is still a real definition change worth surfacing.
            differences[term] = entry
            return
        entry['reason'] = (
            'facet change detected but no replayable input could be '
            'constructed that distinguishes the two contexts'
        )
        undetermined[term] = entry
        return

    if witness is not None:
        entry.update(witness)
    if protected is not None:
        # The protected-redefinition probe is a second, independently
        # replayable witness, layered on top of the semantic witness.
        entry['protected_witness'] = protected['witness']
        entry['protected_old_expanded'] = protected['old_expanded']
        entry['protected_new_expanded'] = protected['new_expanded']
        entry['protected_old_error'] = protected['old_error']
        entry['protected_new_error'] = protected['new_error']
    differences[term] = entry


def _normalize_expanded(value: str) -> str:
    """Serialize expanded output with blank-node labels canonicalized.

    Blank node ids are assigned sequentially per expansion run, so they are
    replaced with a placeholder before comparing two expansions.
    """
    text = json.dumps(value, sort_keys=True, separators=(',', ':'))
    return _BNODE_RE.sub('_:b0', text)


def _document(raw_context, body: dict) -> dict:
    """Build a replay-ready document embedding a deep-copied context."""
    return {'@context': copy.deepcopy(raw_context), **body}


def _witness_candidates(term, old_facets, new_facets):
    """Construct candidate term values for a semantic facet difference.

    Each candidate is a plausible existing input using ``term``. Candidates
    are tried in order; the first whose expansions differ (or whose
    expansions fail on exactly one side) is used.
    """
    old_container = old_facets[CONTAINER]
    new_container = new_facets[CONTAINER]
    containers = set()
    for container in (old_container, new_container):
        if _present(container):
            containers |= container

    candidates = []
    # 1. Scalar: catches IRI, type/language coercion and @list vs @set.
    candidates.append(_VALUE)
    candidates.append(1)
    # 2. Language-map value.
    candidates.append({'en': _VALUE})
    # 3. Type-map value.
    candidates.append({'http://example.org/Type': _VALUE})
    # 4. Id-map value (single subject key).
    candidates.append({'http://example.org/node': {}})
    # 5. Index-map value.
    candidates.append({_VALUE: _VALUE})
    # 6. Graph node value(s).
    candidates.append(
        {'@id': 'http://example.org/graph',
         'http://example.org/l': [{'@value': _VALUE}]}
    )
    candidates.append(
        [{'@id': 'http://example.org/graph',
          'http://example.org/l': [{'@value': _VALUE}]}]
    )
    # 7. @graph @id map value.
    candidates.append(
        {'http://example.org/graph':
         {'http://example.org/l': [{'@value': _VALUE}]}}
    )
    # 8. Arbitrary JSON value (@json coercion keeps it verbatim).
    candidates.append({'arbitrary': True})
    # 9. Reverse property node value(s).
    candidates.append({'@id': 'http://example.org/node'})
    candidates.append([{'@id': 'http://example.org/node'}])

    ordered = []
    for value in candidates:
        payload = {term: value}
        if payload not in ordered:
            ordered.append(payload)

    # A CURIE under a prefix-bearing term catches @prefix redefinition.
    if PREFIX in _facet_diff(old_facets, new_facets) and ':' not in term:
        ordered.append({term + ':witness': _VALUE})

    return ordered


def _build_semantic_witness(
    reporter, term, old_facets, new_facets, old_input, new_input,
):
    """Replay candidate inputs until one distinguishes the two contexts."""
    for body in _witness_candidates(term, old_facets, new_facets):
        old_document = _document(old_input, body)
        new_document = _document(new_input, body)
        old_expanded, old_error = reporter.replay(old_document)
        new_expanded, new_error = reporter.replay(new_document)
        if _distinguishes(old_expanded, old_error, new_expanded, new_error):
            return {
                'witness': old_document,
                'old_expanded': old_expanded,
                'new_expanded': new_expanded,
                'old_error': old_error,
                'new_error': new_error,
            }
    return None


def _distinguishes(old_expanded, old_error, new_expanded, new_error) -> bool:
    if old_error is not None or new_error is not None:
        return old_error != new_error
    return (
        _normalize_expanded(old_expanded)
        != _normalize_expanded(new_expanded)
    )


def _build_protected_witness(
    reporter, term, old_facets, new_facets, old_input, new_input,
):
    """Probe whether overriding the term under a combined context errors.

    A later context overriding a *protected* term definition raises
    ``protected term redefinition``.  The witness layers an inline override
    on top of each side; an error on exactly one side proves the protection
    change is observable.
    """
    if PROTECTED not in _facet_diff(old_facets, new_facets):
        return None
    old_iri = old_facets[IRI]
    new_iri = new_facets[IRI]
    if not _present(old_iri) or not _present(new_iri):
        return None

    override_iri = new_iri if old_iri != new_iri else _WITNESS_IRI
    override = {term: {'@id': override_iri}}

    def layered(raw_input):
        if isinstance(raw_input, list):
            return [*copy.deepcopy(raw_input), override]
        return [copy.deepcopy(raw_input), override]

    body = {term: _VALUE}
    old_document = {'@context': layered(old_input), **body}
    new_document = {'@context': layered(new_input), **body}
    old_expanded, old_error = reporter.replay(old_document)
    new_expanded, new_error = reporter.replay(new_document)
    if not _distinguishes(old_expanded, old_error, new_expanded, new_error):
        return None
    return {
        'witness': old_document,
        'old_expanded': old_expanded,
        'new_expanded': new_expanded,
        'old_error': old_error,
        'new_error': new_error,
    }


def _report_scope_facet(
    reporter, context_key, facet, old_value, new_value,
    old_input, new_input, differences, undetermined,
):
    """Witness a context-scope @vocab/@language/@direction/@base change."""
    body = _scope_witness_body(context_key)
    if body is None:
        undetermined[context_key] = {
            'facets': {
                facet: {
                    'old': _facet_json(old_value),
                    'new': _facet_json(new_value),
                }
            },
            'reason': 'no replayable witness synthesized for this facet',
        }
        return

    old_document = _document(old_input, body)
    new_document = _document(new_input, body)
    old_expanded, old_error = reporter.replay(old_document)
    new_expanded, new_error = reporter.replay(new_document)
    if not _distinguishes(old_expanded, old_error, new_expanded, new_error):
        undetermined[context_key] = {
            'facets': {
                facet: {
                    'old': _facet_json(old_value),
                    'new': _facet_json(new_value),
                }
            },
            'reason': 'synthesized input does not distinguish the contexts',
        }
        return

    differences[context_key] = {
        'facets': {
            facet: {
                'old': _facet_json(old_value),
                'new': _facet_json(new_value),
            }
        },
        'witness': old_document,
        'old_expanded': old_expanded,
        'new_expanded': new_expanded,
        'old_error': old_error,
        'new_error': new_error,
    }


def _scope_witness_body(context_key: str):
    if context_key == '@vocab':
        return {'context-comparison-witness': _VALUE}
    if context_key == '@language':
        return {'context-comparison-witness': _VALUE}
    if context_key == '@direction':
        return {'context-comparison-witness': _VALUE}
    if context_key == '@base':
        return {'@id': 'context-comparison-witness'}
    return None
    """Changes that could not be decided automatically, including context
    processing failures."""
