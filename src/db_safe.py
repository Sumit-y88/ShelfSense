"""Read-only SQLite access with SQL checks for the inventory assistant."""

from pathlib import Path
import re
import sqlite3


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_DB_PATH = PROJECT_ROOT / "data" / "inventory.db"

APPROVED_TABLES = frozenset({"categories", "suppliers", "products", "sales"})
MAX_ROWS = 50
MAX_SQL_LENGTH = 10_000

FORBIDDEN_KEYWORDS = frozenset(
    {
        "ALTER",
        "ANALYZE",
        "ATTACH",
        "COMMIT",
        "CREATE",
        "DELETE",
        "DETACH",
        "DROP",
        "EXCEPT",
        "EXPLAIN",
        "INSERT",
        "INTERSECT",
        "PRAGMA",
        "REINDEX",
        "RELEASE",
        "REPLACE",
        "ROLLBACK",
        "SAVEPOINT",
        "TRANSACTION",
        "TRIGGER",
        "UNION",
        "UPDATE",
        "VACUUM",
        "WITH",
    }
)

_WORD_OR_PUNCTUATION = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+|[(),]")
_LIMIT_AT_END = re.compile(
    r"\bLIMIT\s+(\d+)(?:\s+OFFSET\s+(\d+))?\s*$", re.IGNORECASE
)
_CLAUSE_ENDINGS = {"GROUP", "HAVING", "LIMIT", "ORDER", "WHERE"}


class SQLValidationError(PermissionError):
    """Raised when SQL fails the application's allow-list checks."""


class QueryBlockedError(PermissionError):
    """Raised when SQLite's authorizer refuses a database action."""


def _mask_string_literals(sql: str) -> tuple[str, list[int]]:
    """Hide string contents from keyword checks and find SQL semicolons."""
    masked = list(sql)
    semicolons = []
    index = 0

    while index < len(sql):
        character = sql[index]

        if character == "'":
            start = index
            index += 1
            while index < len(sql):
                if sql[index] == "'":
                    # SQL represents a quote inside a string as two quotes.
                    if index + 1 < len(sql) and sql[index + 1] == "'":
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            else:
                raise SQLValidationError("A string literal is missing its closing quote.")

            for position in range(start, index):
                if masked[position] not in "\r\n":
                    masked[position] = " "
            continue

        if character == "-" and index + 1 < len(sql) and sql[index + 1] == "-":
            raise SQLValidationError("SQL comments are not allowed.")
        if character == "/" and index + 1 < len(sql) and sql[index + 1] == "*":
            raise SQLValidationError("SQL comments are not allowed.")
        if character == "*" and index + 1 < len(sql) and sql[index + 1] == "/":
            raise SQLValidationError("SQL comments are not allowed.")
        if character in {'"', "`", "[", "]"}:
            raise SQLValidationError("Quoted SQL identifiers are not allowed.")

        if character == ";":
            semicolons.append(index)
        elif not (
            character.isascii()
            and (character.isalnum() or character.isspace() or character in "_,.*()+-/%=<>!")
        ):
            raise SQLValidationError(f"Unsupported character in SQL: {character!r}.")

        index += 1

    return "".join(masked), semicolons


def _tokens_and_depths(sql_without_literals: str) -> tuple[list[str], list[int]]:
    """Return SQL words and punctuation, together with each token's depth."""
    tokens = []
    depths = []
    depth = 0

    for match in _WORD_OR_PUNCTUATION.finditer(sql_without_literals):
        token = match.group(0)
        if token == ")":
            depth -= 1
            if depth < 0:
                raise SQLValidationError("SQL has an unmatched closing parenthesis.")
            token_depth = depth
        else:
            token_depth = depth
            if token == "(":
                depth += 1

        tokens.append(token)
        depths.append(token_depth)

    if depth != 0:
        raise SQLValidationError("SQL has an unmatched opening parenthesis.")

    return tokens, depths


