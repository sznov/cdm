from __future__ import annotations

import hashlib
import ipaddress
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from core.artifact_versions import (
    RESULT_RECORD_SCHEMA_VERSION,
    RUN_RECORD_SCHEMA_VERSION,
    normalize_run_record,
)
from core.build_provenance import BuildIdentity, current_build_identity
from core.config_safety import (
    provider_environment_endpoint_url,
    validate_endpoint_url,
    validate_secret_free_mapping,
)
from core.schemas import StructuredModel
from core.providers.factory import provider_descriptor
from core.providers.nvidia_nim_catalog import (
    canonical_nim_model_id,
    metadata_for_nvidia_nim_model,
)
from core.providers.nvidia_nim_discovery import read_bundled_nvidia_nim_catalog
from harnesses.contracts import (
    DirectBaselineEffectiveConfig,
    EffectiveHarnessRunSpec,
    HarnessExecutorId,
    StructuredPatchEffectiveConfig,
)
from harnesses.direct_baseline.prompt_profiles import (
    DIRECT_PROMPT_TEMPLATE_REVISIONS,
    direct_prompt_profile,
)
from harnesses.structured_patch.correction_templates import (
    CORRECTION_TEMPLATE_REVISIONS,
    correction_template_by_id,
)
from harnesses.structured_patch.coverage_prompts import PLAN_COVERAGE_CRITIC_SYSTEM_PROMPT
from harnesses.structured_patch.draft_prompts import SIMPLE_DRAFT_SYSTEM_PROMPT
from harnesses.structured_patch.language_repair_prompts import (
    STRUCTURED_LANGUAGE_REPAIR_SYSTEM_PROMPT,
    STRUCTURED_LANGUAGE_REPAIR_USER_TEMPLATE,
)
from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    UNICODE_NFKC_NAME_POLICY,
)
from harnesses.structured_patch.runner_prompt_profile import (
    async_op_patch_prompt_profile,
)


RUN_PROVENANCE_SCHEMA_VERSION = 1
HARNESS_RUN_ARTIFACT_SCHEMA_VERSION = 2
RUN_EVENT_SCHEMA_VERSION = 2


