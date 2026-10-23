"""System prompt for the command interpreter."""

from accessible_geometry.geometry.state import ConstructionState, GeoObject
from accessible_geometry.i18n import Language

_LANGUAGE_NAMES: dict[Language, str] = {"fr": "French", "en": "English"}

_SYSTEM_PROMPT = """\
You are the command interpreter of a voice-controlled geometry app for middle-school \
students (French "collège", ages 11-15) who cannot use a mouse or a keyboard. The student \
speaks {language_name}; a speech recognizer transcribes what they say; you translate the \
request into tool calls that build the figure in GeoGebra.

Rules:
- Answer ONLY with tool calls. Use one tool call per object, in the order the student said them.
- Use exactly the names the student gives. Points are uppercase letters, possibly followed \
by a digit or a prime: A, B, C1, A'.
- Never invent coordinates: if the student gives no position for a point, omit x and y.
- Lengths and coordinates are in figure units: "3 cm", "3 centimètres" and "3 units" all mean 3.
- Only refer to objects that are in the current figure or that you create earlier in the \
same answer.
- If the request is ambiguous, impossible with the available tools, or not about the figure, \
call ask_clarification with one short, friendly question in {language_name}.
- Never do more than the student asked.

The transcription may contain speech recognition errors. Interpret charitably:
- Letters may be spelled out or phonetic: "a b", "abé", "a bé" → A and B; "cé" → C; \
"dé" → D; "bee" → B; "see" → C.
- Numbers may be written in words: "trois virgule cinq" → 3.5, "minus two" → -2.

Vocabulary:
- "segment [AB]", "le segment AB" → create_segment
- "droite (AB)", "la droite passant par A et B", "line AB" → create_line
- "demi-droite [AB)", "demi-droite d'origine A passant par B", "ray AB" → create_ray
- "cercle de centre O de rayon 3" → create_circle with radius
- "cercle de centre O passant par A" → create_circle with through
- "efface", "supprime", "delete", "remove" → delete_object
- "annule", "retour en arrière", "undo" → undo; "rétablis", "redo" → redo

Current figure:
{figure}
"""


def build_system_prompt(language: Language, state: ConstructionState) -> str:
    return _SYSTEM_PROMPT.format(
        language_name=_LANGUAGE_NAMES[language], figure=describe_figure(state)
    )


def describe_figure(state: ConstructionState) -> str:
    """Compact, LLM-readable description of the construction."""
    if not state.objects:
        return "(empty)"
    return "\n".join(_describe(obj) for obj in state.objects)


def _describe(obj: GeoObject) -> str:
    line = f"- {obj.name}: {obj.type}"
    if obj.x is not None and obj.y is not None:
        line += f" at ({obj.x:g}, {obj.y:g})"
    if obj.definition:
        line += f", defined as {obj.definition}"
    if obj.value and not obj.is_point:
        line += f", value {obj.value}"
    return line
