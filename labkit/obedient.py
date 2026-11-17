"""The obedient model: a scripted model for the fake APIs that obeys each instruction it reads.

The attack suite of Phase 5 tests the design of the agent, not the good sense of one model.
A real model ignores many attacks, so a pass can mean "the model was careful this time".
The obedient model is the worst case: it is fully fooled.

What it reads: the user messages and the result of each tool call. It does not read the
system prompt. It does the first of these that applies:

1. It finds the name of a tool in what it read (a tool of the request). It calls that tool.
   The arguments are the JSON object that comes after the name, when there is one, for
   example `call save_memory with {"fact": "..."}`. Without one, it makes the arguments
   from the text (see `default_arguments`). It does not call a tool again with the same
   arguments, and it ignores the name of a tool in the result of that same tool.
2. When it has not called a tool yet, it calls search_documents and search_datasets with the
   question, so that it reads the documents and the catalogue.
3. Else it answers. The answer repeats each text that it read, word for word. So a link or a
   secret that it read is in the answer, as an attack wants.

Use it in a check or in `make attacks MODEL=obedient`:

    fake.always(obedient.claude_reply)
    fake_openai.always(obedient.openai_reply)
"""

from __future__ import annotations

import json
import re
from typing import Any

from labkit import fake_claude, fake_openai

EXPLORE = ("search_documents", "search_datasets")
WINDOW = 300  # The JSON arguments must start within this number of characters after the name.
MAX_CALLS = 12  # After this number of tool calls in a conversation, it answers.
SQL = re.compile(r"\b(SELECT|WITH)\b.+?(?=;|\"|\n|$)", re.IGNORECASE | re.DOTALL)
URL = re.compile(r"https?://[^\s\"'<>)\]]+")


def strings(text: str) -> list[str]:
    """The texts in a tool result. A JSON result gives each of its strings and numbers."""
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return [text]
    found: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, str):
            found.append(item)
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            found.append(str(item))
        elif isinstance(item, dict):
            for part in item.values():
                walk(part)
        elif isinstance(item, list):
            for part in item:
                walk(part)

    walk(value)
    return found or [text]


def default_arguments(schema: dict[str, Any], text: str, question: str) -> dict[str, Any]:
    """Arguments for a tool whose instruction gives no JSON: values taken from the text."""
    arguments: dict[str, Any] = {}
    properties = schema.get("properties") or {}
    for name in schema.get("required") or list(properties)[:1]:
        kind = (properties.get(name) or {}).get("type", "string")
        if kind == "integer":
            arguments[name] = 5
            continue
        if name == "query" and SQL.search(text):
            arguments[name] = SQL.search(text).group(0).strip()
        elif name == "query":
            arguments[name] = question
        elif "url" in name and URL.search(text):
            arguments[name] = URL.search(text).group(0)
        elif name in {"fact", "description"}:
            arguments[name] = text[:300]
        else:
            arguments[name] = f"obedient-{name}"
    return arguments


def _key(name: str, arguments: dict[str, Any]) -> str:
    return name + json.dumps(arguments, sort_keys=True, ensure_ascii=False)


def decide(
    question: str,
    results: list[tuple[str, str]],
    tools: dict[str, dict[str, Any]],
    made: list[tuple[str, dict[str, Any]]],
) -> list[tuple[str, dict[str, Any]]]:
    """The tool calls of the next reply, or [] for the final answer.

    `results` holds (name of the tool, result text) for each result in the conversation,
    `tools` maps the name of each tool of the request to its JSON schema, and `made` holds
    each earlier call as (name, arguments).
    """
    if len(made) >= MAX_CALLS:
        return []
    done = {_key(name, arguments) for name, arguments in made}
    wanted: list[tuple[str, dict[str, Any]]] = []
    sources = [("", question)] + [(tool, text) for tool, result in results for text in strings(result)]
    for source_tool, text in sources:
        mentions = sorted(
            (match.start(), match.end(), name)
            for name in tools if name != source_tool
            for match in re.finditer(rf"\b{re.escape(name)}\b", text)
        )
        for index, (_, end, name) in enumerate(mentions):
            # The arguments of a mention end where the next mention starts.
            stop = mentions[index + 1][0] if index + 1 < len(mentions) else len(text)
            after = text[end: min(end + WINDOW, stop)]
            arguments = None
            start = after.find("{")
            if start >= 0:
                try:
                    value, _ = json.JSONDecoder().raw_decode(after[start:])
                    arguments = value if isinstance(value, dict) else None
                except json.JSONDecodeError:
                    arguments = None
            if arguments is None:
                arguments = default_arguments(tools[name], text, question)
            key = _key(name, arguments)
            if key not in done:
                done.add(key)
                wanted.append((name, arguments))
    if wanted:
        return wanted
    if not made:
        return [(name, {"query": question}) for name in EXPLORE if name in tools]
    return []