def canonical_json_bytes(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PromptProtocolIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str = Field(min_length=1)
    profile_revision: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    correction_template_id: str | None = None
    correction_template_revision: str | None = None
    correction_template_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_complete_correction_identity(self) -> PromptProtocolIdentity:
        correction_values = (
            self.correction_template_id,
            self.correction_template_revision,
            self.correction_template_sha256,
        )
        if any(value is not None for value in correction_values) and not all(
            isinstance(value, str) and value for value in correction_values
        ):
            raise ValueError("Correction template identity must be either complete or absent.")
        return self


class WorkflowProtocolIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workflow_id: str = Field(min_length=1)
    definition_revision: str = Field(min_length=1)
    executor_id: HarnessExecutorId
    effective_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    whole_harness_max_attempts: int = Field(ge=1)
    prompt: PromptProtocolIdentity


ProviderCatalogDelivery = Literal["live", "persisted", "bundled", "not_applicable"]
ProviderCatalogOrigin = Literal["live", "bundled", "not_applicable"]
ProviderEndpointClass = Literal["provider_default", "provider_compatible", "local", "custom"]


class ProviderExecutionIdentity(BaseModel):
    """Public, secret-free provider inputs captured before execution starts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    binding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    endpoint_class: ProviderEndpointClass
    catalog_source: ProviderCatalogDelivery = "not_applicable"
    catalog_origin: ProviderCatalogOrigin = "not_applicable"
    catalog_retrieved_at_utc: str | None = None
    catalog_stale: bool | None = None
    catalog_unverified: bool | None = None
    selected_model_metadata: dict[str, JsonValue] | None = None
    selected_model_metadata_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def require_consistent_catalog_identity(self) -> ProviderExecutionIdentity:
        if self.catalog_source == "not_applicable":
            if (
                self.catalog_origin != "not_applicable"
                or self.catalog_retrieved_at_utc is not None
                or self.catalog_stale is not None
                or self.catalog_unverified is not None
                or self.selected_model_metadata is not None
            ):
                raise ValueError("A provider without a catalog cannot report catalog provenance.")
        else:
            if not self.catalog_retrieved_at_utc:
                raise ValueError("Catalog-backed provider provenance requires a retrieval time.")
            if not isinstance(self.catalog_stale, bool) or not isinstance(
                self.catalog_unverified,
                bool,
            ):
                raise ValueError("Catalog-backed provider provenance requires status flags.")
            if self.catalog_source in {"live", "persisted"}:
                if self.catalog_origin != "live" or self.catalog_unverified:
                    raise ValueError("Live-derived catalog provenance must retain live origin.")
                if self.catalog_source == "live" and self.catalog_stale:
                    raise ValueError("A live catalog cannot be stale.")
            elif (
                self.catalog_origin != "bundled"
                or not self.catalog_stale
                or not self.catalog_unverified
            ):
                raise ValueError("Bundled catalog provenance must be stale and unverified.")
        if self.selected_model_metadata is None:
            if self.selected_model_metadata_sha256 is not None:
                raise ValueError("Selected metadata hash cannot exist without selected metadata.")
        elif self.selected_model_metadata_sha256 != canonical_sha256(self.selected_model_metadata):
            raise ValueError("Selected provider metadata hash does not match its payload.")
        if self.selected_model_metadata is not None:
            validate_secret_free_mapping(
                self.selected_model_metadata,
                path="provider.selected_model_metadata",
            )
        return self

    def execution_catalog_entries(self) -> list[dict[str, Any]] | None:
        if self.selected_model_metadata is None:
            return None
        if self.selected_model_metadata_sha256 != canonical_sha256(
            self.selected_model_metadata
        ):
            raise ValueError("Selected provider metadata changed after provenance was sealed.")
        return [deepcopy(self.selected_model_metadata)]


class SchemaProtocolIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_record_schema_version: Literal[3] = RUN_RECORD_SCHEMA_VERSION
    result_record_schema_version: Literal[2] = RESULT_RECORD_SCHEMA_VERSION
    run_event_schema_version: Literal[2] = RUN_EVENT_SCHEMA_VERSION
    effective_spec_schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    structured_model_schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RunProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = RUN_PROVENANCE_SCHEMA_VERSION
    specification_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    workflow: WorkflowProtocolIdentity
    provider: ProviderExecutionIdentity
    schemas: SchemaProtocolIdentity
    build: BuildIdentity
    integrity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify_integrity(self) -> RunProvenance:
        payload = self.model_dump(mode="json", exclude={"integrity_sha256"})
        if self.integrity_sha256 != canonical_sha256(payload):
            raise ValueError("Run provenance integrity hash does not match its payload.")
        return self


class HarnessRunArtifact(BaseModel):
    """Inspectable protocol envelope shared by scripted harness entry points."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = HARNESS_RUN_ARTIFACT_SCHEMA_VERSION
    effective_harness_run_spec: EffectiveHarnessRunSpec
    provenance: RunProvenance
    whole_harness_max_attempts: int = Field(ge=1)

    @model_validator(mode="after")
    def require_matching_protocol(self) -> HarnessRunArtifact:
        spec = self.effective_harness_run_spec
        protocol = self.provenance.workflow
        if self.whole_harness_max_attempts != protocol.whole_harness_max_attempts:
            raise ValueError("Whole-harness retry count differs from provenance.")
        if canonical_sha256(spec) != protocol.effective_spec_sha256:
            raise ValueError("Effective harness specification hash does not match provenance.")
        if (
            spec.harness_id != protocol.workflow_id
            or spec.definition_revision != protocol.definition_revision
            or spec.executor_id != protocol.executor_id
        ):
            raise ValueError("Harness identity differs from provenance.")
        binding = spec.model_bindings["default"]
        if binding.provider != self.provenance.provider.provider_id:
            raise ValueError("Provider identity differs from the effective harness specification.")
        if binding.model != self.provenance.provider.model_id:
            raise ValueError("Model identity differs from the effective harness specification.")
        if canonical_sha256(binding) != self.provenance.provider.binding_sha256:
            raise ValueError("Model binding hash differs from the effective harness specification.")
        if not binding.base_url or (
            endpoint_class_for_provider(binding.provider, binding.base_url)
            != self.provenance.provider.endpoint_class
        ):
            raise ValueError("Endpoint class differs from the effective harness specification.")
        return self


class RecordedProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    effective_harness_run_spec: EffectiveHarnessRunSpec
    specification: str
    provenance: RunProvenance


def endpoint_class_for_provider(provider_id: str, endpoint: str) -> ProviderEndpointClass:
    hostname = (urlsplit(endpoint).hostname or "").strip().lower()
    if hostname == "localhost":
        return "local"
    try:
        if hostname and ipaddress.ip_address(hostname).is_loopback:
            return "local"
    except ValueError:
        pass
    default = str(provider_descriptor(provider_id).default_base_url or "").rstrip("/")
    if endpoint.rstrip("/") == default:
        return "provider_default"
    official_suffixes = {
        "gemini": ("googleapis.com",),
        "codex": ("chatgpt.com", "openai.com"),
        "nvidia_nim": ("nvidia.com",),
    }
    if any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in official_suffixes.get(provider_id, ())
    ):
        return "provider_compatible"
    return "custom"


