"""
JSON-LD context comparison tooling.

Compares an old and a new JSON-LD context under a fixed base IRI and
reports how existing inputs would be reinterpreted: term IRI mappings,
type and language coercions, containers, reverse properties and protected
definitions. For every difference a witness can be constructed for, the
report carries a small JSON-LD document per side (ready to be replayed
with :func:`pyld.jsonld.expand`) along with both expansion results.

.. module:: context_diff
  :synopsis: Context comparison and witness generation
"""

import copy
from typing import Any
from urllib.parse import quote

from pyld.documentloader.base import DocumentLoader
from pyld.jsonld import JsonLdError, JsonLdProcessor, expand
from pyld.options import Context, DocumentLoaderCallable

__all__ = ['compare_contexts']

# sentinel for "key absent from the term definition" (distinct from an
# explicit null, e.g. ``@language: None`` suppresses language tagging)
_UNSET = object()

# containers for which no simple value witness can be built
_UNSUPPORTED_CONTAINERS = ('@graph', '@type')

# IRI used to shadow a term when probing protected redefinition
_REDEFINITION_IRI = 'https://example.com/ctx-diff/redefined#'


def compare_contexts(
    old_context: Context | None,
    new_context: Context | None,
    base: str | None = None,
    document_loader: DocumentLoader | DocumentLoaderCallable | None = None,
    processing_mode: str = 'json-ld-1.1',
) -> dict[str, Any]:
    """
    Compares two JSON-LD contexts under a fixed base IRI.

    Both contexts are processed with the given ``document_loader`` for any
    remote context references and their term definitions are compared after
    full IRI expansion, so equivalent prefix spellings (e.g. ``ex:name``
    versus an absolute ``@id``) do not raise an alert. Neither input
    context is modified.

    :param old_context: the currently published context (URL, object or
        array of both).
    :param new_context: the candidate replacement context.
    :param base: the fixed base IRI both contexts are evaluated against.
    :param document_loader: loader used to fetch remote contexts.
    :param processing_mode: the JSON-LD processing mode (default:
        ``json-ld-1.1``).

    :return: a JSON-serializable report with ``changes`` (each carrying a
        replayable ``witness`` with both expansion results),
        ``undetermined`` combinations that could not be decided, and
        context-level ``errors``.
    """
    old_ctx = copy.deepcopy(old_context)
    new_ctx = copy.deepcopy(new_context)

    options: dict[str, Any] = {'processingMode': processing_mode}
    if base is not None:
        options['base'] = base
    if document_loader is not None:
        options['documentLoader'] = document_loader

    report: dict[str, Any] = {
        'base': base,
        'processing_mode': processing_mode,
        'changes': [],
        'undetermined': [],
        'errors': [],
    }

    processor = JsonLdProcessor()
    old_active = _process(processor, old_ctx, options, 'old', report)
    new_active = _process(processor, new_ctx, options, 'new', report)

    if old_active is None or new_active is None:
        for term in sorted(_scan_terms(old_ctx) | _scan_terms(new_ctx)):
            report['undetermined'].append(
                {
                    'term': term,
                    'reason': 'a context could not be processed; see errors',
                }
            )
        return _finish(report)

    old_mappings = old_active['mappings']
    new_mappings = new_active['mappings']
    for term in sorted(set(old_mappings) | set(new_mappings)):
        _compare_term(
            term,
            old_mappings.get(term),
            new_mappings.get(term),
            old_ctx,
            new_ctx,
            options,
            report,
        )

    _compare_defaults(old_active, new_active, old_ctx, new_ctx, options, report)

    return _finish(report)


def _process(processor, local_ctx, options, side, report):
    """Processes a context, recording failures in the report."""
    try:
        initial = processor._get_initial_context(options)
        return processor.process_context(initial, local_ctx, options)
    except JsonLdError as e:
        report['errors'].append(
            {'context': side, 'message': str(e), 'type': e.type, 'code': e.code}
        )
    except Exception as e:
        report['errors'].append(
            {
                'context': side,
                'message': str(e),
                'type': type(e).__name__,
                'code': None,
            }
        )
    return None


