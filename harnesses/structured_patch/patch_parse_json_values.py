from __future__ import annotations


def json_value_end(text: str, start: int) -> int | None:
    opener = text[start]
    closer = "}" if opener == "{" else "]" if opener == "[" else ""
    if not closer:
        return None
    stack = [closer]
    in_string = False
    escape = False
    for index in range(start + 1, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            stack.append("}")
        elif char == "[":
            stack.append("]")
        elif char in {"}", "]"}:
            if not stack or stack[-1] != char:
                return index + 1
            stack.pop()
            if not stack:
                return index + 1
    return None


__all__ = ["json_value_end"]
