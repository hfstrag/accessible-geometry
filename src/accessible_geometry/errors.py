"""Domain exceptions shared across the application."""


class ProviderError(Exception):
    """An external AI provider (speech-to-text or LLM) failed or is unreachable."""


class InterpretationError(Exception):
    """The LLM did not produce a usable set of geometry actions."""


class PlanningError(Exception):
    """A geometry action cannot be applied to the current figure.

    `message` is already localized and can be shown to and spoken to the student.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
