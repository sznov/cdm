from __future__ import annotations

import argparse
from pathlib import Path

from judge.protocol_profiles import load_protocol_profile_config
from judge.protocol_verify import spec_ids_from_dir, verify_protocol_artifact


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hard-verify a generated protocol artifact directory.")
    parser.add_argument("--protocol-dir", required=True, type=Path)
    parser.add_argument("--profile-config", type=Path)
    parser.add_argument("--spec-dir", required=True, type=Path)
    parser.add_argument("--spec-id", action="append", default=[])
    parser.add_argument("--expected-generations", type=int)
    parser.add_argument("--expected-judge-repeats", type=int)
    parser.add_argument("--skip-judge", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_protocol_profile_config(args.profile_config)
    errors = verify_protocol_artifact(
        protocol_dir=args.protocol_dir,
        profile_config=config,
        spec_ids=spec_ids_from_dir(args.spec_dir, args.spec_id),
        default_expected_generations=args.expected_generations,
        default_expected_judge_repeats=args.expected_judge_repeats,
        verify_judges=not args.skip_judge,
    )
    if errors:
        print("protocol artifact verification failed:")
        for error in errors:
            print(f"  {error}")
        return 1
    print("protocol artifact verification ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
