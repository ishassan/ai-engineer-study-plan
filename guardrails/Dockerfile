# The NeMo Guardrails server of Phase 5, week 20: the jailbreak heuristics and the PII detection
# with Presidio, on the CPU, with no model service and no key.
#
# NVIDIA publishes no image of this server: the page "Deploy the NeMo Guardrails Library with
# Docker" builds one from the source repository. This file builds it from the pinned package of
# PyPI instead. Each package has a build for linux/arm64 (Apple Silicon) and linux/amd64.
#
# - torch comes from the CPU index of PyTorch. The jailbreak heuristics compute the perplexity
#   of the input with the model gpt2-large (about 3.2 GB), which the first start downloads into
#   the volume of /models (HF_HOME).
# - Presidio needs the spaCy model en_core_web_lg. NeMo Guardrails loads only this English model.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models

RUN uv venv /opt/venv
RUN uv pip install --no-cache "torch==2.15.0" --index-url https://download.pytorch.org/whl/cpu
RUN uv pip install --no-cache \
    "nemoguardrails[server,sdd]==0.24.1" \
    "transformers==5.23.0" \
    "en_core_web_lg @ https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl"

COPY warm_up.py /warm_up.py
EXPOSE 8000
# The configurations come from the folder config/, which Compose mounts on /config.
CMD ["sh", "-c", "python /warm_up.py && exec nemoguardrails server --config=/config --default-config-id=assistant --port=8000"]
