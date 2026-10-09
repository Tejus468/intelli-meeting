from fastapi import APIRouter, HTTPException, status
from app.qa.models import QuestionRequest, AnswerResponse
from app.qa import service
from app.qa.service import QAServiceError, QALLMError, QARetrievalError

router = APIRouter(prefix="/api/qa", tags=["qa"])


@router.post(
    "/ask",
    response_model=AnswerResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask a question against meeting transcripts and documents",
)
def ask_question(request: QuestionRequest) -> AnswerResponse:
    """Answer a user query with evidence-backed reasoning and source provenance citations."""
    try:
        response = service.answer_question(
            question=request.question,
            top_k=request.top_k,
        )
        return response
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except QALLMError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI answer generation service is currently unavailable. Please verify LLM configuration.",
        )
    except QARetrievalError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Retrieval service encountered an error during evidence search.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing the question.",
        )
