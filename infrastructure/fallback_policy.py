import logging
import psycopg2.errors
import time
from datetime import datetime, timezone
from typing import Optional

from adapters.addis_fortune.adapter import AF_SLUG_MAP, AddisFortuneAdapter
from domain.fallback import FallbackPolicy
from infrastructure.error_classifier import default_classifier
from infrastructure.rate_source_repository import RateSourceRepository
from pipeline.ingest import ingest
from pipeline.runs import finish_run, start_run
from scheduler.extraction.recorder import _run_status, _reset_failure_counter, _expire_stale_fallback_current

logger = logging.getLogger(__name__)


class AddisFortuneFallbackPolicy:
    @property
    def adapter_name(self) -> str:
        return "addis_fortune"

    def attempt(
        self,
        conn,
        source_id: int,
        adapter_key: str,
        user_agent: str,
    ) -> Optional[dict]:
        slug = AF_SLUG_MAP.get(adapter_key)
        if not slug:
            return None

        af_adapter = AddisFortuneAdapter(slug)

        try:
            run_id = start_run(conn, source_id)
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            return None

        t0 = time.monotonic()
        try:
            raw_content, http_status = af_adapter.fetch_raw(
                af_adapter.get_source_url(), user_agent, ssl_verify=True
            )
            result_obj = af_adapter.parse(raw_content)
            records = result_obj.records if hasattr(result_obj, "records") else result_obj

            fetched_at = datetime.now(timezone.utc)
            ingest_result = ingest(
                conn, records, source_id, run_id,
                fetched_at=fetched_at, is_fallback=True,
            )

            duration_ms = int((time.monotonic() - t0) * 1000)
            run_status = _run_status(ingest_result)

            finish_run(
                conn, run_id, run_status,
                http_status=http_status,
                records_found=len(records),
                records_accepted=ingest_result.accepted,
                records_flagged=ingest_result.flagged,
                records_duplicated=ingest_result.duplicates,
                duration_ms=duration_ms,
                is_fallback=True,
                fallback_adapter=self.adapter_name,
            )

            if run_status in ("success", "partial_success"):
                repo = RateSourceRepository(conn)
                repo.update_last_success(source_id)
                _reset_failure_counter(conn, source_id)
                _expire_stale_fallback_current(conn, source_id)

            return {
                "source_id": source_id,
                "status": run_status,
                "accepted": ingest_result.accepted,
                "flagged": ingest_result.flagged,
                "rejected": ingest_result.rejected,
                "duplicates": ingest_result.duplicates,
                "fallback": self.adapter_name,
            }

        except (OSError, RuntimeError, ValueError, psycopg2.Error) as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            error_code, error_summary = default_classifier.classify(exc)
            logger.warning("Fallback attempt failed for source_id=%s: %s", source_id, exc)
            try:
                finish_run(
                    conn, run_id, "failed",
                    error_code=error_code,
                    error_summary=error_summary[:500] if error_summary else None,
                    duration_ms=duration_ms,
                    is_fallback=True,
                    fallback_adapter=self.adapter_name,
                )
            except psycopg2.Error as finish_exc:
                logger.warning("finish_run failed during fallback cleanup: %s", finish_exc)
            conn.rollback()
            return None


class NoFallbackPolicy:
    @property
    def adapter_name(self) -> str:
        return "none"

    def attempt(
        self,
        conn,
        source_id: int,
        adapter_key: str,
        user_agent: str,
    ) -> Optional[dict]:
        return None


default_fallback_policy = AddisFortuneFallbackPolicy()
