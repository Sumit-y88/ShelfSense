"""Connect question handling, SQL checks, database reads, and answers."""

import logging
import sqlite3

from src.db_safe import QueryBlockedError, SQLValidationError, run_query, validate_sql
from src.logger import log_query
from src.llm import (
    REFUSAL_MARKER,
    REFUSAL_MESSAGE,
    generate_answer,
    generate_sql,
    repair_sql,
)


_SAFE_QUERY_MESSAGE = (
    "I couldn't safely run a query for that request. "
    "Please ask about products, stock, suppliers, or sales."
)
_ERROR_MESSAGE = (
    "I couldn't complete that inventory request. Check the Streamlit terminal "
    "for error details and verify your Gemini settings, then try again."
)
_LOGGER = logging.getLogger(__name__)


def _result(
    answer: str,
    sql: str = "",
    rows: list[dict[str, object]] | None = None,
    status: str = "error",
) -> dict[str, object]:
    """Build one consistent result object for the UI and logger."""
    return {
        "answer": answer,
        "sql": sql,
        "rows": rows if rows is not None else [],
        "status": status,
    }


def _answer_question(question: str) -> dict[str, object]:
    """Run the inventory question pipeline before writing its audit record."""
    if not isinstance(question, str) or not question.strip():
        return _result("Please enter a question.", status="blocked")

    try:
        sql = generate_sql(question)
    except Exception as error:
        _LOGGER.error("Gemini SQL generation failed (%s).", type(error).__name__)
        return _result(_ERROR_MESSAGE, status="error")

    if not isinstance(sql, str):
        return _result(_ERROR_MESSAGE, status="error")
    if sql.strip() == REFUSAL_MARKER:
        return _result(REFUSAL_MESSAGE, sql=sql, status="blocked")

    try:
        safe_sql = validate_sql(sql)
    except SQLValidationError:
        return _result(_SAFE_QUERY_MESSAGE, sql=sql, status="blocked")

    sql = safe_sql
    try:
        rows = run_query(sql)
    except QueryBlockedError:
        return _result(_SAFE_QUERY_MESSAGE, sql=sql, status="blocked")
    except sqlite3.Error as first_error:
        # Only retry a SQLite execution error. SQL rejected by the validator
        # or authorizer remains blocked and is never sent back for repair.
        try:
            repaired_sql = repair_sql(question, sql, str(first_error))
            if repaired_sql.strip() == REFUSAL_MARKER:
                return _result(REFUSAL_MESSAGE, sql=repaired_sql, status="blocked")

            sql = repaired_sql
            sql = validate_sql(repaired_sql)
            rows = run_query(sql)
        except (SQLValidationError, QueryBlockedError):
            return _result(_SAFE_QUERY_MESSAGE, sql=sql, status="blocked")
        except Exception as error:
            _LOGGER.error("SQL repair or execution failed (%s).", type(error).__name__)
            return _result(_ERROR_MESSAGE, sql=sql, status="error")
    except SQLValidationError:
        return _result(_SAFE_QUERY_MESSAGE, sql=sql, status="blocked")
    except Exception as error:
        _LOGGER.error("Inventory query failed (%s).", type(error).__name__)
        return _result(_ERROR_MESSAGE, sql=sql, status="error")

    try:
        answer = generate_answer(question, rows)
    except Exception as error:
        _LOGGER.error("Gemini answer generation failed (%s).", type(error).__name__)
        return _result(_ERROR_MESSAGE, sql=sql, rows=rows, status="error")
    if not isinstance(answer, str) or not answer.strip():
        return _result(_ERROR_MESSAGE, sql=sql, rows=rows, status="error")

    return _result(answer, sql=sql, rows=rows, status="allowed")


def answer_question(question: str) -> dict[str, object]:
    """Run the pipeline, record the outcome, and return it to the caller."""
    try:
        result = _answer_question(question)
    except Exception as error:
        _LOGGER.error("Unexpected inventory pipeline failure (%s).", type(error).__name__)
        result = _result(_ERROR_MESSAGE, status="error")

    sql = str(result.get("sql", ""))
    rows = result.get("rows", [])
    row_count = len(rows) if isinstance(rows, list) else 0

    try:
        log_query(
            question=str(question or ""),
            generated_sql=sql,
            status=str(result.get("status", "error")),
            row_count=row_count,
        )
    except Exception:
        _LOGGER.error("Could not write the query audit log.")
        return _result(
            "I couldn't save the query log, so please try again later.",
            sql=sql,
            rows=rows if isinstance(rows, list) else [],
            status="error",
        )

    return result
