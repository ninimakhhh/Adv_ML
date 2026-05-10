from functools import lru_cache

from openai import OpenAI

from shared.config import DEEPSEEK_API_KEY


@lru_cache(maxsize=1)
def get_deepseek_client() -> OpenAI:
    if DEEPSEEK_API_KEY is None:
        raise RuntimeError(
            "DEEPSEEK_API_KEY not set. "
            "Please add it to your .env file: DEEPSEEK_API_KEY=sk-..."
        )
    return OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com"
    )


# Alias for backwards compatibility
get_anthropic_client = get_deepseek_client
