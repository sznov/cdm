from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol


ChatMessage = dict[str, str]


@dataclass
class CompletionResult:
    text: str
    model: str
    usage: dict[str, Any] | None = None
    raw_response: dict[str, Any] | None = None


def completion_result_payload(completion: CompletionResult) -> dict[str, Any]:
    return asdict(completion)


class TextModelClient(Protocol):
    async def complete(
        self,
        *,
        system_prompt: str,
        user_content: str,
        messages: list[ChatMessage] | None = None,
        on_token: Any | None = None,
    ) -> CompletionResult:
        ...
