"""AI Information extraction package."""
from app.extraction.models import (
    BaseExtractedItem,
    ExtractedProblem,
    ExtractedAlternative,
    ExtractedRationale,
    ExtractedDecision,
    ExtractedAction,
    ExtractedPerson,
    ExtractedOutcome,
    ExtractionResult,
)
from app.extraction.prompts import (
    SYSTEM_EXTRACTION_PROMPT,
    build_extraction_user_prompt,
)
from app.extraction.llm_client import (
    BaseLLMClient,
    OpenAICompatibleLLMClient,
    get_default_llm_client,
    LLMError,
    LLMConfigurationError,
    LLMAPIError,
    LLMResponseError,
    extract_json_from_text,
)
from app.extraction.service import (
    extract_from_chunk,
    ExtractionServiceError,
    ExtractionValidationError,
)

__all__ = [
    "BaseExtractedItem",
    "ExtractedProblem",
    "ExtractedAlternative",
    "ExtractedRationale",
    "ExtractedDecision",
    "ExtractedAction",
    "ExtractedPerson",
    "ExtractedOutcome",
    "ExtractionResult",
    "SYSTEM_EXTRACTION_PROMPT",
    "build_extraction_user_prompt",
    "BaseLLMClient",
    "OpenAICompatibleLLMClient",
    "get_default_llm_client",
    "LLMError",
    "LLMConfigurationError",
    "LLMAPIError",
    "LLMResponseError",
    "extract_json_from_text",
    "extract_from_chunk",
    "ExtractionServiceError",
    "ExtractionValidationError",
]
