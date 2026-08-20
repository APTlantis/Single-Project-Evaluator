# Construction Onboarding Plan

## Current State

Single-Project Evaluator has been onboarded as a planning-stage CTS command tool and analysis tool.

The current implementation has moved from the Phase 1 evaluation spine into early Phase 2. It can collect read-only project evidence, represent an evaluation run, write evaluation artifacts, support manual preserved-run completion, and optionally invoke an explicitly selected OpenAI Responses API backend.

## Source Authority

- `docs/Project Proposal — Single-Project Evaluator.md` is the PPS seed and project intent record.
- `provenance/ChatGPT-Design Project Examination Pipeline-20260819-1807.md` is conversation provenance and rationale.
- `project.manifest.toml` records current project identity, governance, lifecycle, and implementation status.

## Construction Phases

### Phase 1: Evaluation Spine

Status: started.

Objectives:

- Represent adoption posture.
- Represent applicability states.
- Represent assessment profile fields.
- Represent finding class and authority.
- Represent evaluation run provenance.
- Collect basic project evidence without modifying the evaluated project.
- Extract project identity, lifecycle, governance, and surface hints from manifests and authority records.
- Prepare a bounded context bundle for a later reasoning backend.
- Write `evaluation.json`, `report.md`, and `run-record.json`.
- Write `context-bundle.json`.
- Write `reasoning-request.json` and `reasoning-request.md`.

Current status:

- Passive evidence inventory implemented.
- Authority record snapshots implemented.
- Project context extraction implemented.
- Surface inference and deferred governance-applicability records implemented.
- Manifest-declared governance standard path extraction implemented.
- Bounded governance material loading implemented for readable standard files, with missing/unreadable paths recorded as evidence limits and readable standard version hints preserved when declared.
- Passive deterministic-evidence signal inference implemented for test sources, build configuration, release artifacts, verification logs, hashes, and checklists.
- Bounded representative file and text-snippet selection implemented.
- No-op backend boundary implemented.
- Provider-neutral reasoning request package implemented.
- Structured backend response validation implemented.
- Finding validation now requires each returned finding to include at least one non-empty evidence or uncertainty reference.
- Governance conformance validation now requires percentage plus satisfied/applicable count strings when conformance entries are present.
- Release eligibility validation now requires BLOCKED to have blockers and PASS/NOT APPLICABLE to have zero blockers.
- Blocker validation now requires blocker counts to be backed by Required/Unsatisfied findings and rejects hidden Required/Unsatisfied findings in non-blocked responses.
- Optional backend narrative preservation and report rendering implemented for response-file runs.
- Response-file runs preserve response file path, size, and SHA-256 provenance.
- `validate-run` checks response-file provenance metadata shape when response-file metadata is present.
- Reports now include a deterministic Priority Findings section ordered Required, Should, Could, then Observation.
- Posture-aware response validation and fillable `response-template.json` artifact implemented to bridge prepared context to response-file evaluation.
- Preserved run inspection and integrity validation implemented with `list-runs`, `show-run`, and `validate-run`, including JSON output.
- `validate-run` checks the selected run-index summary against canonical `evaluation.json` fields.
- `validate-run` checks root latest aliases against the newest indexed run artifacts.
- `validate-run` checks artifact-manifest completeness, simple artifact filenames, byte sizes, and SHA-256 hashes when a manifest is present.
- `validate-run` checks backend response metadata hygiene so hosted provenance cannot silently preserve raw model output or likely credentials.
- Preserved run completion implemented with `complete-run`, allowing a structured response file to generate a new completed run from saved context without rereading the evaluated project.
- `complete-run` validates the selected source run before reusing its preserved context.
- Optional OpenAI Responses API backend implemented behind explicit `--backend openai` selection.
- OpenAI backend requests schema-guided Structured Outputs before parser validation.
- OpenAI request timeout and bounded transport retry configuration are exposed and preserved in run provenance.
- Hosted OpenAI requests are blocked by default when outbound authority records, governance material, or text snippets contain likely secrets; `--allow-sensitive-hosted` is required to override after explicit operator acceptance.
- Hosted response provenance records non-secret response id/status/model/service-tier/usage metadata without storing raw model output or credentials.
- Model-backed evaluation is available only when explicitly selected with credentials and a model; passive/no-op and manual response-file workflows remain supported.

### Phase 2: Core Evaluation Workflow

Objectives:

- Establish project intent from authoritative records.
- Identify project class and likely governed surfaces.
- Load applicable governance material.
- Prepare deterministic evidence for reasoning.
- Invoke a configurable reasoning backend. Started with explicit OpenAI Responses API support.
- Return structured findings and a narrative report.

### Phase 3: Verification Cases

Objectives:

- Create representative fixture projects.
- Verify Personal, Shared, and Adoptable posture behavior.
- Verify Deferred and N/A controls are not treated as failures.
- Verify release eligibility remains distinct from functional completeness.
- Verify unsupported claims are not reported as demonstrated failures.

Current status:

- Started with response-file fixture runs for Personal, Shared, and Adoptable postures.
- Personal fixture verifies creator-specific/non-adoptable assumptions can be appropriate at personal posture.
- Shared fixture verifies Deferred governance applicability is preserved without becoming a release blocker.
- Adoptable fixture verifies high completeness and implementation quality can coexist with BLOCKED release eligibility.
- Unsupported-claim handling now accepts explicit `uncertainty:` evidence references for observations while rejecting Required/Unsatisfied findings backed only by uncertainty.
- Additional fixtures verify low functional completeness can coexist with high implementation quality, insufficient verification evidence is reported as uncertainty rather than demonstrated failure, and full governance conformance can coexist with implementation-quality problems.
- Mixed-surface fixture verifies deterministic context preparation can infer multiple governed surfaces and defer CTS/WDS applicability separately.

### Phase 4: CTS Release Work

Objectives:

- Stabilize command contract.
- Add machine-readable output guarantees. Started for `evaluate --json`, `validate-response --json`, `list-runs --json`, `show-run --json`, `validate-run --json`, and `complete-run --json` success/error output.
- Define exit codes. Started with success `0`, clean command error `1`, and usage/help fallback `2`.
- Document examples. Started with passive, manual response-file, hosted OpenAI, and preserved-run inspection workflows in `examples/README.md`.
- Preserve release evidence. Started with `artifact-manifest.json` hashes for generated run artifacts and `validate-run` manifest integrity checks.

Release work must not be confused with evaluation-engine completeness.

## Read-Only Boundary

The evaluator must not modify evaluated projects.

Phase 1 does not run target-project commands. Later phases may add explicitly enabled active checks, but passive evaluation remains the default.

Report output is required to live outside the evaluated project tree. The CLI rejects `--out` values inside the target project before writing artifacts.
