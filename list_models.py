"""
List the model IDs available on the Duke AI Gateway.

The model names hardcoded in the dropdown in app.py are a starting point, not
a guarantee — gateways add, rename, and retire models. Run this to see what
your key can actually reach:

    uv run list_models.py
    uv run list_models.py claude       # filter by substring
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

load_dotenv()

DEFAULT_BASE_URL = "https://litellm.oit.duke.edu/v1"


def main() -> int:
    api_key = os.environ.get("DUKE_API_KEY", "").strip()
    if not api_key:
        print(
            "DUKE_API_KEY is not set. Copy .env.example to .env and fill it in, "
            "or export it in your shell.",
            file=sys.stderr,
        )
        return 1

    base_url = os.environ.get("DUKE_BASE_URL", "").strip() or DEFAULT_BASE_URL
    needle = sys.argv[1].lower() if len(sys.argv) > 1 else None

    client = OpenAI(api_key=api_key, base_url=base_url)

    try:
        models = client.models.list()
    except OpenAIError as exc:
        print(f"Could not query {base_url}/models: {exc}", file=sys.stderr)
        return 1

    ids = sorted(model.id for model in models.data)
    if needle:
        ids = [model_id for model_id in ids if needle in model_id.lower()]

    if not ids:
        print("No models matched." if needle else "The gateway returned no models.")
        return 0

    print(f"{len(ids)} model(s) available at {base_url}:\n")
    for model_id in ids:
        print(f"  {model_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
