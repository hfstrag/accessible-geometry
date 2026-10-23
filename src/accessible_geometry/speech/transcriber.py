"""Speech-to-text transcription of the student's recorded voice."""

import logging
import time
from typing import Protocol

import groq

from accessible_geometry.errors import ProviderError
from accessible_geometry.i18n import Language

logger = logging.getLogger(__name__)

# Whisper uses the prompt as preceding context: listing geometry words and point
# names makes it spell them the way we expect ("segment AB" rather than "segment habit").
_VOCABULARY_PROMPTS: dict[Language, str] = {
    "fr": (
        "Géométrie. Place le point A, le point B. Trace le segment [AB], la droite (BC), "
        "la demi-droite [CD), le cercle de centre O et de rayon 3. Annule."
    ),
    "en": (
        "Geometry. Place point A, point B. Draw segment AB, line BC, ray CD, "
        "the circle with center O and radius 3. Undo."
    ),
}


class Transcriber(Protocol):
    async def transcribe(self, audio: bytes, filename: str, language: Language) -> str: ...


class GroqTranscriber:
    """Transcriber backed by Whisper hosted on Groq."""

    def __init__(self, client: groq.AsyncGroq, model: str) -> None:
        self._client = client
        self._model = model

    async def transcribe(self, audio: bytes, filename: str, language: Language) -> str:
        started = time.perf_counter()
        try:
            result = await self._client.audio.transcriptions.create(
                file=(filename, audio),
                model=self._model,
                language=language,
                prompt=_VOCABULARY_PROMPTS[language],
                response_format="json",
                temperature=0.0,
            )
        except groq.APIError as exc:
            raise ProviderError("speech-to-text request failed") from exc
        logger.info(
            "STT %s transcribed %d KB in %.0f ms",
            self._model,
            len(audio) // 1024,
            (time.perf_counter() - started) * 1000,
        )
        return result.text.strip()
