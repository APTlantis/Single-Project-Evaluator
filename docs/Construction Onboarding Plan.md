# Construction Onboarding Plan

## Current State

Single-Project Evaluator has been onboarded as a planning-stage CTS command tool and analysis tool.

The current implementation is Phase 1: the evaluation spine. It can collect read-only project evidence, represent an evaluation run, and write evaluation artifacts. It does not yet perform deep model-backed project judgment.

## Source Authority

- `Project Proposal — Single-Project Evaluator.md` is the PPS seed and project intent record.
- `../provenance/ChatGPT-Design Project Examination Pipeline-20260819-1807.md` is conversation provenance and rationale.
- `../project.manifest.toml` records current project identity, governance, lifecycle, and implementation status.

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
- Bounded governance material loading implemented for readable standard files, with missing/unreadable paths recorded as evidence limits.
- Passive deterministic-evidence signal inference implemented for test sources, build configuration, release artifacts, verification logs, hashes, and checklists.
- Bounded representative file and text-snippet selection implemented.
- No-op backend boundary implemented.
- Provider-neutral reasoning request package implemented.
- Structured backend response validation implemented.
- Model-backed evaluation not yet implemented.

### Phase 2: Core Evaluation Workflow

Objectives:

- Establish project intent from authoritative records.
- Identify project class and likely governed surfaces.
- Load applicable governance material.
- Prepare deterministic evidence for reasoning.
- Invoke a configurable reasoning backend.
- Return structured findings and a narrative report.

### Phase 3: Verification Cases

Objectives:

- Create representative fixture projects.
- Verify Personal, Shared, and Adoptable posture behavior.
- Verify Deferred and N/A controls are not treated as failures.
- Verify release eligibility remains distinct from functional completeness.
- Verify unsupported claims are not reported as demonstrated failures.

### Phase 4: CTS Release Work

Objectives:

- Stabilize command contract.
- Add machine-readable output guarantees.
- Define exit codes.
- Document examples.
- Preserve release evidence.

Release work must not be confused with evaluation-engine completeness.

## Read-Only Boundary

The evaluator must not modify evaluated projects.

Phase 1 does not run target-project commands. Later phases may add explicitly enabled active checks, but passive evaluation remains the default.
