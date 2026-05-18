from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FieldType = Literal[
    "string",
    "number",
    "integer",
    "currency",
    "url",
    "email",
    "phone",
    "date",
    "boolean",
    "list_string",
]
TaskType = Literal["list_extraction", "single_entity_extraction"]
ExpectedOutput = Literal["array", "object"]


class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    type: FieldType
    required: bool = False
    description: str | None = Field(default=None, max_length=200)


class IntentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_type: TaskType
    entity_name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    fields: tuple[FieldSpec, ...] = Field(min_length=1, max_length=20)
    expected_output: ExpectedOutput

    def required_fields(self) -> tuple[FieldSpec, ...]:
        return tuple(f for f in self.fields if f.required)

    def optional_fields(self) -> tuple[FieldSpec, ...]:
        return tuple(f for f in self.fields if not f.required)

    def field_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)
