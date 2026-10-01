from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, ClassVar, Iterable, Iterator

from core.model_client import ChatMessage, CompletionResult


CODEX_BASE_URL = os.environ.get("CODEX_BASE_URL", "https://chatgpt.com/backend-api/codex").rstrip("/")
CODEX_CLIENT_VERSION = os.environ.get("CODEX_CLIENT_VERSION", "1.0.0")
CODEX_OAUTH_REFRESH_URL = "https://auth.openai.com/oauth/token"
CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
DEFAULT_CODEX_MODEL = os.environ.get("CODEX_DEFAULT_MODEL", "gpt-5.5")
REFRESH_SKEW_SECONDS = 30
USER_AGENT = "concept-modeler-codex-provider/0.1"


class CodexProviderError(RuntimeError):
    def __init__(self, status: int, message: str, error_type: str = "provider_error") -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.error_type = error_type


class CodexAuthError(CodexProviderError):
    def __init__(self, message: str) -> None:
        super().__init__(401, message, "authentication_error")


@dataclass
class CodexCredentials:
    access_token: str
    account_id: str | None = None


def _json_dumps(data: Any) -> bytes:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _b64url_json(segment: str) -> dict[str, Any] | None:
    padding = "=" * (-len(segment) % 4)
    try:
        raw = base64.urlsafe_b64decode((segment + padding).encode("ascii"))
        value = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def jwt_exp(token: str) -> int | None:
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload = _b64url_json(parts[1])
    exp = payload.get("exp") if payload else None
    return exp if isinstance(exp, int) else None


def token_is_fresh(token: str, skew_seconds: int = REFRESH_SKEW_SECONDS) -> bool:
    exp = jwt_exp(token)
    return exp is None or time.time() < exp - skew_seconds


def extract_account_id(tokens: dict[str, Any]) -> str | None:
    for key in ("account_id", "chatgpt_account_id"):
        value = tokens.get(key)
        if isinstance(value, str) and value:
            return value
    id_token = tokens.get("id_token")
    if isinstance(id_token, str):
        parts = id_token.split(".")
        payload = _b64url_json(parts[1]) if len(parts) >= 2 else None
        auth_claim = payload.get("https://api.openai.com/auth") if payload else None
        if isinstance(auth_claim, dict):
            value = auth_claim.get("chatgpt_account_id")
            if isinstance(value, str) and value:
                return value
    return None


