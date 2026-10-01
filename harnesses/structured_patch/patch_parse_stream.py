from __future__ import annotations

import json
import re

from core.json_repair_loading import load_structured_patch_json_with_deterministic_repairs
from harnesses.structured_patch.patch_parse_json_values import json_value_end
from harnesses.structured_patch.patch_parse_payloads import (
    structured_patch_operations_from_payload,
)
from harnesses.structured_patch.patch_parse_noop import structured_patch_output_is_noop
from core.schemas import StructuredOutputError


class StructuredPatchOperationStreamParser:
    def __init__(self, *, strip_thought_blocks: bool = True) -> None:
        self.buffer = ""
        self.open_thought_tag: str | None = None
        self.repair_reports: list[dict[str, Any]] = []
        self.strip_thought_blocks_enabled = strip_thought_blocks

    def strip_stream_thought_blocks(self, text: str) -> str:
        output: list[str] = []
        remaining = text
        while remaining:
            if self.open_thought_tag is not None:
                close_match = re.search(
                    rf"</\s*{re.escape(self.open_thought_tag)}\s*>",
                    remaining,
                    flags=re.IGNORECASE,
                )
                if close_match is None:
                    return "".join(output)
                remaining = remaining[close_match.end() :]
                self.open_thought_tag = None
                continue

            open_match = re.search(r"<\s*(thought|think)\b[^>]*>", remaining, flags=re.IGNORECASE)
            if open_match is None:
                output.append(remaining)
                break
            output.append(remaining[: open_match.start()])
            self.open_thought_tag = open_match.group(1).lower()
            remaining = remaining[open_match.end() :]
        return "".join(output)

    def load_payload(self, raw_json: str) -> Any:
        payload, reports = load_structured_patch_json_with_deterministic_repairs(raw_json)
        self.repair_reports.extend(reports)
        return payload

    def feed(self, text: str, *, final: bool = False) -> tuple[list[dict[str, Any]], list[str]]:
        self.buffer += self.strip_stream_thought_blocks(text) if self.strip_thought_blocks_enabled else text
        operations: list[dict[str, Any]] = []
        errors: list[str] = []
        while True:
            starts = [index for index in (self.buffer.find("{"), self.buffer.find("[")) if index >= 0]
            if not starts:
                if len(self.buffer) > 4096:
                    self.buffer = self.buffer[-4096:]
                break
            start = min(starts)
            end = json_value_end(self.buffer, start)
            if end is None:
                if start > 0:
                    self.buffer = self.buffer[start:]
                break
            candidate = self.buffer[start:end]
            self.buffer = self.buffer[end:]
            try:
                payload = self.load_payload(candidate)
            except (json.JSONDecodeError, ValueError, StructuredOutputError) as exc:
                errors.append(f"Structured patch operation JSON parsing failed: {exc}")
                continue
            operations.extend(structured_patch_operations_from_payload(payload))
        if final and self.buffer.strip():
            for line in self.buffer.splitlines():
                stripped = line.strip().rstrip(",")
                if not stripped or not stripped.startswith("{"):
                    continue
                try:
                    payload = self.load_payload(stripped)
                except (json.JSONDecodeError, ValueError, StructuredOutputError) as exc:
                    errors.append(f"Structured patch operation JSONL parsing failed: {exc}")
                    continue
                operations.extend(structured_patch_operations_from_payload(payload))
            self.buffer = ""
        if final:
            self.open_thought_tag = None
        return operations, errors


def parse_structured_patch_operations(raw_output: str) -> list[dict[str, Any]]:
    if structured_patch_output_is_noop(raw_output):
        return []
    noop_parser = StructuredPatchOperationStreamParser()
    visible_output = noop_parser.strip_stream_thought_blocks(raw_output)
    # Recognize an explicit final no-op before falling back to thought content.
    # A thought-only or unfinished response is not evidence of a no-op.
    if (
        visible_output.strip()
        and noop_parser.open_thought_tag is None
        and structured_patch_output_is_noop(visible_output)
    ):
        return []
    parser = StructuredPatchOperationStreamParser()
    operations, errors = parser.feed(raw_output, final=True)
    if operations:
        return operations
    thought_fallback_parser = StructuredPatchOperationStreamParser(strip_thought_blocks=False)
    thought_operations, thought_errors = thought_fallback_parser.feed(raw_output, final=True)
    if thought_operations:
        return thought_operations
    errors.extend(thought_errors)
    if errors:
        raise StructuredOutputError("; ".join(errors))
    raise StructuredOutputError("No structured patch operations found.")


__all__ = [
    "StructuredPatchOperationStreamParser",
    "json_value_end",
    "parse_structured_patch_operations",
    "structured_patch_operations_from_payload",
]
