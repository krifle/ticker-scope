from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv


@lru_cache(maxsize=1)
def load_environment() -> None:
    load_dotenv()


def get_alpha_vantage_api_key(explicit_key: str | None = None) -> str | None:
    if explicit_key is not None and explicit_key.strip():
        return explicit_key.strip()

    load_environment()
    return os.getenv("ALPHA_VANTAGE_API_KEY")
