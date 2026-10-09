from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from app.db.postgres import check_postgres_health
from app.db.neo4j import check_neo4j_health, close_neo4j_driver
from app.ingestion.router import router as ingestion_router
from app.qa.router import router as qa_router
from app.timeline.router import router as timeline_router
from app.graph_view.router import router as graph_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_neo4j_driver()


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Intelligent Meeting & Decision Intelligence System API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(ingestion_router)
app.include_router(qa_router)
app.include_router(timeline_router)
app.include_router(graph_router)


@app.get("/health")
def health_check():
    pg_ok = check_postgres_health()
    neo4j_ok = check_neo4j_health()

    is_all_ok = pg_ok and neo4j_ok

    content = {
        "status": "ok" if is_all_ok else "degraded",
        "backend": "ok",
        "postgresql": "ok" if pg_ok else "unavailable",
        "neo4j": "ok" if neo4j_ok else "unavailable",
    }

    http_status = status.HTTP_200_OK if is_all_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=http_status, content=content)
