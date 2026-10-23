"""LLM-based interpreter: student's words in, validated geometry actions out."""

import logging
from typing import Any, Protocol

import groq

from accessible_geometry.errors import InterpretationError, ProviderError
from accessible_geometry.geometry.actions import GeometryAction, parse_tool_call, tool_definitions
from accessible_geometry.geometry.state import ConstructionState
from accessible_geometry.i18n import Language
from accessible_geometry.llm.prompts import build_system_prompt

logger = logging.getLogger(__name__)


class CommandInterpreter(Protocol):
    async def interpret(
        self, text: str, state: ConstructionState, language: Language
    ) -> list[GeometryAction]: ...


class GroqInterpreter:
    """Interpreter backed by a Groq-hosted model with function calling."""

    def __init__(self, client: groq.AsyncGroq, model: str) -> None:
        self._client = client
        self._model = model
        self._tools: list[Any] = tool_definitions()

    async def interpret(
        self, text: str, state: ConstructionState, language: Language
    ) -> list[GeometryAction]:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": build_system_prompt(language, state)},
                    {"role": "user", "content": text},
                ],
                tools=self._tools,
                tool_choice="required",
                temperature=0,
            )
        except groq.BadRequestError as exc:
            # Groq answers 400 "tool_use_failed" when the model emits a malformed tool call.
            raise InterpretationError(f"model failed to call a tool: {exc}") from exc
        except groq.APIError as exc:
            raise ProviderError("LLM request failed") from exc

        tool_calls = response.choices[0].message.tool_calls or []
        if not tool_calls:
            raise InterpretationError("model returned no tool call")
        actions = [
            parse_tool_call(call.function.name, call.function.arguments) for call in tool_calls
        ]
        logger.info("Interpreted %r as %s", text, [a.tool_name for a in actions])
        return actions
