from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AnchorEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    href: str


class KVPair(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    value: str


class FactsBundle(BaseModel):
    """Site-agnostic page facts. Survives DOM shuffles because it's keyed on
    labels, anchor text, structured data, and visible text — not selectors.
    """

    model_config = ConfigDict(frozen=True)

    url: str
    title: str | None = None
    meta_description: str | None = None
    structured_data_compact: str = ""
    anchors: list[AnchorEntry] = Field(default_factory=list)
    key_value_pairs: list[KVPair] = Field(default_factory=list)
    text_blocks: list[str] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)
    calendar_urls: list[str] = Field(default_factory=list)

    def to_prompt_text(self, max_chars: int = 14000) -> str:
        parts: list[str] = []
        if self.title:
            parts.append(f"TITLE: {self.title}")
        if self.meta_description:
            parts.append(f"DESCRIPTION: {self.meta_description}")
        if self.structured_data_compact:
            parts.append(f"STRUCTURED_DATA:\n{self.structured_data_compact}")
        if self.headings:
            parts.append("HEADINGS:\n" + "\n".join(f"- {h}" for h in self.headings))
        if self.key_value_pairs:
            kv = "\n".join(f"- {p.label}: {p.value}" for p in self.key_value_pairs)
            parts.append(f"KEY_VALUE_PAIRS:\n{kv}")
        if self.calendar_urls:
            parts.append("CALENDAR_URLS:\n" + "\n".join(f"- {u}" for u in self.calendar_urls))
        if self.anchors:
            ah = "\n".join(f"- [{a.text}] -> {a.href}" for a in self.anchors)
            parts.append(f"ANCHORS:\n{ah}")
        if self.text_blocks:
            parts.append("TEXT_BLOCKS:\n" + "\n---\n".join(self.text_blocks))
        out = "\n\n".join(parts)
        if len(out) > max_chars:
            out = out[:max_chars] + "\n... [truncated]"
        return out
