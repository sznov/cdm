from __future__ import annotations

from pathlib import Path
from typing import Any

from core.artifacts import load_json
from judge.directional import DEFAULT_DIRECTIONAL_JUDGE_PROMPT_PROFILE, DIRECTIONAL_JUDGE_PROMPT_PROFILE_IDS


DEFAULT_PROTOCOL_PROFILES: dict[str, Any] = {
    "profiles": [
        {
            "id": "gemma_baseline",
            "output_label": "gemma_baseline",
            "label": "Gemma baseline",
            "generator": "direct_baseline",
            "harness_id": "direct-baseline-schema-only-v1",
            "provider": "gemini",
            "profile_arg": "gemma-baseline",
            "prompt_profile": "schema_only_v1",
            "target_valid_generations": 5,
            "fill_max_attempts": 20,
            "judge_repeats": 5,
            "checkpoint_labels": ["single_shot_schema"],
            "manifest": "direct_baseline/checkpoint_manifest.json",
            "judge_output_dir": "direct_repeated_judge",
        },
        {
            "id": "gpt55_reference",
            "output_label": "gpt55_reference",
            "label": "GPT 5.5 reference",
            "generator": "direct_baseline",
            "harness_id": "direct-baseline-schema-only-v1",
            "provider": "codex",
            "profile_arg": "gpt55-reference",
            "prompt_profile": "schema_only_v1",
            "target_valid_generations": 1,
            "fill_max_attempts": 3,
            "judge_repeats": 5,
            "checkpoint_labels": ["single_shot_schema"],
            "manifest": "codex_reference/checkpoint_manifest.json",
            "judge_output_dir": "codex_reference_repeated_judge",
            "optional": True,
        },
        {
            "id": "first_draft",
            "output_label": "first_draft",
            "label": "First draft",
            "generator": "harness_checkpoint",
            "harness_id": "gemma4-tuned-final",
            "judge_repeats": 5,
            "checkpoint_labels": ["first_valid_draft"],
            "manifest": "selected_checkpoints/checkpoint_manifest.json",
            "judge_output_dir": "harness_repeated_judge",
        },
        {
            "id": "revised",
            "output_label": "revised",
            "label": "Revised",
            "generator": "harness_checkpoint",
            "harness_id": "gemma4-tuned-final",
            "judge_repeats": 5,
            "checkpoint_labels": ["pre_posthoc"],
            "manifest": "selected_checkpoints/checkpoint_manifest.json",
            "judge_output_dir": "harness_repeated_judge",
            "paired_against": ["first_draft"],
        },
        {
            "id": "final",
            "output_label": "final",
            "label": "Final",
            "generator": "harness_checkpoint",
            "harness_id": "gemma4-tuned-final",
            "judge_repeats": 5,
            "checkpoint_labels": ["final_guarded_posthoc"],
            "manifest": "selected_checkpoints/checkpoint_manifest.json",
            "judge_output_dir": "harness_repeated_judge",
            "paired_against": ["first_draft", "revised"],
        },
    ]
}


def load_protocol_profile_config(path: Path | None = None) -> dict[str, Any]:
    if path is None:
        return DEFAULT_PROTOCOL_PROFILES
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Protocol profile config must be a JSON object: {path}")
    return payload


def protocol_profiles(config: dict[str, Any]) -> list[dict[str, Any]]:
    raw_profiles = config.get("profiles")
    if not isinstance(raw_profiles, list):
        raise ValueError("Protocol profile config must contain a 'profiles' list.")
    profiles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_profiles, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Profile #{index} must be an object.")
        profile = dict(item)
        profile_id = str(profile.get("id") or "").strip()
        if not profile_id:
            raise ValueError(f"Profile #{index} is missing id.")
        if profile_id in seen:
            raise ValueError(f"Duplicate profile id: {profile_id}")
        seen.add(profile_id)
        labels = profile.get("checkpoint_labels")
        if labels is None:
            label = str(profile.get("checkpoint_label") or "").strip()
            labels = [label] if label else []
        if not isinstance(labels, list):
            raise ValueError(f"Profile {profile_id} checkpoint_labels must be a list.")
        profile["checkpoint_labels"] = [str(label) for label in labels if str(label)]
        profile["judge_repeats"] = int(profile.get("judge_repeats") or 5)
        judge_prompt_profile = str(profile.get("judge_prompt_profile") or DEFAULT_DIRECTIONAL_JUDGE_PROMPT_PROFILE)
        if judge_prompt_profile not in DIRECTIONAL_JUDGE_PROMPT_PROFILE_IDS:
            valid = ", ".join(DIRECTIONAL_JUDGE_PROMPT_PROFILE_IDS)
            raise ValueError(f"Profile {profile_id} has unknown judge_prompt_profile {judge_prompt_profile!r}. Valid profiles: {valid}")
        profile["judge_prompt_profile"] = judge_prompt_profile
        profile["output_label"] = str(profile.get("output_label") or profile_id)
        paired_against = profile.get("paired_against") or []
        if isinstance(paired_against, str):
            paired_against = [paired_against]
        if not isinstance(paired_against, list):
            raise ValueError(f"Profile {profile_id} paired_against must be a string or list.")
        profile["paired_against"] = [str(label) for label in paired_against if str(label)]
        profiles.append(profile)
    return profiles


def direct_generation_profiles(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [profile for profile in protocol_profiles(config) if profile.get("generator") == "direct_baseline"]


def harness_checkpoint_profiles(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [profile for profile in protocol_profiles(config) if profile.get("generator") == "harness_checkpoint"]


__all__ = [
    "DEFAULT_PROTOCOL_PROFILES",
    "direct_generation_profiles",
    "harness_checkpoint_profiles",
    "load_protocol_profile_config",
    "protocol_profiles",
]
