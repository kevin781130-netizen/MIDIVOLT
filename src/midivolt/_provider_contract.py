"""Strict, dependency-free completion gate for MIDIVOLT AI response messages."""
from __future__ import annotations


class ProviderProtocolError(RuntimeError):
    """The provider did not return one complete, usable text message."""


def decode_response_text(provider: str, response: dict) -> str:
    """Reject nonterminal, refused, empty or malformed provider messages."""
    if provider not in ("openai", "ollama"):
        raise ProviderProtocolError("Unknown AI provider protocol")
    try:
        if provider == "openai":
            choice = response["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ProviderProtocolError("AI provider response was incomplete or filtered")
            message = choice["message"]
            if message.get("refusal"):
                raise ProviderProtocolError("AI provider refused this generation")
            content = message["content"]
        else:
            if response.get("done") is not True:
                raise ProviderProtocolError("Local AI response was not complete")
            content = response["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ProviderProtocolError("AI provider returned no text content")
        return content
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ProviderProtocolError("AI provider response is missing the expected message") from exc
