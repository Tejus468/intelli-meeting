"""FastAPI router for document and transcript ingestion endpoints."""
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from app.ingestion.models import DeleteSourceResponse, IngestionResponse, SourceSummary
from app.ingestion.service import (
    ingest_file,
    list_sources,
    delete_source,
    IngestionError,
    IngestionDatabaseError,
    IngestionPipelineError,
    SourceNotFoundError,
)

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])

ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx"}


@router.get(
    "/sources",
    response_model=List[SourceSummary],
    summary="List persisted sources",
)
def get_sources():
    """Return ingested sources from PostgreSQL, newest first, with chunk counts."""
    try:
        return list_sources()
    except IngestionPipelineError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except IngestionDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable. Please ensure database is running.",
        )


@router.delete(
    "/sources/{source_id}",
    response_model=DeleteSourceResponse,
    summary="Delete a source and all data derived from it",
)
async def remove_source(source_id: str):
    """Remove a document's PostgreSQL rows, pgvector embeddings and Neo4j graph data."""
    try:
        await run_in_threadpool(delete_source, source_id)
    except SourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except IngestionPipelineError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except IngestionDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable. Please ensure database is running.",
        )
    return DeleteSourceResponse(source_id=source_id)


@router.post(
    "/upload",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a document or transcript",
)
async def upload_document(file: UploadFile = File(...)):
    """Upload a TXT, PDF, or DOCX document to extract, chunk, and persist provenance."""
    filename = file.filename or ""
    lower_name = filename.lower()

    if not any(lower_name.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type for '{filename}'. Allowed formats: .txt, .pdf, .docx",
        )

    try:
        content = await file.read()
        if not content or len(content.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty.",
            )

        # Ingestion is synchronous and can take a while (LLM calls); keep the event loop free.
        response = await run_in_threadpool(ingest_file, content, filename)
        return response

    except HTTPException:
        raise
    except IngestionPipelineError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except IngestionDatabaseError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable. Please ensure database is running.",
        )
    except IngestionError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during file ingestion.",
        )
