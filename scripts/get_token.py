"""Print an access token of a test user, for curl and for a look at the claims. Phase 5, week 19.

    make token AS=viewer          the token of viewer (analyst and auditor are the other users)
    make token AS=viewer ARGS=--claims    the claims of the token, without the signature check

The script asks the token endpoint of Keycloak (realm `lab`) with the password grant of the
client `assistant-cli`. AUTH_ISSUER (or AUTH_TOKEN_URL) names the server; the default is
http://localhost:8180/realms/lab. The three users and their passwords are in
keycloak/realm-lab.json. Use a token like this:

    curl -N -X POST localhost:8000/ask -H "Authorization: Bearer $(make -s token AS=viewer)" \\
        -H 'Content-Type: application/json' -d '{"question": "Which datasets cover water?"}'
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # for the package labkit

import jwt  # noqa: E402

from labkit.auth import TEST_USERS, password_token  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("user", choices=sorted(TEST_USERS))
    parser.add_argument("--claims", action="store_true", help="print the claims, not the token")
    args = parser.parse_args()
    try:
        token = password_token(args.user)
    except Exception as error:  # noqa: BLE001 (show the reason, not a traceback)
        sys.exit(f"No token: {error}\nIs Keycloak running (make up)?")
    if args.claims:
        print(json.dumps(jwt.decode(token, options={"verify_signature": False}), indent=2))
    else:
        print(token)


if __name__ == "__main__":
    main()
