from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from core.artifacts import load_json, write_csv, write_json
from judge.bootstrap import hierarchical_bootstrap_ci, paired_delta_bootstrap_ci
from judge.protocol_profiles import load_protocol_profile_config, protocol_profiles


SUMMARY_FIELDS = [
    "source",
    "checkpoint_label",
    "spec_count",
    "model_count",
    "primary_mean_precision",
    "primary_mean_recall",
    "primary_mean_f1",
    "primary_mean_macro_f1",
    "model_mean_precision",
    "model_mean_recall",
    "model_mean_f1",
    "model_mean_macro_f1",
]


def rows_from_repeated_dir(path: Path, profiles: list[dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    summary_path = path / "checkpoint_summary.json"
    if not summary_path.exists():
        return [], {}
    rows = load_json(summary_path)
    if not isinstance(rows, list):
        return [], {}
    majority_path = path / "majority_scores.json"
    majority_rows = load_json(majority_path) if majority_path.exists() else []
    if not isinstance(majority_rows, list):
        majority_rows = []
    output: list[dict[str, Any]] = []
    by_profile: dict[str, list[dict[str, Any]]] = {}
    if not profiles:
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = {"source": path.name}
            item.update(row)
            output.append(item)
        by_profile[path.name] = [row for row in majority_rows if isinstance(row, dict)]
        return output, by_profile

    for profile in profiles:
        source = str(profile.get("output_label") or profile.get("id") or path.name)
        labels = {str(label) for label in profile.get("checkpoint_labels") or []}
        profile_majority = [
            row for row in majority_rows if isinstance(row, dict) and (not labels or str(row.get("checkpoint_label") or "") in labels)
        ]
        if profile_majority:
            by_profile[source] = profile_majority
        for row in rows:
            if not isinstance(row, dict):
                continue
            if labels and str(row.get("checkpoint_label") or "") not in labels:
                continue
            item = {"source": source}
            item.update(row)
            output.append(item)
    return output, by_profile


def write_tex_table(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "\\begin{tabular}{lrrrr}",
        "Checkpoint & Models & Precision & Recall & F1 \\\\",
        "\\hline",
    ]
    for row in rows:
        lines.append(
            f"{row.get('source', '')}/{row.get('checkpoint_label', '')} & "
            f"{row.get('model_count', '')} & "
            f"{row.get('primary_mean_precision', '')} & "
            f"{row.get('primary_mean_recall', '')} & "
            f"{row.get('primary_mean_f1', '')} \\\\"
        )
    lines.append("\\end{tabular}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Combine repeated-judge summaries into JSON/CSV/TEX tables.")
    parser.add_argument("--repeated-dir", action="append", default=[], type=Path)
    parser.add_argument("--protocol-dir", type=Path, help="Optional protocol work directory; known repeated-judge dirs are detected.")
    parser.add_argument("--profile-config", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=0)
    parser.add_argument("--bootstrap-seed", type=int, default=20260523)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    profile_config = load_protocol_profile_config(args.profile_config)
    profiles = protocol_profiles(profile_config)
    profiles_by_judge_dir: dict[str, list[dict[str, Any]]] = {}
    for profile in profiles:
        profiles_by_judge_dir.setdefault(str(profile.get("judge_output_dir") or ""), []).append(profile)

    repeated_dirs = list(args.repeated_dir)
    if args.protocol_dir:
        seen_dirs: set[Path] = set()
        for name in sorted(name for name in profiles_by_judge_dir if name):
            path = args.protocol_dir / name
            if path.exists():
                seen_dirs.add(path)
        trajectory_path = args.protocol_dir / "trajectory_repeated_judge"
        if trajectory_path.exists():
            seen_dirs.add(trajectory_path)
        repeated_dirs.extend(sorted(seen_dirs))

    rows: list[dict[str, Any]] = []
    majority_by_profile: dict[str, list[dict[str, Any]]] = {}
    for path in repeated_dirs:
        matching_profiles = profiles_by_judge_dir.get(path.name)
        path_rows, path_majority = rows_from_repeated_dir(path, matching_profiles)
        rows.extend(path_rows)
        for profile, profile_rows in path_majority.items():
            majority_by_profile.setdefault(profile, []).extend(profile_rows)

    bootstrap_rows: list[dict[str, Any]] = []
    paired_delta_rows: list[dict[str, Any]] = []
    if args.bootstrap_samples > 0:
        by_id_or_label = {str(profile.get("id")): str(profile.get("output_label")) for profile in profiles}
        by_id_or_label.update({str(profile.get("output_label")): str(profile.get("output_label")) for profile in profiles})
        for profile, profile_rows in sorted(majority_by_profile.items()):
            bootstrap_rows.extend(
                hierarchical_bootstrap_ci(
                    profile_rows,
                    profile=profile,
                    samples=args.bootstrap_samples,
                    seed=args.bootstrap_seed,
                )
            )
        for profile in profiles:
            right_label = str(profile.get("output_label") or profile.get("id"))
            right_rows = majority_by_profile.get(right_label) or []
            for left_ref in profile.get("paired_against") or []:
                left_label = by_id_or_label.get(str(left_ref), str(left_ref))
                left_rows = majority_by_profile.get(left_label) or []
                if not left_rows or not right_rows:
                    continue
                paired_delta_rows.extend(
                    paired_delta_bootstrap_ci(
                        left_rows,
                        right_rows,
                        comparison=f"{left_label}->{right_label}",
                        samples=args.bootstrap_samples,
                        seed=args.bootstrap_seed,
                    )
                )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "summary_rows.json", rows)
    write_csv(args.out_dir / "summary_rows.csv", rows, SUMMARY_FIELDS)
    write_tex_table(args.out_dir / "summary_table.tex", rows)
    write_json(args.out_dir / "bootstrap_ci.json", bootstrap_rows)
    write_csv(
        args.out_dir / "bootstrap_ci.csv",
        bootstrap_rows,
        ["profile", "kind", "metric", "model_rows", "specs", "samples", "mean", "ci95_low", "ci95_high"],
    )
    write_json(args.out_dir / "paired_deltas.json", paired_delta_rows)
    write_csv(
        args.out_dir / "paired_deltas.csv",
        paired_delta_rows,
        ["comparison", "kind", "metric", "paired_rows", "specs", "samples", "mean", "ci95_low", "ci95_high"],
    )
    print(f"Wrote {len(rows)} summary rows to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
