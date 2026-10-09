"""Bounded per-printer metadata; documents and active jobs are never restored."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from pathlib import PurePosixPath
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1
MAX_RECORDS = 10
RETENTION = timedelta(days=7)
OUTCOMES = {"completed", "canceled", "aborted", "unknown"}


def store_key(entry_id: str) -> str:
    return f"ipp_print.activity.{entry_id}"


def _date(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        date = datetime.fromisoformat(value)
        return date.astimezone(timezone.utc) if date.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def _record(value: Any) -> dict | None:
    if not isinstance(value, dict):
        return None
    job_id, filename, state = value.get("job_id"), value.get("filename"), value.get("state")
    submitted, finished = _date(value.get("submitted_at")), _date(value.get("finished_at"))
    if (type(job_id) is not int or job_id < 1 or not isinstance(filename, str)
            or submitted is None or not isinstance(state, str) or state not in OUTCOMES | {"pending"}):
        return None
    if state != "unknown" and state != "pending" and finished is None:
        return None
    try:
        expires = (submitted + RETENTION).isoformat()
    except OverflowError:
        return None
    unit = value.get("progress_unit")

    def count(value):
        return value if type(value) is int and value >= 0 else None

    return {
        "job_id": job_id, "filename": PurePosixPath(filename.replace("\\", "/")).name[:120],
        "state": state, "submitted_at": submitted.isoformat(),
        "finished_at": finished.isoformat() if finished else None,
        "expires_at": expires,
        "pages_done": count(value.get("pages_done")),
        "progress_unit": unit if isinstance(unit, str) and unit in {"impressions", "sheets"} else None,
    }


class PrintActivity:
    def __init__(self, hass: HomeAssistant, entry_id: str | None):
        self._records: list[dict] = []
        self._closed = False
        self._store = Store(hass, STORAGE_VERSION, store_key(entry_id), private=True,
                            atomic_writes=True) if entry_id else None

    async def async_load(self) -> None:
        if not self._store:
            return
        try:
            data = await self._store.async_load()
        except Exception:
            _LOGGER.warning("Could not restore print activity", exc_info=True)
            return
        records = data.get("records") if isinstance(data, dict) else None
        if not isinstance(records, list):
            return
        found = {}
        for value in records[:MAX_RECORDS]:
            if record := _record(value):
                if record["state"] == "pending":
                    record["state"] = "unknown"  # No observed finish; never claim success.
                found[(record["job_id"], record["submitted_at"])] = record
        self._records = sorted(found.values(), key=lambda r: r["submitted_at"], reverse=True)
        self.prune()
        self._save_later()

    def record(self, job) -> None:
        if self._closed:
            return
        data = {**job.to_dict(), "state": job.state if job.is_terminal() else "pending"}
        record = _record(data)
        if record is None:
            return
        key = (record["job_id"], record["submitted_at"])
        self._records = [r for r in self._records if (r["job_id"], r["submitted_at"]) != key]
        self._records.append(record)
        self._records.sort(key=lambda r: r["submitted_at"], reverse=True)
        self._records = self._records[:MAX_RECORDS]
        self.prune()
        self._save_later()

    def prune(self) -> bool:
        now = datetime.now(timezone.utc)
        retained = [r for r in self._records if _date(r["expires_at"]) > now]
        if retained == self._records:
            return False
        self._records = retained
        self._save_later()
        return True

    def snapshot(self) -> list[dict]:
        now = datetime.now(timezone.utc)
        return [dict(r) for r in self._records if r["state"] in OUTCOMES and _date(r["expires_at"]) > now]

    def _save_later(self) -> None:
        if self._store and not self._closed:
            self._store.async_delay_save(lambda: {"records": self._records})

    async def async_close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._records = [{**r, "state": "unknown"} if r["state"] == "pending" else r for r in self._records]
        self.prune()
        if self._store:
            await self._store.async_save({"records": self._records})