def _scan_terms(ctx):
    """Collects term names from an unprocessed context (best effort)."""
    terms = set()
    if isinstance(ctx, dict):
        for key in ctx:
            if not key.startswith('@'):
                terms.add(key)
    elif isinstance(ctx, list):
        for item in ctx:
            terms |= _scan_terms(item)
    return terms


def _signature(mapping):
    """Normalizes a processed term definition for comparison."""
    if mapping is None:
        return None
    sig = {
        '@id': mapping.get('@id'),
        '@reverse': bool(mapping.get('reverse')),
        '@protected': bool(mapping.get('protected')),
        '@prefix': bool(mapping.get('_prefix')),
    }
    for key in ('@type', '@language', '@direction', '@index', '@nest'):
        sig[key] = mapping.get(key, _UNSET)
    if '@container' in mapping:
        sig['@container'] = sorted(mapping['@container'])
    if '@context' in mapping:
        sig['@context'] = mapping['@context']
    return sig


def _public(sig):
    """Strips internal sentinels from a signature for the report."""
    if sig is None:
        return None
    return {key: value for key, value in sig.items() if value is not _UNSET}


def _kinds(old_sig, new_sig):
    """Classifies the differences between two term signatures."""
    kinds = []
    if old_sig.get('@id') != new_sig.get('@id'):
        kinds.append('iri')
    if old_sig.get('@reverse') != new_sig.get('@reverse'):
        kinds.append('reverse')
    if old_sig.get('@type') != new_sig.get('@type'):
        kinds.append('type_coercion')
    if old_sig.get('@language') != new_sig.get('@language') or old_sig.get(
        '@direction'
    ) != new_sig.get('@direction'):
        kinds.append('language')
    if old_sig.get('@container') != new_sig.get('@container'):
        kinds.append('container')
    if old_sig.get('@protected') != new_sig.get('@protected'):
        kinds.append('protected')
    if old_sig.get('@prefix') != new_sig.get('@prefix'):
        kinds.append('prefix')
    if old_sig.get('@index') != new_sig.get('@index'):
        kinds.append('index')
    if old_sig.get('@nest') != new_sig.get('@nest'):
        kinds.append('nest')
    if old_sig.get('@context') != new_sig.get('@context'):
        kinds.append('scoped_context')
    return kinds


def _compare_term(term, old_mapping, new_mapping, old_ctx, new_ctx, options, report):
    """Compares one term definition and records the outcome."""
    old_sig = _signature(old_mapping)
    new_sig = _signature(new_mapping)
    if old_sig == new_sig:
        return
    if old_sig is None:
        kinds = ['added']
    elif new_sig is None:
        kinds = ['removed']
    else:
        kinds = _kinds(old_sig, new_sig)

    entry = {
        'term': term,
        'kinds': kinds,
        'old': _public(old_sig),
        'new': _public(new_sig),
    }

    if 'scoped_context' in kinds:
        entry['reason'] = (
            'term carries a scoped @context; nested reinterpretation is not analyzed'
        )
        report['undetermined'].append(entry)
        return

    witness = _build_witness(term, kinds, old_sig, new_sig, old_ctx, new_ctx, options)
    if witness is None:
        entry['reason'] = 'no witness could be constructed for this combination'
        report['undetermined'].append(entry)
        return

    entry['witness'] = witness
    report['changes'].append(entry)


def _compare_defaults(old_active, new_active, old_ctx, new_ctx, options, report):
    """Compares context-level defaults (@vocab, @base, @language, @direction)."""
    for key, kind in (
        ('@vocab', 'vocab'),
        ('@base', 'base'),
        ('@language', 'language'),
        ('@direction', 'language'),
    ):
        old_value = old_active.get(key)
        new_value = new_active.get(key)
        if old_value == new_value:
            continue
        entry = {
            'term': key,
            'kinds': [kind],
            'old': old_value,
            'new': new_value,
        }
        witness = _default_witness(
            key, old_active, new_active, old_ctx, new_ctx, options
        )
        if witness is None:
            entry['reason'] = 'no term available to demonstrate the change'
            report['undetermined'].append(entry)
        else:
            entry['witness'] = witness
            report['changes'].append(entry)


