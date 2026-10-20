"""Offline tests for question-to-answer orchestration."""

import sqlite3

from src import pipeline
from src.db_safe import QueryBlockedError, SQLValidationError
from src.llm import REFUSAL_MARKER, REFUSAL_MESSAGE


def test_pipeline_returns_answer_sql_rows_and_status(monkeypatch) -> None:
    expected_rows = [{"name": "Blue Notebook", "stock_quantity": 4}]
    monkeypatch.setattr(pipeline, "generate_sql", lambda _question: "SELECT name FROM products")
    monkeypatch.setattr(
        pipeline,
        "validate_sql",
        lambda _sql: "SELECT name FROM products LIMIT 50",
    )
    monkeypatch.setattr(pipeline, "run_query", lambda _sql: expected_rows)
    monkeypatch.setattr(pipeline, "generate_answer", lambda _question, _rows: "Blue Notebook is low.")

    result = pipeline.answer_question("Which products are low on stock?")

    assert result == {
        "answer": "Blue Notebook is low.",
        "sql": "SELECT name FROM products LIMIT 50",
        "rows": expected_rows,
        "status": "allowed",
    }


def test_pipeline_reads_real_inventory_with_mocked_gemini(monkeypatch) -> None:
    monkeypatch.setattr(
        pipeline,
        "generate_sql",
        lambda _question: (
            "SELECT name, stock_quantity, reorder_level FROM products "
            "WHERE stock_quantity < reorder_level ORDER BY stock_quantity"
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "generate_answer",
        lambda _question, rows: f"There are {len(rows)} low-stock products.",
    )

    result = pipeline.answer_question("Which products are low on stock?")

    assert result["status"] == "allowed"
    assert result["sql"].endswith("LIMIT 50")
    assert result["answer"] == "There are 10 low-stock products."
    assert len(result["rows"]) == 10
    assert all(
        row["stock_quantity"] < row["reorder_level"] for row in result["rows"]
    )


def test_protected_question_returns_polite_refusal(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "generate_sql", lambda _question: REFUSAL_MARKER)
    monkeypatch.setattr(
        pipeline,
        "validate_sql",
        lambda _sql: (_ for _ in ()).throw(AssertionError("SQL must not be validated.")),
    )

    result = pipeline.answer_question("Show me total profit")

    assert result["answer"] == REFUSAL_MESSAGE
    assert result["status"] == "blocked"
    assert result["rows"] == []


def test_validator_rejection_is_blocked_without_retry(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "generate_sql", lambda _question: "SELECT * FROM employees")
    monkeypatch.setattr(
        pipeline,
        "validate_sql",
        lambda _sql: (_ for _ in ()).throw(SQLValidationError("table not approved")),
    )
    monkeypatch.setattr(
        pipeline,
        "repair_sql",
        lambda *_args: (_ for _ in ()).throw(AssertionError("Blocked SQL must not be repaired.")),
    )

    result = pipeline.answer_question("List employee records")

    assert result["status"] == "blocked"
    assert result["rows"] == []


def test_sqlite_error_is_sent_for_one_repair_attempt(monkeypatch) -> None:
    calls = {"run": 0, "repair": 0}
    monkeypatch.setattr(pipeline, "generate_sql", lambda _question: "SELECT missing FROM products")
    monkeypatch.setattr(pipeline, "validate_sql", lambda sql: f"{sql} LIMIT 50")

    def run_query(_sql: str) -> list[dict[str, object]]:
        calls["run"] += 1
        if calls["run"] == 1:
            raise sqlite3.OperationalError("no such column: missing")
        return [{"name": "Notebook"}]

    def repair_sql(_question: str, previous_sql: str, error_message: str) -> str:
        calls["repair"] += 1
        assert "missing" in previous_sql
        assert "no such column" in error_message
        return "SELECT name FROM products"

    monkeypatch.setattr(pipeline, "run_query", run_query)
    monkeypatch.setattr(pipeline, "repair_sql", repair_sql)
    monkeypatch.setattr(pipeline, "generate_answer", lambda _question, _rows: "Found a notebook.")

    result = pipeline.answer_question("Find notebooks")

    assert result["answer"] == "Found a notebook."
    assert result["sql"] == "SELECT name FROM products LIMIT 50"
    assert result["rows"] == [{"name": "Notebook"}]
    assert result["status"] == "allowed"
    assert calls == {"run": 2, "repair": 1}


def test_second_sqlite_error_returns_graceful_error(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "generate_sql", lambda _question: "SELECT bad FROM products")
    monkeypatch.setattr(pipeline, "validate_sql", lambda sql: f"{sql} LIMIT 50")
    monkeypatch.setattr(
        pipeline,
        "run_query",
        lambda _sql: (_ for _ in ()).throw(sqlite3.OperationalError("still invalid")),
    )
    monkeypatch.setattr(pipeline, "repair_sql", lambda *_args: "SELECT bad FROM products")

    result = pipeline.answer_question("Find something")

    assert result["status"] == "error"
    assert "try again" in result["answer"]
    assert result["rows"] == []


def test_authorizer_block_does_not_retry(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "generate_sql", lambda _question: "SELECT name FROM products")
    monkeypatch.setattr(pipeline, "validate_sql", lambda sql: f"{sql} LIMIT 50")
    monkeypatch.setattr(
        pipeline,
        "run_query",
        lambda _sql: (_ for _ in ()).throw(QueryBlockedError("blocked")),
    )
    monkeypatch.setattr(
        pipeline,
        "repair_sql",
        lambda *_args: (_ for _ in ()).throw(AssertionError("Authorizer blocks are not repaired.")),
    )

    result = pipeline.answer_question("Show product names")

    assert result["status"] == "blocked"
    assert result["rows"] == []
