"""The voice command pipeline: speech-to-text, interpretation, planning."""

import logging
from typing import Literal

from pydantic import BaseModel

from accessible_geometry.conversation import History
from accessible_geometry.errors import InterpretationError, PlanningError
from accessible_geometry.geometry.planner import Step, plan_actions
from accessible_geometry.geometry.state import ConstructionState
from accessible_geometry.i18n import Language, translate
from accessible_geometry.llm.interpreter import CommandInterpreter
from accessible_geometry.speech.transcriber import Transcriber

logger = logging.getLogger(__name__)

CommandStatus = Literal["executed", "clarification", "rejected", "empty"]


class CommandResult(BaseModel):
    """What the browser needs to update the figure and give feedback."""

    status: CommandStatus
    transcript: str
    message: str
    steps: list[Step] = []


class VoiceCommandService:
    def __init__(self, transcriber: Transcriber, interpreter: CommandInterpreter) -> None:
        self._transcriber = transcriber
        self._interpreter = interpreter

    async def handle_audio(
        self,
        audio: bytes,
        filename: str,
        state: ConstructionState,
        language: Language,
        history: History,
    ) -> CommandResult:
        transcript = await self._transcriber.transcribe(audio, filename, language)
        logger.info("Transcript (%s): %r", language, transcript)
        return await self.handle_text(transcript, state, language, history)

    async def handle_text(
        self, text: str, state: ConstructionState, language: Language, history: History
    ) -> CommandResult:
        text = text.strip()
        if not text:
            return CommandResult(
                status="empty", transcript="", message=translate("nothing_heard", language)
            )

        try:
            actions = await self._interpreter.interpret(text, state, language, history)
        except InterpretationError:
            logger.warning("Could not interpret %r", text, exc_info=True)
            return CommandResult(
                status="rejected", transcript=text, message=translate("not_understood", language)
            )

        try:
            plan = plan_actions(actions, state, language)
        except PlanningError as exc:
            logger.info("Rejected by planner: %s", exc.message)
            return CommandResult(status="rejected", transcript=text, message=exc.message)

        for step in plan.steps:
            logger.debug("GeoGebra step: %s", step.model_dump_json())

        return CommandResult(
            status=plan.status, transcript=text, message=plan.message, steps=plan.steps
        )
