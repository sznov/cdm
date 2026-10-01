from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


REDACTED = "[REDACTED]"
_RAW_SECRET_REPLACEMENT_MIN_LENGTH = 16

_PROVIDER_ENDPOINT_ENVIRONMENT_VARIABLES = {
    "codex": "CODEX_BASE_URL",
    "gemini": "GEMINI_OPENAI_BASE_URL",
    "nvidia_nim": "NVIDIA_NIM_BASE_URL",
}

_SAFE_TOKEN_PARAMETER_KEYS = {
    "cachedtokens",
    "completiontokens",
    "inputtokens",
    "maxtokens",
    "maxcompletiontokens",
    "maxoutputtokens",
    "mintokens",
    "numtokens",
    "outputtokens",
    "prompttokens",
    "reasoningtokens",
    "tokencount",
    "tokenbudget",
    "totaltokens",
}

_SENSITIVE_EXACT_KEYS = {
    "apikey",
    "apitoken",
    "auth",
    "authentication",
    "authorization",
    "authfile",
    "authpath",
    "bearer",
    "bearertoken",
    "capability",
    "credential",
    "credentials",
    "cookie",
    "cookies",
    "key",
    "lease",
    "password",
    "passwd",
    "privatekey",
    "pwd",
    "refreshtoken",
    "runtimecontrol",
    "secret",
    "secretkey",
    "signingkey",
    "token",
    "tokens",
}

_SENSITIVE_QUERY_EXACT_KEYS = {
    "code",
    "key",
    "sas",
    "sig",
    "signature",
}

_URL_PATTERN = re.compile(r"(?P<url>(?:https?|wss?)://[^\s\"'<>]+)", re.IGNORECASE)
_BEARER_PATTERN = re.compile(r"\bBearer\s+[^\s,;\"']+", re.IGNORECASE)
_AUTHORIZATION_VALUE_PATTERN = re.compile(
    r"(?P<prefix>\bAuthorization[\"']?\s*[:=]\s*[\"']?)"
    r"(?:(?:Bearer|Basic)\s+)?[^\s,;\"']+",
    re.IGNORECASE,
)
_NAMED_SECRET_VALUE_PATTERN = re.compile(
    r"(?P<prefix>\b(?:"
    r"api[-_. ]?key|api[-_. ]?token|access[-_. ]?key(?:[-_. ]?id)?|"
    r"access[-_. ]?token|refresh[-_. ]?token|id[-_. ]?token|session[-_. ]?token|"
    r"auth[-_. ]?file|bearer[-_. ]?token|capability|client[-_. ]?secret|"
    r"credential(?:s)?|lease|password|passwd|private[-_. ]?key|runtime[-_. ]?control|"
    r"secret(?:[-_. ]?access)?[-_. ]?key|"
    r"signing[-_. ]?key|token"
    r")[\"']?\s*[:=]\s*[\"']?)"
    r"[^\s,;&\"']+",
    re.IGNORECASE,
)


class UnsafeConfigurationError(ValueError):
    """Raised when persisted runtime configuration could contain credentials."""


def canonical_config_key(value: object) -> str:
    """Fold case and punctuation so spelling variants share one policy key."""

    return "".join(character for character in str(value).casefold() if character.isalnum())


def is_sensitive_config_key(value: object) -> bool:
    canonical = canonical_config_key(value)
    if not canonical or canonical in _SAFE_TOKEN_PARAMETER_KEYS:
        return False
    if canonical in _SENSITIVE_EXACT_KEYS:
        return True
    if any(
        marker in canonical
        for marker in (
            "accesskey",
            "apikey",
            "authorization",
            "credential",
            "password",
            "privatekey",
            "secret",
        )
    ):
        return True
    if canonical.startswith("authfile") or canonical.endswith("authfile"):
        return True
    if canonical.endswith(("accesstoken", "refreshtoken", "bearertoken")):
        return True
    if canonical.endswith(("clientsecret", "privatekey", "secretkey", "signingkey")):
        return True
    return canonical.endswith(("token", "tokens"))


def is_sensitive_query_key(value: object) -> bool:
    canonical = canonical_config_key(value)
    return is_sensitive_config_key(value) or canonical in _SENSITIVE_QUERY_EXACT_KEYS


