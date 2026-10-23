"""Test doubles for the AI providers, so tests never need a Groq API key."""

from accessible_geometry.conversation import History
from accessible_geometry.errors import InterpretationError
from accessible_geometry.geometry.actions import GeometryAction
from accessible_geometry.geometry.state import ConstructionState
from accessible_geometry.i18n import Language


class FakeTranscriber:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript
        self.calls: list[tuple[bytes, str, Language]] = []

    async def transcribe(self, audio: bytes, filename: str, language: Language) -> str:
        self.calls.append((audio, filename, language))
        return self.transcript


class FakeInterpreter:
    """Returns canned actions; raises InterpretationError when given None."""

    def __init__(self, actions: list[GeometryAction] | None) -> None:
        self.actions = actions
        self.calls: list[tuple[str, History]] = []

    async def interpret(
        self, text: str, state: ConstructionState, language: Language, history: History
    ) -> list[GeometryAction]:
        self.calls.append((text, history))
        if self.actions is None:
            raise InterpretationError("fake failure")
        return self.actions
