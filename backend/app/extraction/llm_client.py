"""LLM provider client abstraction with JSON extraction capabilities."""
import json
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import httpx

from app.core.config import settings


class LLMError(Exception):
    """Base exception for LLM operations."""
    pass


class LLMConfigurationError(LLMError):
    """Raised when LLM configuration (e.g. API key) is missing or invalid."""
    pass


class LLMAPIError(LLMError):
    """Raised when the LLM provider API returns an error or is unreachable."""
    pass


class LLMResponseError(LLMError):
    """Raised when the LLM returns invalid or unparseable JSON."""
    pass


class LLMEmptyResponseError(LLMResponseError):
    """Raised when the LLM returns an empty or whitespace-only response (nothing to parse)."""
    pass


def extract_json_from_text(raw_text: str) -> Dict[str, Any]:
    """Parse JSON from raw LLM output, stripping markdown fences if present."""
    if raw_text is None or not raw_text.strip():
        raise LLMEmptyResponseError("LLM returned an empty response")
    text = raw_text.strip()

    # Match ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    else:
        # A truncated reply may open a fence and never close it: drop a stray opening/closing marker
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()

    if not text:  # e.g. an empty fenced block
        raise LLMEmptyResponseError("LLM returned an empty response")

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMResponseError(f"Failed to parse LLM output as JSON: {e}") from e


class BaseLLMClient(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    def generate_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Generate structured JSON response from system and user prompts."""
        pass

    @abstractmethod
    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        """Generate free-form text response from system and user prompts."""
        pass


class OpenAICompatibleLLMClient(BaseLLMClient):
    """Client for OpenAI-compatible chat completion APIs (OpenAI, Gemini OpenAI endpoint, etc.)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        json_mode: Optional[bool] = None,
    ):
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.llm_timeout_seconds
        self.json_mode = json_mode if json_mode is not None else settings.llm_json_mode

    def _call_api(self, system_prompt: str, user_prompt: str, response_format: Optional[Dict[str, Any]] = None) -> str:
        if not self.api_key:
            raise LLMConfigurationError(
                "LLM API key is not configured. Please set the LLM_API_KEY environment variable."
            )

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
        }
        if response_format:
            payload["response_format"] = response_format

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            raise LLMAPIError(f"LLM API returned HTTP {e.response.status_code}") from None
        except httpx.TimeoutException:
            raise LLMAPIError(f"LLM API request timed out after {self.timeout:g}s") from None
        except httpx.RequestError as e:
            raise LLMAPIError("LLM API request connection failed") from None
        except Exception as e:
            raise LLMAPIError("Unexpected error communicating with LLM API") from None

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise LLMResponseError("LLM response format missing choices/message/content") from e

    def generate_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        response_format = {"type": "json_object"} if self.json_mode else None
        content = self._call_api(system_prompt, user_prompt, response_format=response_format)
        return extract_json_from_text(content)

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        return self._call_api(system_prompt, user_prompt).strip()


def get_default_llm_client() -> BaseLLMClient:
    """Factory to retrieve configured LLM client instance."""
    return OpenAICompatibleLLMClient()

