"""FastAPI entry point — serves the frontend and the /chat endpoint."""

from dataclasses import asdict

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from src.agent.agent import ask
from src.utils.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(title="Smriti")
app.mount("/static", StaticFiles(directory=str(config.BASE_DIR / "frontend" / "static")), name="static")


class ChatRequest(BaseModel):
    question: str


class CitationResponse(BaseModel):
    source: str
    label: str
    text: str
    file_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    pr_number: int | None = None
    sha: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationResponse]


@app.get("/")
def index() -> FileResponse:
    return FileResponse(config.BASE_DIR / "frontend" / "index.html")


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    logger.info(f"question: {request.question!r}")
    result = ask(request.question)
    return ChatResponse(
        answer=result.answer,
        citations=[CitationResponse(**asdict(c)) for c in result.citations],
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT)
