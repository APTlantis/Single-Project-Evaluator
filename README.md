# Single-Project Evaluator

Single-Project Evaluator is a read-only command-oriented analysis tool for examining one project at a time. It is designed to combine project intent, WGS lifecycle state, applicable City Hall governance, declared adoption posture, implementation evidence, operational behavior, and verification evidence into a multidimensional evaluation report.

The project is currently in Phase 1: the evaluation spine. This first implementation establishes durable data structures, project evidence collection, report artifact writing, and run provenance. It does not yet perform deep reasoning-model evaluation.

## Source Materials

- `docs/Project Proposal — Single-Project Evaluator.md` is the authoritative PPS seed.
- `provenance/ChatGPT-Design Project Examination Pipeline-20260819-1807.md` is decision history and rationale.

## Current CLI

```powershell
python -m pip install -e .
python -m single_project_evaluator evaluate --project D:\Some\Project --posture shared --out reports
```

The evaluator currently writes:

- `evaluation.json`
- `report.md`
- `run-record.json`
- `context-bundle.json`
- `reasoning-request.json`
- `reasoning-request.md`
- `response-template.json`
- `runs/<timestamp>-<report-id>/...`
- `runs/index.json`
- `runs/index.md`

The evaluated project is read-only. The current collector inventories files, extracts project context, prepares a bounded reasoning context bundle, loads bounded governance material from manifest-declared standard paths when available, records passive deterministic-evidence signals such as test sources, build configuration, release artifacts, verification logs, and hash/checklist records, writes a provider-neutral reasoning request package, and records discovered project material; it does not run target-project commands, tests, builds, installers, or API calls. The `--out` directory must be outside the evaluated project so report generation never writes into the target project tree.

Phase 1 supports only the no-op reasoning backend:

```powershell
python -m single_project_evaluator evaluate --project D:\Some\Project --posture shared --out reports --backend none
```

For machine-readable success output, add `--json`:

```powershell
python -m single_project_evaluator evaluate --project D:\Some\Project --posture shared --out reports --backend none --json
```

Model-backed evaluation is not implemented yet. The current backend boundary includes a no-op backend, a response-file backend, and a response parser/validator for the future structured model response. Structured backend responses may include an optional markdown `narrative` field, which is preserved in `evaluation.json` and rendered in `report.md`.

Each evaluation writes `response-template.json` as a fillable skeleton matching the structured backend response contract. Use it with `reasoning-request.json` or `reasoning-request.md` when preparing an external/manual reasoning response.

Validate a saved structured backend response before using it:

```powershell
python -m single_project_evaluator validate-response --response-file reports\response.json
```

```powershell
python -m single_project_evaluator validate-response --response-file reports\response.json --json
```

Use a validated response file to produce populated assessment/report fields:

```powershell
python -m single_project_evaluator evaluate --project D:\Some\Project --posture shared --out reports --backend response-file --response-file reports\response.json
```

List preserved evaluation runs from an existing report directory:

```powershell
python -m single_project_evaluator list-runs --out reports
```

```powershell
python -m single_project_evaluator list-runs --out reports --json
```

## Command Contract

- Exit `0`: command completed successfully.
- Exit `1`: command input or runtime error reported cleanly without a traceback.
- Exit `2`: command-line usage error or help fallback.

When `--json` is present on `evaluate`, `validate-response`, or `list-runs`, success output is written as JSON to stdout. Clean command errors are written as JSON to stderr:

```json
{
  "status": "error",
  "error": "human-readable message",
  "error_type": "ExceptionClassName"
}
```

## Adoption Postures

- `personal`: optimized for the creator or a narrowly known operator.
- `shared`: usable by other people with similar needs and technical context.
- `adoptable`: independently adoptable by unrelated users who share the problem.

These are evaluation inputs, not maturity levels.

## Development

```powershell
python -m unittest discover -s tests
```

If system Python is unavailable, use the bundled Codex workspace Python runtime.

## Construction Notes

See `docs/Construction Onboarding Plan.md` for the current staged build plan.