def _default_witness(key, old_active, new_active, old_ctx, new_ctx, options):
    """Builds a witness for a context-level default change."""
    if key == '@vocab':
        term = _plain_term(old_active, new_active)
        if term is None:
            return None

        def make_doc(ctx):
            return {'@context': ctx, term: 'value'}
    elif key == '@base':

        def make_doc(ctx):
            return {
                '@context': ctx,
                '@id': 'item',
                'https://example.com/predicate': 'value',
            }
    else:
        # @language / @direction defaults apply to any untyped string value

        def make_doc(ctx):
            return {'@context': ctx, 'https://example.com/predicate': 'hello'}

    return _replay(make_doc, old_ctx, new_ctx, options)


def _plain_term(*active_contexts):
    """Finds a simple term defined in any of the given active contexts."""
    for active_ctx in active_contexts:
        for term, mapping in sorted(active_ctx['mappings'].items()):
            if mapping is not None and ':' not in term and not term.startswith('@'):
                return term
    return None


def _value_for(defs, containers):
    """Chooses a small JSON value exercising the given definitions."""
    if '@language' in containers:
        return {'en': 'hello', 'de': 'hallo'}
    if '@index' in containers:
        return {'key': 'value'}
    if '@list' in containers or '@set' in containers:
        return ['alpha', 'beta']
    types = {d.get('@type') for d in defs} - {_UNSET, None, '@none'}
    if types & {'@id', '@vocab'}:
        return 'https://example.com/target'
    if '@json' in types:
        return {'a': 1}
    if types:
        return '42'
    if any(
        isinstance(d.get('@language'), str) or isinstance(d.get('@direction'), str)
        for d in defs
    ):
        return 'hello'
    if any(d.get('@reverse') for d in defs):
        return {'@id': 'https://example.com/target'}
    return 'value'


def _build_witness(term, kinds, old_sig, new_sig, old_ctx, new_ctx, options):
    """Builds a witness demonstrating the term definition change."""
    defs = [sig for sig in (old_sig, new_sig) if sig]
    containers = set()
    for sig in defs:
        containers.update(sig.get('@container') or [])
    if containers & set(_UNSUPPORTED_CONTAINERS):
        return None

    candidates = []
    if ':' not in term and any(d.get('@prefix') for d in defs):
        # prefix terms are best demonstrated through prefix:suffix usage
        candidates.append(lambda ctx: {'@context': ctx, term + ':witness': 'value'})
    value = _value_for(defs, containers)
    candidates.append(lambda ctx: {'@context': ctx, term: value})
    if 'protected' in kinds:
        redefinition = {term: {'@id': _REDEFINITION_IRI + quote(term, safe='')}}
        candidates.append(
            lambda ctx: {'@context': [ctx, redefinition], term: 'shadowed'}
        )

    first = None
    for make_doc in candidates:
        witness = _replay(make_doc, old_ctx, new_ctx, options)
        if first is None:
            first = witness
        if _observable(witness):
            return witness
    return first


def _replay(make_doc, old_ctx, new_ctx, options):
    """Expands a witness document against both contexts."""
    old_doc = make_doc(old_ctx)
    new_doc = make_doc(new_ctx)
    old_expansion, old_error = _expand_safe(old_doc, options)
    new_expansion, new_error = _expand_safe(new_doc, options)
    return {
        'old_document': old_doc,
        'new_document': new_doc,
        'old_expansion': old_expansion,
        'new_expansion': new_expansion,
        'old_error': old_error,
        'new_error': new_error,
    }


def _expand_safe(doc, options):
    """Expands a document, capturing processing errors instead of raising."""
    try:
        return expand(doc, dict(options)), None
    except JsonLdError as e:
        return None, {'message': str(e), 'type': e.type, 'code': e.code}
    except Exception as e:
        return None, {'message': str(e), 'type': type(e).__name__, 'code': None}


def _observable(witness):
    """Checks whether a witness shows a difference between both sides."""
    if witness['old_error'] != witness['new_error']:
        return True
    return witness['old_expansion'] != witness['new_expansion']


def _finish(report):
    """Adds summary counts to the report."""
    report['summary'] = {
        'changes': len(report['changes']),
        'undetermined': len(report['undetermined']),
        'errors': len(report['errors']),
    }
    return report
