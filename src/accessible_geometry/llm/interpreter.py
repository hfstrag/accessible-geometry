"""LLM-based interpreter: student's words in, validated geometry actions out."""

import logging
import time
from typing import Any, Protocol

import groq

from accessible_geometry.conversation import History
from accessible_geometry.errors import InterpretationError, ProviderError
from accessible_geometry.geometry.actions import (
    AskClarification,
    GeometryAction,
    parse_tool_call,
    tool_definitions,
)
from accessible_geometry.geometry.state import ConstructionState
from accessible_geometry.i18n import Language
from accessible_geometry.llm.prompts import build_system_prompt

logger = logging.getLogger(__name__)

# Some models emit a single tool call per response, so the request is run as a
# loop: each call is acknowledged and the model continues until it stops calling tools.
MAX_ROUNDS = 8
_ACKNOWLEDGEMENT = (
    "Recorded. Continue with the next step of the student's request, "
    "or answer with a short text and no tool call if the request is complete."
)


class CommandInterpreter(Protocol):
    async def interpret(
        self, text: str, state: ConstructionState, language: Language, history: History
    ) -> list[GeometryAction]: ...


class GroqInterpreter:
    """Interpreter backed by a Groq-hosted model with function calling."""

    def __init__(self, client: groq.AsyncGroq, model: str) -> None:
        self._client = client
        self._model = model
        self._tools: list[Any] = tool_definitions()

    async def interpret(
        self, text: str, state: ConstructionState, language: Language, history: History
    ) -> list[GeometryAction]:
        system_prompt = build_system_prompt(language, state)
        logger.debug("LLM system prompt:\n%s", system_prompt)
        messages: list[Any] = [{"role": "system", "content": system_prompt}]
        for exchange in history:
            messages.append({"role": "user", "content": exchange.user})
            messages.append({"role": "assistant", "content": exchange.assistant})
        messages.append({"role": "user", "content": text})
        logger.debug("LLM user message: %r (with %d previous exchanges)", text, len(history))

        actions: list[GeometryAction] = []
        for round_number in range(1, MAX_ROUNDS + 1):
            # The first round must call a tool; later rounds may stop.
            message = await self._complete(
                messages, required=not actions, round_number=round_number
            )
            tool_calls = message.tool_calls or []
            if not tool_calls:
                break
            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in tool_calls
                    ],
                }
            )
            for call in tool_calls:
                logger.debug("LLM tool call: %s(%s)", call.function.name, call.function.arguments)
                try:
                    action = parse_tool_call(call.function.name, call.function.arguments)
                except InterpretationError as exc:
                    # Let the model see its mistake and try again.
                    logger.info("Invalid tool call, sent back to the model: %s", exc)
                    result = f"Error: {exc}. Fix the call."
                else:
                    actions.append(action)
                    result = _ACKNOWLEDGEMENT
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            if any(isinstance(action, AskClarification) for action in actions):
                break
        else:
            logger.warning("Stopped after %d rounds for %r", MAX_ROUNDS, text)

        if not actions:
            raise InterpretationError("model returned no valid tool call")
        logger.info("Interpreted %r as %s", text, [a.tool_name for a in actions])
        return actions

    async def _complete(self, messages: list[Any], *, required: bool, round_number: int) -> Any:
        started = time.perf_counter()
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=self._tools,
                tool_choice="required" if required else "auto",
                temperature=0,
            )
        except groq.BadRequestError as exc:
            # Groq answers 400 "tool_use_failed" when the model emits a malformed tool call.
            raise InterpretationError(f"model failed to call a tool: {exc}") from exc
        except groq.APIError as exc:
            raise ProviderError("LLM request failed") from exc

        _log_usage(self._model, response, time.perf_counter() - started, round_number)
        message = response.choices[0].message
        if reasoning := getattr(message, "reasoning", None):
            logger.debug("LLM reasoning:\n%s", reasoning)
        return message


def _log_usage(model: str, response: Any, elapsed_s: float, round_number: int) -> None:
    """One INFO line per LLM call: token usage and latency, to keep costs visible."""
    usage = getattr(response, "usage", None)
    prefix = f"LLM {model} round {round_number} answered in {elapsed_s * 1000:.0f} ms"
    if usage is None:
        logger.info(prefix)
        return
    details = getattr(usage, "completion_tokens_details", None)
    reasoning_tokens = getattr(details, "reasoning_tokens", None)
    logger.info(
        "%s: %s prompt + %s completion tokens%s",
        prefix,
        usage.prompt_tokens,
        usage.completion_tokens,
        f" (of which {reasoning_tokens} reasoning)" if reasoning_tokens else "",
    )
