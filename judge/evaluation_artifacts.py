from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from judge.evaluation_contracts import (
    ArtifactDescriptor,
    DatasetCase,
    EvaluationDataset,
    MaterializedArtifact,
)


WINDOWS_REPARSE_ATTRIBUTE = 0x0400


class EvaluationArtifactError(ValueError):
    pass


def canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def write_json_atomic(path: Path, payload: Any) -> None:
    write_bytes_atomic(path, canonical_json_bytes(payload))


def _has_reparse_attribute(path_stat: os.stat_result) -> bool:
    attributes = int(getattr(path_stat, "st_file_attributes", 0))
    return bool(attributes & WINDOWS_REPARSE_ATTRIBUTE)


def _path_prefixes(path: Path) -> list[Path]:
    absolute = Path(os.path.abspath(path))
    anchor = Path(absolute.anchor)
    current = anchor
    prefixes: list[Path] = []
    for part in absolute.parts[1:]:
        current = current / part
        prefixes.append(current)
    return prefixes


def assert_unlinked_regular_file(path: Path, *, label: str) -> os.stat_result:
    for component in _path_prefixes(path):
        try:
            component_stat = os.lstat(component)
        except FileNotFoundError as exc:
            raise EvaluationArtifactError(f"{label} does not exist") from exc
        if stat.S_ISLNK(component_stat.st_mode) or _has_reparse_attribute(component_stat):
            raise EvaluationArtifactError(f"{label} uses a linked or reparse-backed path")
    try:
        path_stat = os.lstat(path)
    except FileNotFoundError as exc:
        raise EvaluationArtifactError(f"{label} does not exist") from exc
    if not stat.S_ISREG(path_stat.st_mode):
        raise EvaluationArtifactError(f"{label} must be a regular file")
    return path_stat


def resolve_source_path(
    raw_path: str,
    *,
    manifest_dir: Path,
    allow_absolute: bool = True,
) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        if not allow_absolute:
            raise EvaluationArtifactError("adapter-produced artifact paths must be relative")
        return Path(os.path.abspath(candidate))
    if any(part in {"", "."} for part in candidate.parts):
        raise EvaluationArtifactError(f"unsafe relative artifact path: {raw_path!r}")
    if not allow_absolute and ".." in candidate.parts:
        raise EvaluationArtifactError(f"unsafe relative artifact path: {raw_path!r}")
    return Path(os.path.abspath(manifest_dir / candidate))


def stable_file_bytes(
    path: Path,
    *,
    label: str,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
) -> bytes:
    before = assert_unlinked_regular_file(path, label=label)
    payload = path.read_bytes()
    after = assert_unlinked_regular_file(path, label=label)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_after or len(payload) != after.st_size:
        raise EvaluationArtifactError(f"{label} changed while it was being prepared")
    actual_hash = sha256_bytes(payload)
    if expected_sha256 is not None and actual_hash != expected_sha256:
        raise EvaluationArtifactError(f"{label} SHA-256 does not match the manifest")
    if expected_size is not None and len(payload) != expected_size:
        raise EvaluationArtifactError(f"{label} size does not match the manifest")
    return payload


def storage_name(identifier: str) -> str:
    normalized = unicodedata.normalize("NFKD", identifier)
    ascii_text = normalized.encode("ascii", errors="ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").lower()
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:10]
    return f"{(slug or 'item')[:48]}-{digest}"


def artifact_filename(role: str, source_path: Path) -> str:
    suffix = "".join(source_path.suffixes)
    safe_suffix = suffix if suffix and len(suffix) <= 32 else ""
    return f"{storage_name(role)}{safe_suffix}"


