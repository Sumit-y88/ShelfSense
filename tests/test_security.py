"""Security checks for the read-only inventory query layer."""

import sqlite3

import pytest

from src.db_safe import (
    QueryBlockedError,
    SQLValidationError,
    open_readonly_connection,
    run_query,
    validate_sql,
)


def test_valid_select_is_allowed_and_limited() -> None:
    sql = validate_sql("SELECT name FROM products")

    assert sql == "SELECT name FROM products LIMIT 50"
    assert len(run_query("SELECT name FROM products")) == 50


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE products",
        "DELETE FROM products",
        "UPDATE products SET name = 'changed'",
        "INSERT INTO products (name) VALUES ('new')",
    ],
)
def test_write_or_ddl_statements_are_blocked(sql: str) -> None:
    with pytest.raises(SQLValidationError):
        validate_sql(sql)


def test_multiple_statements_are_blocked() -> None:
    sql = "SELECT name FROM products; SELECT name FROM suppliers"

    with pytest.raises(SQLValidationError, match="one SQL statement"):
        validate_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "ATTACH DATABASE 'other.db' AS other",
        "SELECT name FROM products; PRAGMA table_info(products)",
        "PRAGMA table_info(products)",
    ],
)
def test_attach_and_pragma_statements_are_blocked(sql: str) -> None:
    with pytest.raises(SQLValidationError):
        validate_sql(sql)


@pytest.mark.parametrize(
    "table_name",
    ["employees", "product_costs", "profit_reports"],
)
def test_private_tables_are_blocked(table_name: str) -> None:
    with pytest.raises(SQLValidationError, match="not approved"):
        validate_sql(f"SELECT * FROM {table_name}")


def test_union_tricks_are_blocked() -> None:
    sql = "SELECT name FROM products UNION SELECT name FROM employees"

    with pytest.raises(SQLValidationError, match="UNION"):
        validate_sql(sql)


def test_limit_is_added_or_capped_at_fifty() -> None:
    assert validate_sql("SELECT name FROM products").endswith("LIMIT 50")
    assert validate_sql("SELECT name FROM products LIMIT 100").endswith("LIMIT 50")
    assert validate_sql("SELECT name FROM products LIMIT 10").endswith("LIMIT 10")


def test_authorizer_blocks_pragmas_and_attach_directly() -> None:
    connection = open_readonly_connection()
    try:
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute("PRAGMA table_info(products)")
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute("ATTACH DATABASE ':memory:' AS other")
    finally:
        connection.close()


def test_authorizer_blocks_reads_from_unapproved_tables() -> None:
    connection = open_readonly_connection()
    try:
        with pytest.raises(sqlite3.DatabaseError):
            # sqlite_master exists in this database, but isn't on the allow list.
            connection.execute("SELECT name FROM sqlite_master")
    finally:
        connection.close()


def test_authorizer_blocks_sql_functions() -> None:
    with pytest.raises(QueryBlockedError):
        # SQLITE_FUNCTION is outside the SELECT/READ allow list.
        run_query("SELECT COUNT(*) FROM products")