def with_frozen_default_binding(
    spec: EffectiveHarnessRunSpec,
    *,
    model_id: str,
    endpoint: str,
) -> EffectiveHarnessRunSpec:
    payload = spec.model_dump(mode="json")
    binding = dict(payload["model_bindings"]["default"])
    binding.update(model=model_id, base_url=endpoint.rstrip("/"))
    payload["model_bindings"] = {"default": binding}
    effective_config = dict(payload["effective_config"])
    effective_config.update(
        provider=binding["provider"],
        model=model_id,
        gemini_base_url=endpoint.rstrip("/"),
        model_bindings={"default": binding},
    )
    payload["effective_config"] = effective_config
    return EffectiveHarnessRunSpec.model_validate(payload).detached_copy()


def materialize_script_execution(
    spec: EffectiveHarnessRunSpec,
) -> tuple[EffectiveHarnessRunSpec, ProviderExecutionIdentity]:
    """Freeze the inputs actually consumed by catalog-independent batch scripts."""

    binding = spec.model_bindings["default"]
    descriptor = provider_descriptor(binding.provider)
    environment_endpoint = provider_environment_endpoint_url(binding.provider)
    binding_endpoint = str(binding.base_url or "").strip().rstrip("/")
    default_endpoint = str(descriptor.default_base_url or "").strip().rstrip("/")
    endpoint = (
        environment_endpoint
        if environment_endpoint and binding_endpoint in {"", default_endpoint}
        else binding_endpoint or environment_endpoint or default_endpoint
    )
    if not endpoint:
        raise ValueError(f"Provider {binding.provider!r} has no effective endpoint.")
    validate_endpoint_url(endpoint, field_name=f"{binding.provider} effective endpoint")
    model_id = binding.model
    selected_metadata: dict[str, Any] | None = None
    catalog_fields: dict[str, Any] = {
        "catalog_source": "not_applicable",
        "catalog_origin": "not_applicable",
    }
    if binding.provider == "nvidia_nim":
        catalog = read_bundled_nvidia_nim_catalog()
        model_id = canonical_nim_model_id(model_id, catalog.models)
        selected_metadata = metadata_for_nvidia_nim_model(model_id, catalog.models)
        serialized = catalog.detached_dict()
        catalog_fields = {
            "catalog_source": catalog.source,
            "catalog_origin": catalog.origin,
            "catalog_retrieved_at_utc": serialized["retrieved_at_utc"],
            "catalog_stale": catalog.stale,
            "catalog_unverified": catalog.unverified,
        }
    frozen_spec = with_frozen_default_binding(
        spec,
        model_id=model_id,
        endpoint=endpoint,
    )
    identity = ProviderExecutionIdentity(
        provider_id=binding.provider,
        model_id=model_id,
        binding_sha256=canonical_sha256(frozen_spec.model_bindings["default"]),
        endpoint_class=endpoint_class_for_provider(binding.provider, endpoint),
        selected_model_metadata=selected_metadata,
        selected_model_metadata_sha256=(
            canonical_sha256(selected_metadata) if selected_metadata is not None else None
        ),
        **catalog_fields,
    )
    return frozen_spec, identity