def is_endpoint_url_key(value: object) -> bool:
    canonical = canonical_config_key(value)
    return (
        canonical in {"endpoint", "url"}
        or canonical.endswith("baseurl")
        or canonical.endswith("endpointurl")
        or canonical.endswith("invokeurl")
        or canonical.endswith("urltemplate")
    )


def validate_endpoint_url(
    value: object,
    *,
    field_name: str = "endpoint URL",
    require_absolute: bool = True,
) -> None:
    """Reject invalid or credential-bearing endpoint forms without echoing them."""

    if value in (None, ""):
        return
    if not isinstance(value, str):
        raise UnsafeConfigurationError(f"{field_name} must be a string.")
    try:
        parsed = urlsplit(value)
        username = parsed.username
        password = parsed.password
        query = parse_qsl(parsed.query, keep_blank_values=True)
    except ValueError as exc:
        raise UnsafeConfigurationError(f"{field_name} is not a valid endpoint URL.") from exc
    if require_absolute and (
        parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname
    ):
        raise UnsafeConfigurationError(
            f"{field_name} must be an absolute HTTP or HTTPS URL."
        )
    if username is not None or password is not None:
        raise UnsafeConfigurationError(f"{field_name} must not include URL user information.")
    if parsed.fragment:
        raise UnsafeConfigurationError(f"{field_name} must not include a URL fragment.")
    for query_key, _query_value in query:
        if is_sensitive_query_key(query_key):
            raise UnsafeConfigurationError(
                f"{field_name} must not include a sensitive query key."
            )


def provider_environment_endpoint_url(provider: str) -> str | None:
    """Return one validated provider environment endpoint, when configured."""

    normalized_provider = str(provider).strip().lower()
    environment_name = _PROVIDER_ENDPOINT_ENVIRONMENT_VARIABLES.get(
        normalized_provider
    )
    if not environment_name:
        return None
    value = os.getenv(environment_name, "").strip()
    if not value:
        return None
    validate_endpoint_url(value, field_name=environment_name)
    return value.rstrip("/")


def validate_secret_free_mapping(value: object, *, path: str) -> None:
    """Recursively reject credential keys and unsafe endpoint URLs."""

    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = str(raw_key)
            nested_path = f"{path}.{key}"
            if is_sensitive_config_key(key):
                raise UnsafeConfigurationError(
                    f"Credential-bearing configuration is not allowed at {nested_path}; "
                    "use environment credentials instead."
                )
            if is_endpoint_url_key(key) and nested not in (None, ""):
                validate_endpoint_url(
                    nested,
                    field_name=nested_path,
                    require_absolute=False,
                )
            validate_secret_free_mapping(nested, path=nested_path)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested in enumerate(value):
            validate_secret_free_mapping(nested, path=f"{path}[{index}]")


def selected_provider_endpoint_url(
    provider: str,
    explicit_url: str | None,
) -> str | None:
    """Resolve and validate only the endpoint the selected provider will use."""

    normalized_provider = str(provider).strip().lower()
    environment_name = _PROVIDER_ENDPOINT_ENVIRONMENT_VARIABLES.get(
        normalized_provider
    )
    explicit_value = explicit_url.strip() if isinstance(explicit_url, str) else explicit_url
    environment_value = provider_environment_endpoint_url(normalized_provider)
    value = explicit_value or environment_value or None
    if value:
        validate_endpoint_url(
            value,
            field_name=environment_name or f"{provider} base URL",
        )
    return value


def _credential_environment_values() -> tuple[str, ...]:
    values = {
        value
        for name, value in os.environ.items()
        if value and is_sensitive_config_key(name)
    }
    return tuple(sorted(values, key=len, reverse=True))


def _redact_configured_values(text: str) -> str:
    redacted = text
    for secret in _credential_environment_values():
        if len(secret) >= _RAW_SECRET_REPLACEMENT_MIN_LENGTH:
            redacted = redacted.replace(secret, REDACTED)
        else:
            redacted = re.sub(
                rf"(?<![A-Za-z0-9]){re.escape(secret)}(?![A-Za-z0-9])",
                REDACTED,
                redacted,
            )
    return redacted