def _check_table_references(tokens: list[str], depths: list[int]) -> None:
    """Allow only approved table names and reject comma-based table lists."""
    table_reference_count = 0

    for index, token in enumerate(tokens):
        keyword = token.upper()
        if keyword not in {"FROM", "JOIN"}:
            continue

        table_index = index + 1
        if table_index >= len(tokens):
            raise SQLValidationError(f"{keyword} must be followed by an approved table.")

        table_name = tokens[table_index].lower()
        if table_name not in APPROVED_TABLES:
            raise SQLValidationError(f"Table {tokens[table_index]!r} is not approved.")
        table_reference_count += 1

        clause_depth = depths[index]
        for later_index in range(table_index + 1, len(tokens)):
            if depths[later_index] < clause_depth:
                break
            if depths[later_index] != clause_depth:
                continue

            later_token = tokens[later_index].upper()
            if later_token in _CLAUSE_ENDINGS:
                break
            if tokens[later_index] == ",":
                raise SQLValidationError(
                    "Comma-separated table lists are not allowed; use an explicit JOIN."
                )

    if table_reference_count == 0:
        raise SQLValidationError("The query must read from an approved inventory table.")


def validate_sql(sql: str) -> str:
    """Validate a single SELECT and enforce a maximum result size of 50 rows."""
    if not isinstance(sql, str):
        raise SQLValidationError("SQL must be provided as text.")

    candidate = sql.strip()
    if not candidate:
        raise SQLValidationError("SQL cannot be empty.")
    if len(candidate) > MAX_SQL_LENGTH:
        raise SQLValidationError("SQL is longer than the allowed maximum.")

    masked_sql, semicolons = _mask_string_literals(candidate)
    if len(semicolons) > 1:
        raise SQLValidationError("Only one SQL statement is allowed.")
    if semicolons:
        semicolon_position = semicolons[0]
        if candidate[semicolon_position + 1 :].strip():
            raise SQLValidationError("Only one SQL statement is allowed.")
        candidate = candidate[:semicolon_position].rstrip()
        masked_sql = masked_sql[:semicolon_position].rstrip()

    tokens, depths = _tokens_and_depths(masked_sql)
    if not tokens or tokens[0].upper() != "SELECT":
        raise SQLValidationError("The query must start with SELECT.")

    upper_words = {token.upper() for token in tokens if token[0].isalpha() or token[0] == "_"}
    forbidden = sorted(upper_words & FORBIDDEN_KEYWORDS)
    if forbidden:
        raise SQLValidationError(f"Forbidden SQL keyword: {forbidden[0]}.")

    _check_table_references(tokens, depths)

    limit_matches = list(_LIMIT_AT_END.finditer(masked_sql))
    if limit_matches:
        match = limit_matches[-1]
        limit_count = int(match.group(1))
        offset = match.group(2)
        if len(limit_matches) > 1:
            raise SQLValidationError("Only one LIMIT clause is allowed.")
        if limit_count > MAX_ROWS:
            suffix = f" OFFSET {offset}" if offset is not None else ""
            candidate = candidate[: match.start()].rstrip() + f" LIMIT {MAX_ROWS}{suffix}"
    elif "LIMIT" in upper_words:
        raise SQLValidationError("LIMIT must use an integer and appear at the end of the query.")
    else:
        candidate = f"{candidate} LIMIT {MAX_ROWS}"

    return candidate


def _inventory_authorizer(action: int, first_argument: str | None, second_argument: str | None,
                          database_name: str | None, source: str | None) -> int:
    """Permit only SELECT and reads from approved tables in the main database."""
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK

    if action == sqlite3.SQLITE_READ:
        table_name = (first_argument or "").lower()
        if database_name == "main" and table_name in APPROVED_TABLES:
            return sqlite3.SQLITE_OK

    return sqlite3.SQLITE_DENY


def open_readonly_connection() -> sqlite3.Connection:
    """Open only inventory.db in SQLite read-only mode and install its authorizer."""
    database_uri = f"{INVENTORY_DB_PATH.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(database_uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.set_authorizer(_inventory_authorizer)
    return connection


def run_query(sql: str) -> list[dict[str, object]]:
    """Validate and run a query, returning each result row as a dictionary."""
    safe_sql = validate_sql(sql)
    connection = open_readonly_connection()

    try:
        cursor = connection.execute(safe_sql)
        column_names = [column[0] for column in cursor.description or []]
        return [dict(zip(column_names, row)) for row in cursor.fetchall()]
    except sqlite3.DatabaseError as error:
        if "not authorized" in str(error).lower():
            raise QueryBlockedError("SQLite's authorizer blocked this query.") from error
        raise
    finally:
        connection.close()
