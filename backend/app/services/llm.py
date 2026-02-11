from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

try:
    # OpenAI python lib 
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore


# ----------------------------
# Public types
# ----------------------------

logger = logging.getLogger(__name__)

@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


class LLMError(RuntimeError):
    """Raised when the LLM provider returns an error or is misconfigured."""


# ----------------------------
# Config helpers
# ----------------------------

def _get_env(name: str, default: Optional[str] = None) -> str:
    val = os.getenv(name, default)
    if val is None:
        raise LLMError(f"Missing required environment variable: {name}")
    return val


def _to_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise LLMError(f"Invalid int for env var {name}: {raw}") from e


def _to_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as e:
        raise LLMError(f"Invalid float for env var {name}: {raw}") from e


# ----------------------------
# Main client
# ----------------------------

class LLMClient:
    """
    Pluggable LLM client.

    Providers:
      - groq: OpenAI-compatible API at https://api.groq.com/openai/v1
      - openai: OpenAI official API
      - ollama: local Ollama server at http://localhost:11434
      - mock: returns deterministic placeholder output for local dev
    """

    def __init__(self) -> None:
        self.provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
        self.timeout_s = _to_int("LLM_TIMEOUT_SECONDS", 30)
        self.max_tokens = _to_int("LLM_MAX_TOKENS", 600)
        self.temperature = _to_float("LLM_TEMPERATURE", 0.1)

        if self.provider == "groq":
            if OpenAI is None:
                raise LLMError(
                    "openai package is not installed. Add `openai>=1.40.0` to requirements.txt."
                )
            api_key = _get_env("GROQ_API_KEY")
            base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
            self.model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

            # Use httpx timeout for safety
            http_client = httpx.Client(timeout=self.timeout_s)

            self._client = OpenAI(api_key=api_key, base_url=base_url, http_client=http_client)

        elif self.provider == "openai":
            if OpenAI is None:
                raise LLMError(
                    "openai package is not installed. Add `openai>=1.40.0` to requirements.txt."
                )
            api_key = _get_env("OPENAI_API_KEY")
            base_url = os.getenv("OPENAI_BASE_URL")
            self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            http_client = httpx.Client(timeout=self.timeout_s)
            if base_url:
                self._client = OpenAI(api_key=api_key, base_url=base_url, http_client=http_client)
            else:
                self._client = OpenAI(api_key=api_key, http_client=http_client)

        elif self.provider == "ollama":
            self.model = os.getenv("OLLAMA_MODEL", "llama3.1:latest")
            self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
            self._client = None

        elif self.provider == "mock":
            self.model = "mock"
            self._client = None

        else:
            raise LLMError(f"Unsupported LLM_PROVIDER: {self.provider}")
        logger.info("LLM initialized; provider=%s model=%s", self.provider, self.model)

    def chat(
        self,
        messages: List[LLMMessage],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Basic chat completion. Returns assistant text.
        """
        if self.provider == "mock":
            return self._mock_response(messages)

        if self.provider == "ollama":
            temp = self.temperature if temperature is None else temperature
            mx = self.max_tokens if max_tokens is None else max_tokens
            prompt = _messages_to_prompt(messages)
            try:
                with httpx.Client(timeout=self.timeout_s) as client:
                    resp = client.post(
                        f"{self.base_url}/api/generate",
                        json={
                            "model": self.model,
                            "prompt": prompt,
                            "stream": False,
                            "options": {"temperature": temp, "num_predict": mx},
                        },
                    )
                if resp.status_code >= 400:
                    raise LLMError(
                        f"LLM call failed ({self.provider}) status={resp.status_code}: {resp.text}"
                    )
                data = resp.json()
                text = (data.get("response") or "").strip()
                return text
            except LLMError:
                raise
            except Exception as e:
                raise LLMError(f"LLM call failed ({self.provider}): {e}") from e

        # groq
        assert self._client is not None
        temp = self.temperature if temperature is None else temperature
        mx = self.max_tokens if max_tokens is None else max_tokens

        payload_messages = [{"role": m.role, "content": m.content} for m in messages]

        try:
            # response_format is optional; if you later want JSON mode you can pass it.
            kwargs: Dict[str, Any] = {}
            if response_format:
                kwargs["response_format"] = response_format

            resp = self._client.chat.completions.create(
                model=self.model,
                messages=payload_messages,
                temperature=temp,
                max_tokens=mx,
                **kwargs,
            )
            text = (resp.choices[0].message.content or "").strip()
            return text

        except Exception as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            suffix = f" status={status}" if status else ""
            raise LLMError(f"LLM call failed ({self.provider}){suffix}: {e}") from e

    def chat_json(
        self,
        messages: List[LLMMessage],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Attempts to return valid JSON dict.
        Uses strict prompting + parses result.
        """
        system_guard = LLMMessage(
            role="system",
            content=(
                "Return ONLY valid JSON. No markdown. No commentary. "
                "If you are unsure, return an empty JSON object {}."
            ),
        )
        text = self.chat(
            [system_guard, *messages],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Try direct parse; if it fails, attempt to extract JSON block.
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Basic salvage: find first '{' and last '}'
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except Exception:
                    pass
            return {}

    @staticmethod
    def _mock_response(messages: List[LLMMessage]) -> str:
        # deterministic + useful for UI wiring
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return (
            "MOCK_ANSWER: I received your question. "
            "This is a placeholder response for local development.\n\n"
            f"User asked: {last_user[:200]}"
        )


# Singleton helper (simple + practical)
_llm_singleton: Optional[LLMClient] = None


def get_llm(*, force_reload: bool = False) -> LLMClient:
    global _llm_singleton
    if force_reload or _llm_singleton is None:
        _llm_singleton = LLMClient()
    return _llm_singleton


def reset_llm() -> None:
    global _llm_singleton
    _llm_singleton = None


def _messages_to_prompt(messages: List[LLMMessage]) -> str:
    parts: list[str] = []
    for m in messages:
        role = m.role.upper()
        parts.append(f"{role}:\n{m.content}".strip())
    parts.append("ASSISTANT:\n")
    return "\n\n".join(parts).strip()