def _redact_url_match(
    match: re.Match[str],
    *,
    redact_fragment: bool,
) -> str:
    raw_url = match.group("url")
    trailing = ""
    while raw_url and raw_url[-1] in ".,;)]}":
        trailing = raw_url[-1] + trailing
        raw_url = raw_url[:-1]
    try:
        parsed = urlsplit(raw_url)
        userinfo = parsed.username is not None or parsed.password is not None
        sensitive_query = any(
            is_sensitive_query_key(key)
            for key, _value in parse_qsl(parsed.query, keep_blank_values=True)
        )
        if not userinfo and not sensitive_query and not (redact_fragment and parsed.fragment):
            return raw_url + trailing
        authority = parsed.netloc.rsplit("@", 1)[-1]
        netloc = f"{REDACTED}@{authority}" if userinfo else parsed.netloc
        query_items = [
            (key, REDACTED if is_sensitive_query_key(key) else value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        ]
        query = urlencode(query_items, doseq=True)
        fragment = "" if (redact_fragment or userinfo or sensitive_query) else parsed.fragment
        return urlunsplit((parsed.scheme, netloc, parsed.path, query, fragment)) + trailing
    except ValueError:
        sanitized = raw_url.split("#", 1)[0] if redact_fragment else raw_url
        sanitized = re.sub(
            r"(?i)([?&](?:code|key|sas|sig|signature)=)[^&\s]+",
            rf"\g<1>{REDACTED}",
            sanitized,
        )
        return re.sub(
            r"(?<=://)[^/\s@]+@",
            f"{REDACTED}@",
            sanitized,
        ) + trailing


def redact_sensitive_text(
    value: object,
    *,
    redact_named_values: bool = True,
    redact_url_fragments: bool = True,
) -> str:
    """Redact configured credentials and common credential-bearing text forms."""

    text = str(value)
    text = _redact_configured_values(text)
    text = _URL_PATTERN.sub(
        lambda match: _redact_url_match(
            match,
            redact_fragment=redact_url_fragments,
        ),
        text,
    )
    text = _AUTHORIZATION_VALUE_PATTERN.sub(
        lambda match: f"{match.group('prefix')}{REDACTED}",
        text,
    )
    text = _BEARER_PATTERN.sub(f"Bearer {REDACTED}", text)
    if redact_named_values:
        text = _NAMED_SECRET_VALUE_PATTERN.sub(
            lambda match: f"{match.group('prefix')}{REDACTED}",
            text,
        )
    return text


def redact_sensitive_value(value: Any) -> Any:
    """Return a detached recursively redacted JSON-like value."""

    if isinstance(value, Mapping):
        return {
            key: REDACTED if is_sensitive_config_key(key) else redact_sensitive_value(nested)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_value(item) for item in value)
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def redact_persisted_value(value: Any, *, error_context: bool = False) -> Any:
    """Redact persisted structures without rewriting ordinary research content."""

    if isinstance(value, Mapping):
        redacted: dict[Any, Any] = {}
        for key, nested in value.items():
            canonical = canonical_config_key(key)
            if is_sensitive_config_key(key):
                redacted[key] = REDACTED
                continue
            nested_is_error = error_context or canonical in {
                "detail",
                "error",
                "exception",
                "failure",
                "lasterror",
            }
            redacted[key] = redact_persisted_value(
                nested,
                error_context=nested_is_error,
            )
        return redacted
    if isinstance(value, list):
        return [redact_persisted_value(item, error_context=error_context) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_persisted_value(item, error_context=error_context) for item in value)
    if isinstance(value, str):
        return redact_sensitive_text(
            value,
            redact_named_values=error_context,
            redact_url_fragments=error_context,
        )
    return value


def safe_exception_detail(error: BaseException) -> str:
    return redact_sensitive_text(str(error) or repr(error))


__all__ = [
    "REDACTED",
    "UnsafeConfigurationError",
    "canonical_config_key",
    "is_endpoint_url_key",
    "is_sensitive_config_key",
    "is_sensitive_query_key",
    "redact_sensitive_text",
    "redact_sensitive_value",
    "redact_persisted_value",
    "safe_exception_detail",
    "provider_environment_endpoint_url",
    "selected_provider_endpoint_url",
    "validate_endpoint_url",
    "validate_secret_free_mapping",
]