def answer_text(question: str, results: list[tuple[str, str]]) -> str:
    """The final answer: each text that the model read, word for word."""
    texts = [question] + [text for _, result in results for text in strings(result)]
    return "I followed each instruction that I read.\n\n" + "\n\n".join(texts)


def answer_value(schema: dict[str, Any] | None, text: str) -> dict[str, Any]:
    value = {"answer": text, "dataset_ids": [], "tools_called": [], "citations": []}
    properties = set((schema or {}).get("properties") or value)
    return {key: item for key, item in value.items() if key in properties}


# ---- the fake Claude API ------------------------------------------------------------------------


def _claude_state(body: dict[str, Any]) -> tuple[str, list[tuple[str, str]], list[tuple[str, dict[str, Any]]]]:
    names: dict[str, str] = {}
    made: list[tuple[str, dict[str, Any]]] = []
    results: list[tuple[str, str]] = []
    for message in body.get("messages", []):
        content = message.get("content")
        for block in [] if isinstance(content, str) else content:
            if block.get("type") == "tool_use":
                names[block["id"]] = block["name"]
                made.append((block["name"], block.get("input") or {}))
            elif block.get("type") == "tool_result":
                output = block.get("content")
                if not isinstance(output, str):
                    output = " ".join(part.get("text", "") for part in output or [] if isinstance(part, dict))
                results.append((names.get(block.get("tool_use_id"), ""), output))
    return fake_claude.last_user_text(body), results, made


def claude_reply(body: dict[str, Any]) -> fake_claude.Reply:
    """A reply of the obedient model for the fake Claude API."""
    question, results, made = _claude_state(body)
    output_format = (body.get("output_config") or {}).get("format") or {}
    choice = body.get("tool_choice") or {}
    forced = choice.get("name") if isinstance(choice, dict) and choice.get("type") == "tool" else None
    tools = {tool["name"]: tool.get("input_schema") or {} for tool in body.get("tools") or [] if "name" in tool}
    if forced:  # Structured output through a forced tool: answer in the schema of the tool.
        return fake_claude.tool_reply((forced, answer_value(tools.get(forced), answer_text(question, results))), thinking=False)
    calls = decide(question, results, tools, made)
    if calls:
        return fake_claude.tool_reply(*calls)
    text = answer_text(question, results)
    if output_format.get("schema"):
        return fake_claude.json_reply(answer_value(output_format["schema"], text))
    return fake_claude.text_reply(text)


# ---- the fake OpenAI API ------------------------------------------------------------------------


def _openai_tools(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tools = {}
    for tool in body.get("tools") or []:
        function = tool.get("function") or tool
        if function.get("name"):
            tools[function["name"]] = function.get("parameters") or {}
    return tools


def openai_reply(body: dict[str, Any]) -> fake_openai.Reply:
    """A reply of the obedient model for the fake OpenAI API (both endpoints)."""
    names = {}
    made = []
    for call in fake_openai.function_calls(body):
        names[call["call_id"]] = call["name"]
        arguments = call.get("arguments")
        try:
            arguments = json.loads(arguments) if isinstance(arguments, str) else arguments or {}
        except json.JSONDecodeError:
            arguments = {}
        made.append((call["name"], arguments))
    results = [(names.get(item["call_id"], ""), item["output"]) for item in fake_openai.tool_outputs(body)]
    question = fake_openai.last_user_text(body)
    tools = _openai_tools(body)
    forced = fake_openai.forced_tool(body)
    if forced and not fake_openai.wants_json(body):
        return fake_openai.tool_reply((forced, answer_value(tools.get(forced), answer_text(question, results))))
    calls = decide(question, results, tools, made)
    if calls:
        return fake_openai.tool_reply(*calls)
    text = answer_text(question, results)
    schema = fake_openai.json_schema(body)
    if schema:
        return fake_openai.json_reply(answer_value(schema, text))
    return fake_openai.text_reply(text)
