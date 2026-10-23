"""Recent exchanges between the student and the app, kept by the browser.

They give the LLM short-term memory, so that a student can correct a request
("non, je voulais dire B") or answer a clarification question.
"""

from pydantic import BaseModel, Field

MAX_EXCHANGES = 8


class Exchange(BaseModel):
    user: str = Field(max_length=1000, description="What the student said.")
    assistant: str = Field(max_length=1000, description="What the app answered.")


History = list[Exchange]
