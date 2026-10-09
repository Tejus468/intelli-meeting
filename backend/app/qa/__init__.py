"""Evidence-backed Question Answering package."""
from app.qa.models import QuestionRequest, SourceReference, AnswerResponse
from app.qa.prompts import QA_SYSTEM_PROMPT, build_qa_user_prompt, format_evidence_block
from app.qa.service import (
    answer_question,
    extract_source_references,
    QAServiceError,
    QARetrievalError,
    QALLMError,
)
from app.qa.router import router as qa_router

__all__ = [
    "QuestionRequest",
    "SourceReference",
    "AnswerResponse",
    "QA_SYSTEM_PROMPT",
    "build_qa_user_prompt",
    "format_evidence_block",
    "answer_question",
    "extract_source_references",
    "QAServiceError",
    "QARetrievalError",
    "QALLMError",
    "qa_router",
]
