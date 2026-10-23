"""API routes, mounted under `/api`."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from accessible_geometry.config import Settings
from accessible_geometry.conversation import MAX_EXCHANGES, Exchange
from accessible_geometry.geometry.state import ConstructionState
from accessible_geometry.i18n import Language
from accessible_geometry.service import CommandResult, VoiceCommandService

router = APIRouter()


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_service(request: Request) -> VoiceCommandService:
    service: VoiceCommandService | None = getattr(request.app.state, "service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GROQ_API_KEY is not configured on the server.",
        )
    return service


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
ServiceDep = Annotated[VoiceCommandService, Depends(get_service)]


class HealthResponse(BaseModel):
    status: str
    ai_configured: bool


class TextCommandRequest(BaseModel):
    text: str = Field(max_length=1000)
    language: Language
    state: ConstructionState = Field(default_factory=ConstructionState)
    history: list[Exchange] = Field(default_factory=list, max_length=MAX_EXCHANGES)


_HistoryAdapter = TypeAdapter(Annotated[list[Exchange], Field(max_length=MAX_EXCHANGES)])


@router.get("/health")
async def health(request: Request) -> HealthResponse:
    return HealthResponse(
        status="ok", ai_configured=getattr(request.app.state, "service", None) is not None
    )


@router.post("/command")
async def text_command(payload: TextCommandRequest, service: ServiceDep) -> CommandResult:
    """Run a typed command. Skips speech-to-text; also useful for testing."""
    return await service.handle_text(payload.text, payload.state, payload.language, payload.history)


@router.post("/voice")
async def voice_command(
    service: ServiceDep,
    settings: SettingsDep,
    audio: Annotated[UploadFile, File(description="Recorded speech (webm, ogg, wav...).")],
    language: Annotated[Language, Form()],
    state: Annotated[str, Form(description="ConstructionState as JSON.")] = "{}",
    history: Annotated[str, Form(description="Recent exchanges as a JSON list.")] = "[]",
) -> CommandResult:
    """Run a spoken command recorded by the browser."""
    try:
        construction = ConstructionState.model_validate_json(state)
        exchanges = _HistoryAdapter.validate_json(history)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.errors()
        ) from exc

    data = await audio.read(settings.max_audio_bytes + 1)
    if len(data) > settings.max_audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Recording is too long."
        )
    return await service.handle_audio(
        data, audio.filename or "speech.webm", construction, language, exchanges
    )
