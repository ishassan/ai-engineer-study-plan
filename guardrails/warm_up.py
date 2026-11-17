"""Load the models of the rails before the server starts, so that the first check is fast.

The first start downloads gpt2-large into /models (the volume of the service). Each later start
reads it from there.
"""

from nemoguardrails.library.jailbreak_detection.heuristics import checks  # noqa: F401 (loads gpt2-large)
from nemoguardrails.library.sensitive_data_detection.actions import _get_analyzer

_get_analyzer()
print("The jailbreak model and the Presidio analyzer are ready.", flush=True)
