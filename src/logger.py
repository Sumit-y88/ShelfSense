"""Append one structured audit record for each inventory question."""

from datetime import datetime, timezone
import json
from pathlib import Path
import threading


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_FILE_PATH = PROJECT_ROOT / "logs" / "queries.log"
ALLOWED_STATUSES = frozenset({"allowed", "blocked", "error"})
_WRITE_LOCK = threading.Lock()


def log_query(question: str, generated_sql: str, status: str, row_count: int) -> None:
    """Append timestamp, question, SQL, status, and returned row count as JSON."""
    if status not in ALLOWED_STATUSES:
        raise ValueError("status must be allowed, blocked, or error")
    if row_count < 0:
        raise ValueError("row_count cannot be negative")

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "question": question,
        "sql": generated_sql,
        "status": status,
        "row_count": row_count,
    }
    log_line = json.dumps(record, ensure_ascii=False)

    LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        with LOG_FILE_PATH.open("a", encoding="utf-8", newline="\n") as log_file:
            log_file.write(log_line + "\n")
