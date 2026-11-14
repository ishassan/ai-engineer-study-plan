"""Send one question to the running API and print the stream.

    make ask Q="Which datasets are about crude oil?"

The script prints the text as it arrives, then each other event on its own line.
"""

from __future__ import annotations

import json
import sys

import httpx

URL = "http://localhost:8000/ask"


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        sys.exit('Give a question: make ask Q="Which datasets are about crude oil?"')
    event = "message"
    in_text = False
    try:
        with httpx.stream("POST", URL, json={"question": sys.argv[1]}, timeout=120) as response:
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
    except httpx.ConnectError:
        sys.exit("The API does not answer on localhost:8000. Run `make up` first.")


if __name__ == "__main__":
    main()