def _prompt_identity(spec: EffectiveHarnessRunSpec) -> PromptProtocolIdentity:
    config = spec.effective_config
    if isinstance(config, DirectBaselineEffectiveConfig):
        profile = direct_prompt_profile(config.prompt_profile)
        prompt_content = {
            "system_prompt": profile.system_prompt,
            "user_template": profile.user_template,
        }
        return PromptProtocolIdentity(
            profile_id=profile.id,
            profile_revision=DIRECT_PROMPT_TEMPLATE_REVISIONS[profile.id],
            content_sha256=canonical_sha256(prompt_content),
        )

    if not isinstance(config, StructuredPatchEffectiveConfig):  # pragma: no cover - typed spec guard
        raise TypeError("Unsupported effective harness configuration.")
    name_policy = (
        UNICODE_NFKC_NAME_POLICY
        if spec.executor_id == HarnessExecutorId.STRUCTURED_PATCH_REFINED
        else LEGACY_ASCII_NAME_POLICY
    )
    profile = async_op_patch_prompt_profile(
        direct_microop_judge=config.direct_microop_judge,
        name_policy=name_policy,
    )
    prompt_content: dict[str, Any] = {
        "draft_system_prompt": SIMPLE_DRAFT_SYSTEM_PROMPT,
        "draft_user_template": profile.draft_user_template,
        "coverage_system_prompt": PLAN_COVERAGE_CRITIC_SYSTEM_PROMPT,
        "coverage_user_template": profile.coverage_critic_user_template,
        "patch_system_prompt": profile.patch_clerk_system_prompt,
        "patch_user_template": profile.patch_clerk_user_template,
    }
    if config.language_repair:
        prompt_content["language_repair_system_prompt"] = STRUCTURED_LANGUAGE_REPAIR_SYSTEM_PROMPT
        prompt_content["language_repair_user_template"] = STRUCTURED_LANGUAGE_REPAIR_USER_TEMPLATE

    correction_id = config.correction_template_id if config.auto_correction_sequence else None
    correction_revision: str | None = None
    correction_sha256: str | None = None
    if correction_id:
        template = correction_template_by_id(correction_id)
        if template is None or correction_id not in CORRECTION_TEMPLATE_REVISIONS:
            raise ValueError(f"Unknown correction template for provenance: {correction_id}")
        correction_revision = CORRECTION_TEMPLATE_REVISIONS[correction_id]
        if name_policy.preserves_unicode:
            correction_revision = f"{correction_revision}+unicode-nfkc-v1"
        correction_sha256 = canonical_sha256(
            {
                "template": template,
                "system_prompt": profile.correction_patch_system_prompt,
                "user_template": profile.correction_patch_user_template,
            }
        )
    return PromptProtocolIdentity(
        profile_id=f"structured_patch_{profile.profile_id}",
        profile_revision=profile.profile_revision,
        content_sha256=canonical_sha256(prompt_content),
        correction_template_id=correction_id,
        correction_template_revision=correction_revision,
        correction_template_sha256=correction_sha256,
    )


def schema_protocol_identity() -> SchemaProtocolIdentity:
    return SchemaProtocolIdentity(
        effective_spec_schema_sha256=canonical_sha256(EffectiveHarnessRunSpec.model_json_schema()),
        structured_model_schema_sha256=canonical_sha256(StructuredModel.model_json_schema()),
    )


def build_run_provenance(
    *,
    spec: EffectiveHarnessRunSpec,
    specification: str,
    provider: ProviderExecutionIdentity,
    whole_harness_max_attempts: int = 1,
    build: BuildIdentity | None = None,
) -> RunProvenance:
    attempts = max(1, int(whole_harness_max_attempts))
    unsealed = {
        "schema_version": RUN_PROVENANCE_SCHEMA_VERSION,
        "specification_sha256": text_sha256(specification),
        "workflow": WorkflowProtocolIdentity(
            workflow_id=spec.harness_id,
            definition_revision=spec.definition_revision,
            executor_id=spec.executor_id,
            effective_spec_sha256=canonical_sha256(spec),
            whole_harness_max_attempts=attempts,
            prompt=_prompt_identity(spec),
        ).model_dump(mode="json"),
        "provider": provider.model_dump(mode="json"),
        "schemas": schema_protocol_identity().model_dump(mode="json"),
        "build": (build or current_build_identity()).detached_dict(),
    }
    return RunProvenance.model_validate(
        {**unsealed, "integrity_sha256": canonical_sha256(unsealed)}
    )


def harness_run_artifact(
    *,
    spec: EffectiveHarnessRunSpec,
    specification: str,
    provider: ProviderExecutionIdentity,
    whole_harness_max_attempts: int,
    build: BuildIdentity | None = None,
) -> HarnessRunArtifact:
    return HarnessRunArtifact(
        effective_harness_run_spec=spec.detached_copy(),
        provenance=build_run_provenance(
            spec=spec,
            specification=specification,
            provider=provider,
            whole_harness_max_attempts=whole_harness_max_attempts,
            build=build,
        ),
        whole_harness_max_attempts=max(1, int(whole_harness_max_attempts)),
    )


