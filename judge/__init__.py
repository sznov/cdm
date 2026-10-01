"""LLM-as-judge evaluation helpers.

The judge package is intentionally separate from core generation logic. It can
depend on core model/schema/artifact helpers, while core must not import judge.
"""

from judge.directional import (
    DEFAULT_DIRECTIONAL_JUDGE_PROMPT_PROFILE,
    DIRECTIONAL_JUDGE_PROMPT_PROFILE_IDS,
    DIRECTIONAL_JUDGE_PROMPT_PROFILES,
    DirectionalJudgePromptProfile,
    DirectionalModelJudgeClient,
    build_directional_model_judge_messages,
    directional_judge_prompt_profile,
    evaluate_model_files_directional,
    evaluate_structured_model_pair_directional,
    indexed_model_artifacts,
    parse_directional_model_judge_output,
    score_directional_all_artifacts,
)
from judge.aggregation import aggregate_judged_run, summarize_profile
from judge.accounting import generation_accounting_rows, write_generation_accounting
from judge.bootstrap import hierarchical_bootstrap_ci, paired_delta_bootstrap_ci
from judge.checkpoints import select_protocol_checkpoints
from judge.protocol_profiles import (
    direct_generation_profiles,
    harness_checkpoint_profiles,
    load_protocol_profile_config,
    protocol_profiles,
)
from judge.protocol_verify import spec_ids_from_dir, verify_protocol_artifact
from judge.repeated import (
    build_repeated_judge_reports,
    degenerate_zero_directional_reason,
    normalize_model_rows,
    write_repeated_judge_reports,
)
from judge.trajectory import build_trajectory_reports, write_trajectory_reports

__all__ = [
    "aggregate_judged_run",
    "build_repeated_judge_reports",
    "build_trajectory_reports",
    "build_directional_model_judge_messages",
    "DEFAULT_DIRECTIONAL_JUDGE_PROMPT_PROFILE",
    "DIRECTIONAL_JUDGE_PROMPT_PROFILE_IDS",
    "DIRECTIONAL_JUDGE_PROMPT_PROFILES",
    "DirectionalJudgePromptProfile",
    "DirectionalModelJudgeClient",
    "degenerate_zero_directional_reason",
    "directional_judge_prompt_profile",
    "evaluate_model_files_directional",
    "evaluate_structured_model_pair_directional",
    "generation_accounting_rows",
    "hierarchical_bootstrap_ci",
    "indexed_model_artifacts",
    "direct_generation_profiles",
    "harness_checkpoint_profiles",
    "load_protocol_profile_config",
    "normalize_model_rows",
    "paired_delta_bootstrap_ci",
    "parse_directional_model_judge_output",
    "protocol_profiles",
    "score_directional_all_artifacts",
    "select_protocol_checkpoints",
    "spec_ids_from_dir",
    "summarize_profile",
    "verify_protocol_artifact",
    "write_repeated_judge_reports",
    "write_generation_accounting",
    "write_trajectory_reports",
]