def materialize_artifact(
    descriptor: ArtifactDescriptor,
    *,
    manifest_dir: Path,
    destination: Path,
    work_dir: Path,
    label: str,
    allow_absolute: bool = True,
) -> MaterializedArtifact:
    source = resolve_source_path(
        descriptor.path,
        manifest_dir=manifest_dir,
        allow_absolute=allow_absolute,
    )
    payload = stable_file_bytes(
        source,
        label=label,
        expected_sha256=descriptor.sha256,
        expected_size=descriptor.size_bytes,
    )
    try:
        os.lstat(destination)
        destination_exists = True
    except FileNotFoundError:
        destination_exists = False
    if destination_exists:
        existing = stable_file_bytes(
            destination,
            label=f"prepared destination for {label}",
        )
        if existing != payload:
            raise EvaluationArtifactError(
                f"prepared destination for {label} conflicts with source bytes"
            )
    else:
        write_bytes_atomic(destination, payload)
    relative_path = destination.relative_to(work_dir).as_posix()
    return MaterializedArtifact(
        path=relative_path,
        media_type=descriptor.media_type,
        schema_id=descriptor.schema_id,
        sha256=sha256_bytes(payload),
        size_bytes=len(payload),
    )


def load_dataset(path: Path) -> EvaluationDataset:
    payload = stable_file_bytes(path, label="evaluation dataset manifest")
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationArtifactError("evaluation dataset manifest is not valid UTF-8 JSON") from exc
    return EvaluationDataset.model_validate(decoded)


def _materialize_case_artifacts(
    case: DatasetCase,
    *,
    dataset_dir: Path,
    work_dir: Path,
) -> dict[str, Any]:
    case_storage = storage_name(case.case_id)
    output: dict[str, Any] = {
        "case_id": case.case_id,
        "storage_name": case_storage,
        "inputs": {},
        "references": {},
        "metadata": case.metadata,
    }
    for category, descriptors in (
        ("inputs", case.inputs),
        ("references", case.references),
    ):
        materialized: dict[str, Any] = {}
        for role, descriptor in sorted(descriptors.items()):
            source_path = resolve_source_path(
                descriptor.path,
                manifest_dir=dataset_dir,
            )
            destination = (
                work_dir
                / "artifacts"
                / "dataset"
                / case_storage
                / category
                / artifact_filename(role, source_path)
            )
            artifact = materialize_artifact(
                descriptor,
                manifest_dir=dataset_dir,
                destination=destination,
                work_dir=work_dir,
                label=f"dataset case {case.case_id!r} {category} artifact {role!r}",
            )
            materialized[role] = artifact.model_dump(mode="json")
        output[category] = materialized
    return output


def prepare_dataset(
    dataset_path: Path,
    *,
    work_dir: Path,
) -> dict[str, Any]:
    dataset = load_dataset(dataset_path)
    cases = [
        _materialize_case_artifacts(
            case,
            dataset_dir=dataset_path.parent,
            work_dir=work_dir,
        )
        for case in dataset.cases
    ]
    return {
        "artifact_kind": "prepared_evaluation_dataset",
        "schema_version": 1,
        "dataset_id": dataset.dataset_id,
        "cases": cases,
    }


def verify_materialized_artifact(
    artifact: MaterializedArtifact | dict[str, Any],
    *,
    work_dir: Path,
) -> Path:
    parsed = (
        artifact
        if isinstance(artifact, MaterializedArtifact)
        else MaterializedArtifact.model_validate(artifact)
    )
    relative = Path(parsed.path)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise EvaluationArtifactError("materialized artifact path is unsafe")
    path = work_dir / relative
    payload = stable_file_bytes(
        path,
        label="materialized evaluation artifact",
        expected_sha256=parsed.sha256,
        expected_size=parsed.size_bytes,
    )
    if sha256_bytes(payload) != parsed.sha256:
        raise EvaluationArtifactError("materialized evaluation artifact hash mismatch")
    return path


def artifact_map_from_payload(payload: dict[str, Any]) -> dict[str, MaterializedArtifact]:
    return {
        role: MaterializedArtifact.model_validate(descriptor)
        for role, descriptor in payload.items()
    }


def manifest_sha256(payload: Any) -> str:
    return sha256_bytes(canonical_json_bytes(payload))


__all__ = [
    "EvaluationArtifactError",
    "artifact_filename",
    "artifact_map_from_payload",
    "assert_unlinked_regular_file",
    "canonical_json_bytes",
    "load_dataset",
    "manifest_sha256",
    "materialize_artifact",
    "prepare_dataset",
    "resolve_source_path",
    "sha256_bytes",
    "sha256_file",
    "stable_file_bytes",
    "storage_name",
    "verify_materialized_artifact",
    "write_bytes_atomic",
    "write_json_atomic",
]
