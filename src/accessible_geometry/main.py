"""Application factory and command-line entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import groq
import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from accessible_geometry import __version__
from accessible_geometry.api.routes import router
from accessible_geometry.config import Settings, get_settings
from accessible_geometry.errors import ProviderError
from accessible_geometry.llm.interpreter import GroqInterpreter
from accessible_geometry.service import VoiceCommandService
from accessible_geometry.speech.transcriber import GroqTranscriber

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    _configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not settings.has_api_key:
            logger.warning("GROQ_API_KEY is not set: voice commands are disabled.")
            yield
            return
        assert settings.groq_api_key is not None
        client = groq.AsyncGroq(
            api_key=settings.groq_api_key.get_secret_value(), timeout=settings.request_timeout_s
        )
        app.state.service = VoiceCommandService(
            transcriber=GroqTranscriber(client, settings.stt_model),
            interpreter=GroqInterpreter(client, settings.llm_model),
        )
        try:
            yield
        finally:
            await client.close()

    app = FastAPI(title="Accessible Geometry", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.service = None
    app.include_router(router, prefix="/api")
    app.add_exception_handler(ProviderError, _provider_error_handler)
    # Mounted last so that it does not shadow the API routes.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


async def _provider_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("AI provider error: %s", exc, exc_info=exc.__cause__)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": "The speech or language service is unavailable. Try again."},
    )


def _configure_logging(level: str) -> None:
    """Log our own modules at `level` (e.g. debug), third-party libraries at INFO.

    Done in `create_app` rather than `run` so it also applies under `uvicorn --reload`.
    """
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("accessible_geometry").setLevel(level.upper())


def run() -> None:
    """Start the server (the `accessible-geometry` command)."""
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
