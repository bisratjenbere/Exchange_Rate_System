import logging
from datetime import date
from typing import Any, Tuple, List, Union

from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, Severity
from adapters.core.protocol import UniversalAdapter, is_universal_adapter
from domain.records import AdapterRecord
from domain.source import RateSource

logger = logging.getLogger(__name__)


def _get(source, key, default=None):
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def create_parse_context(
    source: Union[RateSource, dict],
    collection_date: date = None,
) -> ParseContext:
    return ParseContext(
        category=_get(source, "default_category") or "cash",
        collection_date=collection_date or date.today(),
        source_id=_get(source, "id") or _get(source, "source_id") or 0,
    )


def parse_with_adapter(
    adapter: Any,
    raw_content: str,
    source: Union[RateSource, dict],
    collection_date: date = None,
    adapter_config: dict = None,
) -> ParseOutcome:
    adapter_key = _get(source, "adapter_key") or "unknown"

    if not is_universal_adapter(adapter):
        logger.error("Adapter %s does not implement UniversalAdapter protocol", adapter_key)
        return _error_outcome("Adapter does not implement UniversalAdapter protocol")

    ctx = create_parse_context(source, collection_date)

    if adapter_config and hasattr(adapter, "slug"):
        adapter.slug = adapter_config.get("slug", adapter.slug)
        if hasattr(adapter, "url"):
            adapter.url = f"https://exchange.addisfortune.news/bank/{adapter.slug}"

    try:
        outcome = adapter.parse(raw_content, ctx)
        if not isinstance(outcome, ParseOutcome):
            logger.warning("Adapter %s returned %s, expected ParseOutcome", adapter_key, type(outcome).__name__)
            return _error_outcome(f"Adapter returned unexpected type: {type(outcome).__name__}")
        return outcome
    except Exception as e:
        logger.error("Adapter %s raised exception: %s", adapter_key, e, exc_info=True)
        return _error_outcome(f"Adapter raised exception: {e}")


def _error_outcome(detail: str) -> ParseOutcome:
    return ParseOutcome(
        records=tuple(),
        issues=(RowIssue(row_ref="page", code="bad_json", detail=detail, severity=Severity.ERROR),),
        rows_seen=0,
        structure_hash=None,
    )


def extract_errors_and_warnings(outcome: ParseOutcome) -> Tuple[List[str], List[str]]:
    errors, warnings = [], []
    for issue in outcome.issues:
        message = f"[{issue.row_ref}] {issue.detail}"
        if issue.severity == Severity.ERROR:
            errors.append(message)
        else:
            warnings.append(message)
    return errors, warnings
