"""Tests for structured query logging."""

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from src import logger


@pytest.fixture
def log_path(monkeypatch):
    path = Path(__file__).parent / f".queries-{uuid4().hex}.log"
    monkeypatch.setattr(logger, "LOG_FILE_PATH", path)
    yield path
    path.unlink(missing_ok=True)


def test_log_query_appends_a_record(log_path) -> None:

    logger.log_query(
        "Which products are low on stock?",
        "SELECT name FROM products LIMIT 50",
        "allowed",
        3,
    )

    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    parsed_time = datetime.fromisoformat(record["timestamp"])
    assert parsed_time.utcoffset().total_seconds() == 0
    assert record["question"] == "Which products are low on stock?"
    assert record["sql"] == "SELECT name FROM products LIMIT 50"
    assert record["status"] == "allowed"
    assert record["row_count"] == 3


@pytest.mark.parametrize("status", ["allowed", "blocked", "error"])
def test_log_query_accepts_pipeline_statuses(log_path, status) -> None:
    logger.log_query("Question", "", status, 0)

    assert json.loads(log_path.read_text(encoding="utf-8"))["status"] == status


def test_log_query_rejects_unknown_status(log_path) -> None:
    with pytest.raises(ValueError, match="status"):
        logger.log_query("Question", "", "success", 0)


def test_pipeline_records_blocked_requests(monkeypatch) -> None:
    from src import pipeline

    captured = []
    monkeypatch.setattr(pipeline, "generate_sql", lambda _question: "REFUSE_FINANCIAL_OR_HR")
    monkeypatch.setattr(pipeline, "log_query", lambda **record: captured.append(record))

    result = pipeline.answer_question("Show me total profit")

    assert result["status"] == "blocked"
    assert captured == [
        {
            "question": "Show me total profit",
            "generated_sql": "REFUSE_FINANCIAL_OR_HR",
            "status": "blocked",
            "row_count": 0,
        }
    ]
