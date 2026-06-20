from __future__ import annotations

from dataclasses import dataclass

from pydantic.types import JsonValue


@dataclass(frozen=True, slots=True)
class NativeEvent:
    type: str
    payload: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ParserDiagnostic:
    code: str
    detail: str