def validate_recorded_protocol(
    *,
    spec: EffectiveHarnessRunSpec,
    specification: str,
    provenance: RunProvenance,
) -> None:
    if text_sha256(specification) != provenance.specification_sha256:
        raise ValueError("Recorded specification hash does not match specification.txt.")
    protocol = provenance.workflow
    if canonical_sha256(spec) != protocol.effective_spec_sha256:
        raise ValueError("Recorded effective harness specification hash does not match provenance.")
    if (
        spec.harness_id != protocol.workflow_id
        or spec.definition_revision != protocol.definition_revision
        or spec.executor_id != protocol.executor_id
    ):
        raise ValueError("Recorded workflow identity does not match its effective specification.")
    current_prompt = _prompt_identity(spec)
    if current_prompt != protocol.prompt:
        raise ValueError("Recorded prompt/template identity does not match this executable protocol.")
    if schema_protocol_identity() != provenance.schemas:
        raise ValueError("Recorded schema identity is not supported by this release.")
    binding = spec.model_bindings["default"]
    if binding.provider != provenance.provider.provider_id or binding.model != provenance.provider.model_id:
        raise ValueError("Recorded provider/model identity does not match its effective specification.")
    if canonical_sha256(binding) != provenance.provider.binding_sha256:
        raise ValueError("Recorded model binding hash does not match its effective specification.")
    if not binding.base_url or (
        endpoint_class_for_provider(binding.provider, binding.base_url)
        != provenance.provider.endpoint_class
    ):
        raise ValueError("Recorded endpoint class does not match its effective specification.")


def load_recorded_protocol(run_dir: Path) -> RecordedProtocol:
    """Load one exact run protocol without consulting catalogs or live discovery."""

    run_path = Path(run_dir) / "run.json"
    try:
        record_payload = json.loads(run_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read recorded run protocol: {exc}") from exc
    record = normalize_run_record(record_payload)
    spec = EffectiveHarnessRunSpec.model_validate(record.get("effective_harness_run_spec"))
    provenance = RunProvenance.model_validate(record.get("provenance"))
    if record.get("runtime_harness_id") != spec.harness_id:
        raise ValueError("Recorded run harness ID does not match its effective specification.")
    if record.get("harness_definition_revision") != spec.definition_revision:
        raise ValueError("Recorded run harness revision does not match its effective specification.")
    if record.get("provider") != spec.model_bindings["default"].provider:
        raise ValueError("Recorded run provider does not match its effective specification.")
    if record.get("model") != spec.model_bindings["default"].model:
        raise ValueError("Recorded run model does not match its effective specification.")
    if canonical_sha256(record.get("model_bindings")) != canonical_sha256(
        spec.model_dump(mode="json")["model_bindings"]
    ):
        raise ValueError("Recorded run bindings do not match its effective specification.")
    request_payload = record.get("request")
    if not isinstance(request_payload, dict):
        raise ValueError("Recorded run request is missing.")
    if request_payload.get("specification_path") != "specification.txt":
        raise ValueError("Recorded specification path must be specification.txt.")
    specification_path = Path(run_dir) / "specification.txt"
    try:
        specification = specification_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Cannot read recorded specification: {exc}") from exc
    if request_payload.get("specification_sha256") != text_sha256(specification):
        raise ValueError("Recorded request specification hash does not match specification.txt.")
    if request_payload.get("specification_length") != len(specification):
        raise ValueError("Recorded request specification length does not match specification.txt.")
    validate_recorded_protocol(spec=spec, specification=specification, provenance=provenance)
    return RecordedProtocol(
        effective_harness_run_spec=spec.detached_copy(),
        specification=specification,
        provenance=provenance.model_copy(deep=True),
    )


__all__ = [
    "HARNESS_RUN_ARTIFACT_SCHEMA_VERSION",
    "RUN_PROVENANCE_SCHEMA_VERSION",
    "HarnessRunArtifact",
    "PromptProtocolIdentity",
    "ProviderExecutionIdentity",
    "ProviderEndpointClass",
    "RecordedProtocol",
    "RunProvenance",
    "SchemaProtocolIdentity",
    "WorkflowProtocolIdentity",
    "build_run_provenance",
    "canonical_sha256",
    "endpoint_class_for_provider",
    "harness_run_artifact",
    "load_recorded_protocol",
    "materialize_script_execution",
    "schema_protocol_identity",
    "text_sha256",
    "validate_recorded_protocol",
    "with_frozen_default_binding",
]
