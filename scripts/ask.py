"""Send one question to the running API and print the stream.

    make ask Q="Which datasets are about crude oil?"
    make ask AS=viewer Q="..."    from Phase 5, week 19: ask with the token of a test user

The script prints the text as it arrives, then each other event on its own line.

From Phase 7, week 26: when the `done` event has a `trace_id` and the script runs in a terminal,
it asks whether the answer was good or bad, and sends the rating with an optional comment to
POST /feedback.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

URL = "http://localhost:8000/ask"
FEEDBACK_URL = "http://localhost:8000/feedback"


def token_headers(user: str) -> dict[str, str]:
    """Get a token for a test user from the authorization server (Phase 5)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # for the package labkit
    from labkit.auth import password_token

    try:
        return {"Authorization": f"Bearer {password_token(user)}"}
    except Exception as error:  # noqa: BLE001 (show the reason, not a traceback)
        sys.exit(f"No token for {user}: {error}\nIs Keycloak running (make up)?")


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        sys.exit('Give a question: make ask Q="Which datasets are about crude oil?"')
    headers = token_headers(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else {}
    event = "message"
    in_text = False
    trace_id = None
    try:
        with httpx.stream("POST", URL, json={"question": sys.argv[1]}, headers=headers, timeout=120) as response:
            if response.status_code == 401:
                sys.exit('The API asks for an access token (HTTP 401). Give a test user: make ask AS=viewer Q="..."')
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith("event:"):
                    event = line[len("event:") :].strip()
                elif line.startswith("data:"):
                    data = json.loads(line[len("data:") :])
                    if event == "text":
                        print(data["text"], end="", flush=True)
                        in_text = True
                        continue
                    if in_text:
                        print()
                        in_text = False
                    print(f"[{event}] {json.dumps(data, ensure_ascii=False)}")
                    if event == "done":
                        trace_id = data.get("trace_id")
    except httpx.ConnectError:
        sys.exit("The API does not answer on localhost:8000. Run `make up` first.")
    if trace_id and sys.stdin.isatty():
        ask_feedback(trace_id, headers)


def ask_feedback(trace_id: str, headers: dict[str, str]) -> None:
    """Week 26: the feedback control of the answer. Enter skips it."""
    rating = input("Was the answer good? [g]ood, [b]ad, Enter to skip: ").strip().lower()
    if rating not in {"g", "b", "good", "bad"}:
        return
    comment = input("Comment (Enter for none): ").strip()
    body = {"trace_id": trace_id, "rating": "good" if rating.startswith("g") else "bad"}
    if comment:
        body["comment"] = comment
    response = httpx.post(FEEDBACK_URL, json=body, headers=headers, timeout=30)
    if response.is_success:
        print("Feedback stored.")
    else:
        print(f"The API refused the feedback: HTTP {response.status_code} {response.text}")


if __name__ == "__main__":
    main()
