from __future__ import annotations

from ..typing import AsyncResult, Messages
from .needs_auth.OpenaiAPI import OpenaiAPI

class Jmuz(OpenaiAPI):
    label = "Jmuz"
    url = "https://discord.gg/Ew6JzjA2NR"
    login_url = None
    api_base = "https://jmuz.me/gpt/api/v2"
    api_key = "prod"

    working = True
    needs_auth = False
    supports_stream = True
    supports_system_message = False

    default_model = "gpt-4o"
    model_aliases = {
        "gemini": "gemini-exp",
        "gemini-1.5-pro": "gemini-pro",
        "gemini-1.5-flash": "gemini-thinking",
        "deepseek-chat": "deepseek-v3",
        "qwq-32b": "qwq-32b-preview",
    }

    @classmethod
    def get_models(cls, **kwargs):
        if not cls.models:
            cls.models = super().get_models(api_key=cls.api_key, api_base=cls.api_base)
        return cls.models

    @classmethod
    async def create_async_generator(
            cls,
            model: str,
            messages: Messages,
            stream: bool = False,
            api_key: str = None,
            api_base: str = None,
            **kwargs
    ) -> AsyncResult:
        model = cls.get_model(model)
        headers = {
            "Authorization": f"Bearer {cls.api_key}",
            "Content-Type": "application/json",
            "accept": "*/*",
            "cache-control": "no-cache",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        }
        started = False
        buffer = ""
        async for chunk in super().create_async_generator(
            model=model,
            messages=messages,
            api_base=cls.api_base,
            api_key=cls.api_key,
            stream=cls.supports_stream,
            headers=headers,
            **kwargs
        ):
            if isinstance(chunk, str):
                buffer += chunk
                if "Join for free".startswith(buffer) or buffer.startswith("Join for free"):
                    if buffer.endswith("\n"):
                        buffer = ""
                    continue
                if "https://discord.gg/".startswith(buffer) or "https://discord.gg/" in buffer:
                    if "..." in buffer:
                        buffer = ""
                    continue
                if "o1-preview".startswith(buffer) or buffer.startswith("o1-preview"):
                    if "\n" in buffer:
                        buffer = ""
                    continue
                if not started:
                    buffer = buffer.lstrip()
                if buffer:
                    started = True
                    yield buffer
                    buffer = ""
            else:
                yield chunk
