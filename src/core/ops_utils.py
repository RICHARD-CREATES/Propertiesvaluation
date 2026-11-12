"""
Operational Reliability Utilities — Structured PII-Safe Logging,
Rate Limiting Middleware & SQLite Online Snapshots
==================================================================
Milestone 8 — Phases 7 & 8
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Deque, Dict, Optional

from src.core.evidence_storage import redact_pii_text


class RedactingJsonFormatter(logging.Formatter):
    """Formats structured JSON logs while automatically redacting Indian PII patterns."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": redact_pii_text(record.getMessage()),
        }
        return json.dumps(payload, ensure_ascii=False)


def configure_structured_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("valuation_platform")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(RedactingJsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding-window rate limiter per client IP."""

    def __init__(self, max_requests_per_minute: int = 180) -> None:
        self.max_rpm = max(1, int(max_requests_per_minute))
        self._buckets: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow_request(self, client_key: str, now_ts: Optional[float] = None) -> tuple[bool, int]:
        now = time.monotonic() if now_ts is None else now_ts
        cutoff = now - 60.0
        with self._lock:
            q = self._buckets[client_key]
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.max_rpm:
                retry_after = max(1, int(60.0 - (now - q[0])) + 1)
                return False, retry_after
            q.append(now)
            return True, 0


def backup_sqlite_database(
    source_db_path: Path,
    backup_dir: Path,
) -> Dict[str, Any]:
    """
    Creates an atomic, transactionally consistent SQLite online backup using SQLite's
    native `.backup()` API (never raw file copy under live writes) + SHA-256 verification.
    """
    src_path = Path(source_db_path)
    if not src_path.exists():
        raise FileNotFoundError(f"Source database '{src_path}' does not exist.")

    dest_dir = Path(backup_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%SZ")
    dest_path = dest_dir / f"{src_path.stem}_backup_{stamp}.db"

    src_conn = sqlite3.connect(str(src_path))
    dest_conn = sqlite3.connect(str(dest_path))
    try:
        src_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        src_conn.close()

    digest = hashlib.sha256(dest_path.read_bytes()).hexdigest()
    return {
        "backup_file": str(dest_path),
        "size_bytes": dest_path.stat().st_size,
        "sha256": digest,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "method": "sqlite3_online_backup_api",
    }
