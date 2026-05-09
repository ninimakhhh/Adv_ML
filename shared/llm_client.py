from functools import lru_cache

from anthropic import Anthropic

from shared.config import ANTHROPIC_API_KEY


@lru_cache(maxsize=1)
def get_anthropic_client() -> Anthropic:
    return Anthropic(api_key=ANTHROPIC_API_KEY)
