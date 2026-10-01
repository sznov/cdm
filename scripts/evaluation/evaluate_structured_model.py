from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from core.model_call_logger import ModelCallLogger
from core.providers.factory import build_text_model_client, default_model_for_provider
from core.runtime_env import load_dotenv_file
from judge import (
    DEFAULT_DIRECTIONAL_JUDGE_PROMPT_PROFILE,
    DIRECTIONAL_JUDGE_PROMPT_PROFILE_IDS,
    DirectionalModelJudgeClient,
    evaluate_model_files_directional,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate one structured model against a reference using directional LLM judging only.")
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--predicted", required=True, type=Path)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--confidence-threshold", type=float, default=0.5)
    parser.add_argument("--provider", choices=("gemini", "codex", "nvidia_nim"), default="codex")
    parser.add_argument("--model", help="Defaults to the selected provider's default model.")
    parser.add_argument("--base-url")
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--max-completion-tokens", type=int, default=32768)
    parser.add_argument("--codex-reasoning-effort", default="xhigh")
    parser.add_argument(
        "--judge-prompt-profile",
        choices=DIRECTIONAL_JUDGE_PROMPT_PROFILE_IDS,
        default=DEFAULT_DIRECTIONAL_JUDGE_PROMPT_PROFILE,
    )
    return parser


async def command_evaluate(args: argparse.Namespace) -> int:
    load_dotenv_file()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    model = args.model or default_model_for_provider(args.provider)
    client = build_text_model_client(
        provider=args.provider,
        model=model,
        base_url=args.base_url.rstrip("/") if args.base_url else None,
        timeout_seconds=args.timeout_seconds,
        max_completion_tokens=args.max_completion_tokens,
        reasoning_effort=args.codex_reasoning_effort if args.provider == "codex" else None,
        response_format_json_object=True,
    )
    logger = ModelCallLogger(job_id=f"directional-eval-{args.predicted.stem}", log_dir=args.output_dir / "model_calls")
    result = await evaluate_model_files_directional(
        gold_model_path=args.gold,
        predicted_model_path=args.predicted,
        specification_path=args.spec,
        output_dir=args.output_dir,
        judge_client=DirectionalModelJudgeClient(client, logger=logger, prompt_profile_id=args.judge_prompt_profile),
        confidence_threshold=args.confidence_threshold,
    )
    aggregate = result["directional_semantic_score"]["aggregate"]
    print(
        "directional_semantic "
        f"precision={aggregate['precision']} recall={aggregate['recall']} f1={aggregate['f1']} macro_f1={aggregate['macro_f1']}"
    )
    return 0


def main() -> int:
    return asyncio.run(command_evaluate(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