class CodexAuthProvider:
    def __init__(self, auth_file: str | Path | None = None) -> None:
        self.auth_file = Path(
            auth_file
            or os.environ.get("CODEX_AUTH_FILE")
            or (Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "auth.json")
        )
        self._env_access_token: str | None = None
        self._env_account_id: str | None = None

    def get(self, *, force_refresh: bool = False) -> CodexCredentials:
        env_token = self._env_access_token or os.environ.get("CODEX_ACCESS_TOKEN")
        if env_token:
            if force_refresh:
                refresh_token = os.environ.get("CODEX_REFRESH_TOKEN")
                if not refresh_token:
                    raise CodexAuthError("CODEX_ACCESS_TOKEN is set but CODEX_REFRESH_TOKEN is not.")
                refreshed = self._refresh(refresh_token)
                env_token = str(refreshed.get("access_token") or env_token)
                self._env_access_token = env_token
                self._env_account_id = extract_account_id(refreshed) or os.environ.get("CODEX_ACCOUNT_ID")
            return CodexCredentials(env_token, self._env_account_id or os.environ.get("CODEX_ACCOUNT_ID"))

        data = self._read_auth()
        if data.get("auth_mode") != "chatgpt":
            raise CodexAuthError("Codex provider requires Codex ChatGPT auth. Run `codex login` with ChatGPT auth.")
        tokens = data.get("tokens")
        if not isinstance(tokens, dict) or not tokens.get("access_token"):
            raise CodexAuthError("No Codex ChatGPT access token found. Run `codex login` first.")
        if force_refresh or not token_is_fresh(str(tokens["access_token"])):
            refresh_token = tokens.get("refresh_token")
            if not isinstance(refresh_token, str) or not refresh_token:
                raise CodexAuthError("No Codex refresh token found. Run `codex login` again.")
            refreshed = self._refresh(refresh_token)
            for key in ("access_token", "id_token", "refresh_token", "account_id", "chatgpt_account_id"):
                if refreshed.get(key):
                    tokens[key] = refreshed[key]
            data["tokens"] = tokens
            data["last_refresh"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
            self._write_auth(data)
        return CodexCredentials(str(tokens["access_token"]), extract_account_id(tokens))

    def _read_auth(self) -> dict[str, Any]:
        if not self.auth_file.exists():
            raise CodexAuthError(f"Codex auth file not found at {self.auth_file}. Run `codex login` first.")
        try:
            data = json.loads(self.auth_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CodexAuthError(f"Codex auth file is not valid JSON: {exc}") from exc
        return data if isinstance(data, dict) else {}

    def _write_auth(self, data: dict[str, Any]) -> None:
        tmp = self.auth_file.with_suffix(self.auth_file.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.auth_file)
        try:
            os.chmod(self.auth_file, 0o600)
        except OSError:
            pass

    def _refresh(self, refresh_token: str) -> dict[str, Any]:
        payload = {"client_id": CODEX_OAUTH_CLIENT_ID, "grant_type": "refresh_token", "refresh_token": refresh_token}
        request = urllib.request.Request(
            CODEX_OAUTH_REFRESH_URL,
            data=_json_dumps(payload),
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                value = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise CodexAuthError(f"Codex token refresh failed with HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise CodexAuthError(f"Codex token refresh failed: {exc}") from exc
        return value if isinstance(value, dict) else {}


def iter_sse_events(stream: BinaryIO) -> Iterator[dict[str, Any]]:
    event_name: str | None = None
    data_lines: list[str] = []

    def emit() -> dict[str, Any] | None:
        nonlocal event_name, data_lines
        if not data_lines:
            event_name = None
            return None
        data = "\n".join(data_lines)
        event = event_name
        event_name = None
        data_lines = []
        if data == "[DONE]":
            return None
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            return {"type": event or "message", "data": data}
        if event and isinstance(parsed, dict) and "type" not in parsed:
            parsed["type"] = event
        return parsed if isinstance(parsed, dict) else {"type": event or "message", "data": parsed}

    for raw_line in stream:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
        if line == "":
            event = emit()
            if event is not None:
                yield event
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    event = emit()
    if event is not None:
        yield event


def normalize_model(model: str | None) -> str:
    model = model or DEFAULT_CODEX_MODEL
    return model.split("/", 1)[1] if model.startswith("openai-codex/") else model


def _flatten_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
        return "\n".join(parts)
    return str(content)


def chat_messages_to_responses_payload(
    *,
    model: str,
    messages: list[ChatMessage],
    max_completion_tokens: int | None = None,
    reasoning_effort: str | None = None,
    response_format_json_object: bool = True,
) -> dict[str, Any]:
    input_items: list[dict[str, Any]] = []
    instruction_parts: list[str] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role in ("system", "developer"):
            text = _flatten_text(content).strip()
            if text:
                instruction_parts.append(text)
        elif role in ("user", "assistant"):
            input_items.append({"role": role, "content": _flatten_text(content)})
        else:
            raise CodexProviderError(400, f"Unsupported message role: {role!r}.")
    payload: dict[str, Any] = {"model": normalize_model(model), "input": input_items, "store": False}
    if instruction_parts:
        payload["instructions"] = "\n\n".join(instruction_parts)
    # The Codex ChatGPT Responses surface currently rejects max_output_tokens.
    # Keep accepting max_completion_tokens in the client interface for parity
    # with other providers, but do not send it on this backend.
    _ = max_completion_tokens
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}
    if response_format_json_object:
        payload["text"] = {"format": {"type": "json_object"}}
    return payload


def usage_to_completion_usage(usage: Any) -> dict[str, Any] | None:
    if not isinstance(usage, dict):
        return None
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    total_tokens = usage.get("total_tokens")
    if total_tokens is None and isinstance(input_tokens, int) and isinstance(output_tokens, int):
        total_tokens = input_tokens + output_tokens
    result: dict[str, Any] = {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": total_tokens,
    }
    if usage.get("input_tokens_details") is not None:
        result["prompt_tokens_details"] = usage["input_tokens_details"]
    if usage.get("output_tokens_details") is not None:
        result["completion_tokens_details"] = usage["output_tokens_details"]
    return result


def collect_response_completion(events: Iterable[dict[str, Any]], model: str) -> CompletionResult:
    text_parts: list[str] = []
    usage: dict[str, Any] | None = None
    raw_events: list[dict[str, Any]] = []
    response_id = f"codex-{uuid.uuid4().hex}"
    for event in events:
        raw_events.append(event)
        event_type = event.get("type")
        if event_type in ("response.output_text.delta", "response.refusal.delta") and isinstance(event.get("delta"), str):
            text_parts.append(event["delta"])
        elif event_type == "response.completed":
            response = event.get("response")
            if isinstance(response, dict):
                response_id = str(response.get("id") or response_id)
                usage = usage_to_completion_usage(response.get("usage"))
        elif event_type in ("response.error", "error"):
            error = event.get("error") if isinstance(event.get("error"), dict) else event
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise CodexProviderError(502, f"Codex upstream stream error: {message}", "upstream_error")
    return CompletionResult(
        text="".join(text_parts),
        model=model,
        usage=usage,
        raw_response={"id": response_id, "events": raw_events},
    )


class CodexBackend:
    def __init__(
        self,
        auth_provider: CodexAuthProvider | None = None,
        *,
        base_url: str = CODEX_BASE_URL,
        timeout_seconds: float = 900.0,
    ) -> None:
        self.auth_provider = auth_provider or CodexAuthProvider()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def create_response_stream(self, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        request_payload = dict(payload)
        request_payload["stream"] = True
        request_payload.setdefault("store", False)
        with self._open("POST", f"{self.base_url}/responses", request_payload) as response:
            yield from iter_sse_events(response)

    def _open(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None,
        *,
        retried: bool = False,
    ) -> Any:
        credentials = self.auth_provider.get(force_refresh=False)
        headers = {
            "Authorization": f"Bearer {credentials.access_token}",
            "Accept": "text/event-stream, application/json",
            "User-Agent": USER_AGENT,
        }
        if credentials.account_id:
            headers["ChatGPT-Account-ID"] = credentials.account_id
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = _json_dumps(payload)
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            return urllib.request.urlopen(request, timeout=self.timeout_seconds)
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and not retried:
                self.auth_provider.get(force_refresh=True)
                return self._open(method, url, payload, retried=True)
            detail = exc.read().decode("utf-8", errors="replace")
            raise CodexProviderError(exc.code, f"Codex upstream returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise CodexProviderError(502, f"Could not reach Codex upstream: {exc}", "upstream_error") from exc


@dataclass
class CodexResponsesClient:
    provider_id: ClassVar[str] = "codex"

    model: str = DEFAULT_CODEX_MODEL
    max_completion_tokens: int | None = 32768
    reasoning_effort: str | None = "xhigh"
    response_format_json_object: bool = True
    base_url: str = CODEX_BASE_URL
    auth_file: str | Path | None = None
    timeout_seconds: float = 900.0

    async def complete(
        self,
        *,
        system_prompt: str,
        user_content: str,
        messages: list[ChatMessage] | None = None,
        on_token: Any | None = None,
    ) -> CompletionResult:
        if on_token is not None:
            raise NotImplementedError("CodexResponsesClient does not support token streaming yet.")
        chat_messages = messages or [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        payload = chat_messages_to_responses_payload(
            model=self.model,
            messages=chat_messages,
            max_completion_tokens=self.max_completion_tokens,
            reasoning_effort=self.reasoning_effort,
            response_format_json_object=self.response_format_json_object,
        )
        backend = CodexBackend(
            CodexAuthProvider(self.auth_file),
            base_url=self.base_url,
            timeout_seconds=self.timeout_seconds,
        )
        return await asyncio.to_thread(lambda: collect_response_completion(backend.create_response_stream(payload), self.model))


__all__ = [
    "CodexAuthError",
    "CodexAuthProvider",
    "CodexBackend",
    "CodexCredentials",
    "CodexProviderError",
    "CodexResponsesClient",
    "chat_messages_to_responses_payload",
    "collect_response_completion",
    "iter_sse_events",
    "normalize_model",
    "token_is_fresh",
    "usage_to_completion_usage",
]
