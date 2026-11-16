"""Week 16 checks: the two MCP servers, the safety of the SQL server, and the agent on the servers.

Run them with `make check WEEK=16`. The checks start your two servers from
assistant/servers/ (see conftest.py) with SQL_ROW_LIMIT=40 and SQL_TIMEOUT_SECONDS=2, and call
them with the MCP client of the official SDK, as the agent does. Postgres, both model services
(the test set check searches the documents) and the tables of the schema `data` (`make up`)
must be ready, and Langfuse for the trace check. The model is the fake Claude API, so the
checks are free.
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlparse

import psycopg
import pytest
import test_week14
import test_week15
from phase4_helpers import (
    answer_value,
    ask,
    has_tools,
    mcp_call,
    mcp_tools,
    returned_chunks,
    structured,
    tool_calls,
    tool_results,
)
from test_week15 import new_dataset  # noqa: F401 (a fixture of the week 15 checks)

from labkit.fake_claude import first_user_text, json_reply, text_reply, tool_reply

ROW_LIMIT = 40
TIMEOUT_SECONDS = 2
CATALOGUE_TOOLS = {"search_datasets", "get_dataset_schema", "get_dataset_stats", "register_dataset"}
SLOW_QUERY = "SELECT count(*) FROM data.gas_sales a, data.gas_sales b, data.gas_sales c"


@pytest.fixture(autouse=True)
def graph(monkeypatch):
    monkeypatch.setenv("AGENT_IMPL", "langgraph")
    monkeypatch.setenv("AGENT_PLANNER", "off")
    monkeypatch.setenv("PROVIDER", "anthropic")


@pytest.fixture(scope="module")
def data_tables():
    """Fail with a clear message when the tables of the schema `data` are not loaded."""
    from assistant.config import get_settings

    try:
        with psycopg.connect(get_settings().database_url, connect_timeout=3) as connection:
            found = connection.execute("SELECT count(*) FROM data.sources").fetchone()[0]
    except psycopg.Error as error:
        pytest.fail(f"The schema `data` is not ready. Run `make up`.\n{error}", pytrace=False)
    assert found == 8, "Run `make up`: it loads data/tables/*.csv into the schema `data`."


@pytest.fixture
def working_sql(mcp, data_tables) -> None:
    """A refusal counts only when run_sql answers a good query."""
    is_error, value = run_sql(mcp, "SELECT count(*) AS n FROM data.cement")
    if is_error or "112" not in json.dumps(value):
        pytest.fail(f"run_sql does not answer a good query (SELECT count(*) FROM data.cement): {str(value)[:300]}",
                    pytrace=False)


def run_sql(mcp, query: str, timeout: float = 60) -> tuple[bool, Any]:
    return mcp_call(mcp["sql"].url, "run_sql", {"query": query}, timeout=timeout)


def rows_of(value: Any) -> list:
    assert isinstance(value, dict) and isinstance(value.get("rows"), list), (
        f"run_sql must return a JSON object with the keys `rows` and `truncated`. It returned: {str(value)[:300]}"
    )
    return value["rows"]


# ---- step 2: two servers ------------------------------------------------------------------


def test_the_servers_have_the_tools(mcp):
    from assistant.tools import TOOLS

    sql_tools = mcp_tools(mcp["sql"].url)
    assert set(sql_tools) == {"run_sql"}, f"The SQL server has one tool, run_sql: {sorted(sql_tools)}"
    assert sql_tools["run_sql"]["input_schema"].get("required") == ["query"]
    assert len(sql_tools["run_sql"]["description"]) >= 150, (
        "Describe run_sql for the model: when to use it, the tables that it can read, and the row limit."
    )
    catalogue = mcp_tools(mcp["catalogue"].url)
    assert set(catalogue) == CATALOGUE_TOOLS, f"The catalogue server has these tools: {sorted(catalogue)}"
    assert set(catalogue["register_dataset"]["input_schema"].get("required", [])) == {
        "dataset_id", "title", "description", "owner",
    }
    for tool in TOOLS:
        if tool["name"] in catalogue:
            assert catalogue[tool["name"]]["description"] == tool["description"], (
                f"Give {tool['name']} on the server the description of assistant/tools.py, so the model sees no change."
            )


def test_the_catalogue_server_runs_the_catalogue_tools(mcp, database):
    is_error, found = mcp_call(mcp["catalogue"].url, "search_datasets", {"query": "cement production"})
    assert not is_error, found
    assert "cement-production-and-sales" in json.dumps(found), found
    is_error, stats = mcp_call(mcp["catalogue"].url, "get_dataset_stats", {"dataset_id": "cement-production-and-sales"})
    assert not is_error and "112" in json.dumps(stats), stats
    is_error, error = mcp_call(mcp["catalogue"].url, "get_dataset_schema", {"dataset_id": test_week15.BAD_ID})
    assert is_error, f"An unknown dataset ID is an error result: {error}"


# ---- step 3: a safe SQL server -------------------------------------------------------------


def test_the_sql_role_can_only_read(sql, data_tables):
    from assistant.config import get_settings

    role = urlparse(get_settings().sql_database_url).username
    rows = sql("SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls FROM pg_roles WHERE rolname = %s", (role,))
    assert rows, f"The role {role!r} of SQL_DATABASE_URL does not exist. Make it in a migration."
    assert not any(rows[0].values()), f"The role {role} must not be a superuser or create roles or databases."
    writable = sql(
        "SELECT table_schema || '.' || table_name AS name FROM information_schema.tables "
        "WHERE table_schema IN ('public', 'data') AND (has_table_privilege(%(r)s, quote_ident(table_schema) || '.' || "
        "quote_ident(table_name), 'INSERT,UPDATE,DELETE,TRUNCATE') "
        "OR pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid = (quote_ident(table_schema) || '.' || "
        "quote_ident(table_name))::regclass)) = %(r)s)",
        {"r": role},
    )
    assert writable == [], f"The role {role} can change these tables: {[row['name'] for row in writable]}"
    assert sql("SELECT has_table_privilege(%s, 'data.cement', 'SELECT') AS ok", (role,))[0]["ok"], (
        f"The role {role} must read the tables of the schema `data`."
    )


def test_run_sql_returns_the_rows_of_a_query(mcp, data_tables):
    is_error, value = run_sql(mcp, "SELECT sex_engl, nationality_engl, obs_value_obsv FROM data.population "
                                   "WHERE year_time = 2014 ORDER BY 1, 2")
    assert not is_error, value
    assert len(rows_of(value)) == 4 and value["truncated"] is False, value
    assert "7812695" in json.dumps(value), value
    is_error, value = run_sql(mcp, "SELECT id FROM datasets WHERE id = 'cement-production-and-sales'")
    assert not is_error and len(rows_of(value)) == 1, f"The catalogue tables are on the list. {value}"


def test_run_sql_connects_with_the_read_only_role(mcp, data_tables):
    from assistant.config import get_settings

    role = urlparse(get_settings().sql_database_url).username
    is_error, value = run_sql(mcp, "SELECT current_user AS name FROM data.sources LIMIT 1")
    assert not is_error, value
    assert role in json.dumps(value), f"run_sql must connect with SQL_DATABASE_URL (the role {role}): {value}"


WRITES = [
    "INSERT INTO data.cement (date, name, value) VALUES (1900, 'check', 1)",
    "UPDATE data.cement SET value = 0",
    "DELETE FROM data.cement",
    "WITH gone AS (DELETE FROM data.cement RETURNING *) SELECT count(*) FROM gone",
    "SELECT count(*) FROM data.cement; DELETE FROM data.cement",
    "SELECT 1 FROM data.cement LIMIT 1; UPDATE datasets SET title = 'changed by a check'",
    "DROP TABLE data.cement",
    "TRUNCATE data.cement",
    "CREATE TABLE data.made_by_a_check AS SELECT * FROM data.cement",
]


@pytest.mark.parametrize("statement", WRITES)
def test_run_sql_refuses_a_statement_that_writes_data(mcp, sql, working_sql, statement):
    before = sql("SELECT (SELECT count(*) FROM data.cement) AS cement, (SELECT sum(value) FROM data.cement) AS total, "
                 "(SELECT count(*) FROM datasets WHERE title = 'changed by a check') AS changed")
    is_error, value = run_sql(mcp, statement)
    after = sql("SELECT (SELECT count(*) FROM data.cement) AS cement, (SELECT sum(value) FROM data.cement) AS total, "
                "(SELECT count(*) FROM datasets WHERE title = 'changed by a check') AS changed")
    assert after == before, f"The statement changed data: {statement}"
    assert sql("SELECT to_regclass('data.made_by_a_check') IS NULL AS gone")[0]["gone"], "The statement made a table."
    assert is_error, f"Refuse the statement with an error result: {statement}\nResult: {str(value)[:300]}"


OUTSIDE = [
    "SELECT * FROM conversations",
    "SELECT * FROM audit_log",
    "SELECT count(*) FROM data.cement WHERE EXISTS (SELECT 1 FROM memories)",
    "WITH old AS (SELECT * FROM conversation_messages) SELECT count(*) FROM old",
    "SELECT tablename FROM pg_catalog.pg_tables",
    "SELECT rolname FROM pg_roles",
    "SELECT count(*) FROM data.cement WHERE EXISTS (SELECT 1 FROM pg_catalog.pg_class)",
    "WITH r AS (SELECT rolname FROM pg_roles) SELECT count(*) FROM data.cement, r",
]


@pytest.mark.parametrize("statement", OUTSIDE)
def test_run_sql_refuses_a_table_that_is_not_on_the_list(mcp, working_sql, statement):
    is_error, value = run_sql(mcp, statement)
    assert is_error, (
        "Refuse each table outside your list (the schema `data`, datasets, dataset_columns), also in a "
        f"subquery or a CTE: {statement}\nResult: {str(value)[:300]}"
    )


def test_run_sql_cuts_the_rows_at_the_limit(mcp, data_tables):
    is_error, value = run_sql(mcp, "SELECT * FROM data.gas_sales")
    assert not is_error, value
    assert len(rows_of(value)) == ROW_LIMIT, f"With SQL_ROW_LIMIT={ROW_LIMIT}, return {ROW_LIMIT} of the 1352 rows."
    assert value["truncated"] is True, "Set truncated to true when the rows were cut."
    is_error, value = run_sql(mcp, f"SELECT * FROM data.gas_sales LIMIT {ROW_LIMIT}")
    assert not is_error and value["truncated"] is False, "A result with exactly the limit is not cut."


def test_run_sql_stops_a_slow_query(mcp, sql, working_sql):
    started = time.monotonic()
    try:
        is_error, value = run_sql(mcp, SLOW_QUERY, timeout=TIMEOUT_SECONDS + 28)
    except Exception as error:  # the client gave up: the server did not stop the query
        is_error, value = False, f"{type(error).__name__}: {error}"
    finally:
        sql("SELECT pg_cancel_backend(pid) FROM pg_stat_activity WHERE query LIKE %s AND pid <> pg_backend_pid()",
            ("%data.gas_sales a, data.gas_sales b%",))
    seconds = time.monotonic() - started
    assert is_error and seconds < TIMEOUT_SECONDS + 15, (
        f"With SQL_TIMEOUT_SECONDS={TIMEOUT_SECONDS}, stop the query and return an error. The call took "
        f"{seconds:.0f} s and returned: {str(value)[:300]}"
    )


# ---- step 4: the agent on the servers ------------------------------------------------------


def test_the_agent_gets_its_tools_from_the_servers(client, fake, mcp, data_tables, database):
    fake.script(
        tool_reply(("run_sql", {"query": "SELECT * FROM data.gas_sales"})),
        json_reply({"answer": "The table has gas sales by city.", "dataset_ids": [], "tools_called": ["run_sql"]}),
    )
    result = ask(client, "Show me the gas sales of each city.")
    assert result.answer is not None, result.errors
    names = {tool.get("name") for tool in fake.requests[0].get("tools", [])}
    assert {"run_sql", *CATALOGUE_TOOLS} <= names, f"The model gets the tools of both servers: {sorted(names)}"
    assert {"search_documents", "save_memory"} <= names, "Keep search_documents and save_memory in the graph."
    output = next(r for r in tool_results(fake.requests[1]) if r["id"] == tool_calls(fake.requests[1])[0]["id"])
    assert not output["is_error"], output
    value = json.loads(output["output"])
    assert len(rows_of(value)) == ROW_LIMIT, (
        "The tool result of run_sql must come from the SQL server of the check (SQL_ROW_LIMIT=40 there). "
        "Connect the graph to MCP_SQL_URL with the LangChain MCP adapters."
    )


def test_the_catalogue_tools_run_on_the_catalogue_server(client, fake, mcp, database):
    server = mcp["catalogue"]

    def search_once():
        fake.reset()
        fake.script(
            tool_reply(("search_datasets", {"query": "cement production"})),
            json_reply({"answer": "Found it.", "dataset_ids": [], "tools_called": ["search_datasets"]}),
        )
        result = ask(client, "Which datasets are about cement?")
        found = [r for body in fake.requests for r in tool_results(body) if not r["is_error"] and "cement" in r["output"]]
        return result, found

    before = server.tool_calls()
    result, found = search_once()
    assert found, f"search_datasets gave no result. Errors: {result.errors}"
    assert server.tool_calls() == before + 1, (
        "search_datasets must run on the catalogue server (MCP_CATALOGUE_URL), not as the function in "
        "assistant/tools.py. The server logged no call."
    )
    server.stop()
    try:
        result, found = search_once()
    finally:
        server.start()
    assert not found, (
        "With the catalogue server stopped, search_datasets still gave results. The graph must call the "
        "tool on the server, not the function in assistant/tools.py."
    )
    assert result.status_code == 200 and result.done is not None


@pytest.mark.parametrize("name", [
    "test_the_conversation_continues_after_a_restart_of_the_service",
    "test_register_dataset_does_not_run_after_a_refusal",
    "test_each_tool_call_has_one_row_in_the_audit_log",
])
def test_approval_and_the_audit_log_work_with_the_tools_on_the_servers(name, request, mcp, fake, sql, new_dataset):  # noqa: F811
    """The checks of week 15 again: the approval and the audit log stay in the graph."""
    check = getattr(test_week15, name)
    fixtures = {"fake": fake, "sql": sql, "new_dataset": new_dataset, "database": None}
    for fixture in ("client", "service"):
        if fixture in check.__code__.co_varnames[: check.__code__.co_argcount]:
            fixtures[fixture] = request.getfixturevalue(fixture)
    check(**{key: fixtures[key] for key in check.__code__.co_varnames[: check.__code__.co_argcount]})


def test_the_trace_checks_of_week_8_pass_with_the_tools_on_the_servers(mcp):
    """The trace checks of week 8 again, in a new process, on the graph with the MCP tools."""
    try:
        test_week14.test_the_trace_checks_of_week_8_pass_on_the_graph()
    except AssertionError as error:
        raise AssertionError(
            f"{error}\nAn adapter tool is a LangChain tool: with the callbacks of the run, it makes its own "
            "`tool` observation in Langfuse."
        ) from None


# ---- step 5: the test set still passes -----------------------------------------------------


def oracle(cases: list[dict[str, Any]]):
    """The fake model: it searches with the question, then names the expected datasets and cites
    the expected chunk when the search returned it (else the first chunk)."""
    by_question = {case["question"]: case for case in cases}

    def reply(body: dict[str, Any]):
        case = by_question.get(first_user_text(body))
        if case is None or not has_tools(body):
            return text_reply("A summary.")
        if not tool_results(body):
            tool = "search_documents" if case.get("expected_chunk_ids") else "search_datasets"
            return tool_reply((tool, {"query": case["question"]}))
        chunks = returned_chunks(body)
        expected = [c for c in chunks if c["chunk_id"] in set(case.get("expected_chunk_ids") or [])]
        cited = [{"document_title": c["title"], "page": c["page"], "chunk_id": c["chunk_id"]} for c in (expected or chunks)[:1]]
        return structured("anthropic", lambda b: answer_value(b, "The answer of the fake model.",
                                                               case.get("expected_dataset_ids") or [], cited))(body)

    return reply


def test_the_ci_cases_of_the_test_set_still_pass_on_the_servers(fake, mcp, services, database):
    from evals.compare import run_case
    from evals.run_testset import code_pass, load_cases

    cases = [case for case in load_cases() if case.get("ci")]
    assert cases, 'Mark the CI cases in evals/testset.jsonl with "ci": true (week 11).'
    fake.always(oracle(cases))
    before = mcp["catalogue"].tool_calls()
    failed = []
    for case in cases:
        row = run_case(case, "check-week16")
        if not code_pass(case, row):
            failed.append((case["id"], row.get("errors") or row.get("dataset_ids") or row.get("citations")))
    assert not failed, f"These CI cases of the test set fail on the graph with the MCP tools: {failed}"
    datasets = sum(not case.get("expected_chunk_ids") for case in cases)
    assert mcp["catalogue"].tool_calls() >= before + datasets, "search_datasets must run on the catalogue server."
