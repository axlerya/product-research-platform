"""Value object TokenUsage — расход токенов LLM за прогон."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Токены prompt и completion, потраченные прогоном.

    Attributes:
        prompt_tokens: Токены запроса.
        completion_tokens: Токены ответа модели.
    """

    prompt_tokens: int
    completion_tokens: int

    @property
    def total(self) -> int:
        """Суммарный расход токенов за прогон."""
        return self.prompt_tokens + self.completion_tokens
