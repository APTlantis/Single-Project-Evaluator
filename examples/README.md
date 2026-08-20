# Examples

This directory documents example evaluator workflows. The examples are intentionally small: they demonstrate command behavior and response semantics without turning fixture material into real governed projects.

The evaluator is read-only with respect to the project being examined. In every example, place `--out` outside the target project tree.

## Passive Preparation

Create a preserved evidence package without model-backed reasoning:

```powershell
python -m single_project_evaluator --version
python -m single_project_evaluator evaluate --project D:\Some\Project --posture shared --out D:\CTS\Single-Project Evaluator\reports --backend none
```

Use JSON mode when another tool needs machine-readable output:

```powershell
python -m single_project_evaluator evaluate --project D:\Some\Project --posture shared --out D:\CTS\Single-Project Evaluator\reports --backend none --json
```

The run writes `evaluation.json`, `report.md`, `run-record.json`, `context-bundle.json`, `reasoning-request.json`, `reasoning-request.md`, and `response-template.json`.

## Manual Response Workflow

Use `reasoning-request.md` and `response-template.json` to prepare a structured response. Validate it before generating a completed report:

```powershell
python -m single_project_evaluator validate-response --response-file D:\CTS\Single-Project Evaluator\reports\response.json --posture shared --json
```

Apply the response file to a fresh collection:

```powershell
python -m single_project_evaluator evaluate --project D:\Some\Project --posture shared --out D:\CTS\Single-Project Evaluator\reports --backend response-file --response-file D:\CTS\Single-Project Evaluator\reports\response.json
```

Or apply it to a preserved run without rereading the evaluated project:

```powershell
python -m single_project_evaluator complete-run --out D:\CTS\Single-Project Evaluator\reports --run 93dfff32 --response-file D:\CTS\Single-Project Evaluator\reports\response.json --json
```

## Hosted OpenAI Workflow

Hosted evaluation is explicit. Set credentials outside committed files and select the backend and model:

```powershell
$env:OPENAI_API_KEY = "..."
python -m single_project_evaluator evaluate --project D:\Some\Project --posture shared --out D:\CTS\Single-Project Evaluator\reports --backend openai --model gpt-5 --timeout-seconds 120 --retries 1
```

The backend blocks likely sensitive outbound context by default. Use `--allow-sensitive-hosted` only after intentionally accepting the disclosure risk.

## Run Inspection

List, inspect, and validate preserved runs:

```powershell
python -m single_project_evaluator list-runs --out D:\CTS\Single-Project Evaluator\reports
python -m single_project_evaluator show-run --out D:\CTS\Single-Project Evaluator\reports --run 93dfff32 --json
python -m single_project_evaluator validate-run --out D:\CTS\Single-Project Evaluator\reports --run 93dfff32 --json
```

## Response Semantics To Preserve

Example response files should exercise evaluator semantics rather than become product fixtures:

- Personal projects may keep creator-specific assumptions when that matches declared posture.
- Deferred and N/A controls are not failures.
- High functional completeness and implementation quality can coexist with blocked release eligibility.
- Low functional completeness can coexist with high implementation quality.
- Full governance conformance can coexist with implementation-quality problems.
- Insufficient verification evidence should be recorded as `uncertainty:` evidence, not as a demonstrated failure.
- Mixed-surface projects may carry more than one deferred delivery-standard applicability record.
