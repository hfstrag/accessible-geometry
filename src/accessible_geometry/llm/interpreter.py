"""LLM-based interpreter: student's words in, validated geometry actions out."""

import logging
import time
from typing import Any, Protocol

import groq

from accessible_geometry.conversation import History
from accessible_geometry.errors import InterpretationError, ProviderError
from accessible_geometry.geometry.actions import GeometryAction, parse_tool_call, tool_definitions
from accessible_geometry.geometry.state import ConstructionState
from accessible_geometry.i18n import Language
from accessible_geometry.llm.prompts import build_system_prompt

logger = logging.getLogger(__name__)

# The model answers each command with a single `apply_actions` call. Invalid
# calls are sent back with the error so that the model can correct them.
MAX_ATTEMPTS = 3


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

        for attempt in range(1, MAX_ATTEMPTS + 1):
            message = await self._complete(messages, attempt)
            tool_calls = message.tool_calls or []
            if not tool_calls:
                raise InterpretationError("model returned no tool call")

            # Normally one call; if a model splits the request, the calls are concatenated.
            actions: list[GeometryAction] = []
            errors: dict[str, str] = {}
            for call in tool_calls:
                logger.debug("LLM tool call: %s(%s)", call.function.name, call.function.arguments)
                try:
                    actions.extend(parse_tool_call(call.function.name, call.function.arguments))
                except InterpretationError as exc:
                    errors[call.id] = str(exc)
            if not errors:
                logger.info("Interpreted %r as %s", text, [a.action_name for a in actions])
                return actions

            logger.info("Invalid tool call (attempt %d), sent back: %s", attempt, errors)
            messages.append(_assistant_message(message.content, tool_calls))
            for call in tool_calls:
                result = (
                    f"Error: {errors[call.id]}."
                    if call.id in errors
                    else "Not applied, because of the error in another call."
                )
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            messages.append(
                {
                    "role": "user",
                    "content": f"Nothing was applied. Call {tool_calls[0].function.name} "
                    "again once, with the complete corrected list of actions.",
                }
            )

        raise InterpretationError(f"no valid tool call after {MAX_ATTEMPTS} attempts")

    async def _complete(self, messages: list[Any], attempt: int) -> Any:
        started = time.perf_counter()
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=self._tools,
                tool_choice="required",
                temperature=0,
            )
        except groq.BadRequestError as exc:
            # Groq answers 400 "tool_use_failed" when the model emits a malformed tool call.
            raise InterpretationError(f"model failed to call a tool: {exc}") from exc
        except groq.APIError as exc:
            raise ProviderError("LLM request failed") from exc

        _log_usage(self._model, response, time.perf_counter() - started, attempt)
        message = response.choices[0].message
        if reasoning := getattr(message, "reasoning", None):
            logger.debug("LLM reasoning:\n%s", reasoning)
        return message


def _log_usage(model: str, response: Any, elapsed_s: float, attempt: int) -> None:
    """One INFO line per LLM call: token usage and latency, to keep costs visible."""
    usage = getattr(response, "usage", None)
    retry = f" (attempt {attempt})" if attempt > 1 else ""
    prefix = f"LLM {model}{retry} answered in {elapsed_s * 1000:.0f} ms"
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


def _assistant_message(content: str | None, tool_calls: list[Any]) -> dict[str, Any]:
    """Echo the model's tool calls back into the conversation, as the API requires."""
    return {
        "role": "assistant",
        "content": content or "",
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.function.name, "arguments": call.function.arguments},
            }
            for call in tool_calls
        ],
    }
