from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from vid2note_core.errors import Vid2NoteError
from vid2note_core.source.models import SourceRecord
from vid2note_core.vault.models import VaultPage
from vid2note_core.wiki.models import ChangeSet


class ChatModel(Protocol):
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str: ...


class WikiInvalidChangeSetError(Vid2NoteError):
    def __init__(self):
        super().__init__(
            "Wiki compiler returned an invalid ChangeSet",
            code="WIKI_INVALID_CHANGESET",
            user_message="Wiki 变更提案格式无效，请重试",
            step="wiki_compiler",
        )


class CompileInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: SourceRecord
    source_note: VaultPage
    schema_text: str
    index_text: str
    related_pages: list[VaultPage]


class CompileResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    classification: Literal["new", "enhancement", "duplicate", "correction", "contradiction", "gap"]
    changeset: ChangeSet | None


class WikiCompiler:
    def __init__(self, llm: ChatModel):
        self.llm = llm
        self.prompt = (Path(__file__).parents[1] / "prompts" / "wiki_ingest.txt").read_text(
            encoding="utf-8"
        )

    def propose(self, request: CompileInput) -> CompileResult:
        input_payload = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
        messages = [
            {"role": "system", "content": self.prompt},
            {"role": "user", "content": input_payload},
        ]
        response = self.llm.chat(messages, temperature=0, max_tokens=12_000, timeout=120)
        try:
            return CompileResult.model_validate_json(response)
        except ValidationError as first_error:
            repair_messages = [
                *messages,
                {"role": "assistant", "content": response},
                {
                    "role": "user",
                    "content": (
                        "The JSON failed validation. Return one corrected JSON object only. "
                        f"Validation errors: {first_error.json()}"
                    ),
                },
            ]
            repaired = self.llm.chat(
                repair_messages,
                temperature=0,
                max_tokens=12_000,
                timeout=120,
            )
            try:
                return CompileResult.model_validate_json(repaired)
            except ValidationError as second_error:
                raise WikiInvalidChangeSetError() from second_error
