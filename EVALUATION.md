# Evaluation utilities

The generic evaluation scripts in `scripts/evaluation/` support
user-supplied datasets, candidate generators, judges, aggregation, and bootstrap
comparisons. They are separate from the app UI.

## Evaluate your own data

Install the application dependencies as described in
[README.md](README.md), then run from the repository root. These commands use the
source checkout; the application Docker image does not include the scripts.

```sh
python -m scripts.evaluation.run_suite --help
python -m scripts.evaluation.run_suite --suite path/to/suite.json --work-dir out/evaluation/my-suite --validate-only
```

Supply your own suite configuration and the datasets, reference models, and
other artifacts it requires. Configuration types are defined in
`judge/evaluation_contracts.py`. Validation prepares a local workspace but
does not make generator or judge calls.

To execute the evaluation, rerun with `--resume` in place of `--validate-only`.
Live generation and judging require provider credentials and can incur
substantial charges; the runner does not impose a spending cap or interactive
confirmation.

Lower-level scripts under `scripts/generation/` and
`scripts/evaluation/` support generation, checkpoint export, judging, and
aggregation. Use their `--help` options for arguments.
