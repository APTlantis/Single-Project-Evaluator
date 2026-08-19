# Project Proposal — Single-Project Evaluator

## Proposal Status

**PPS Readiness:** Ready  
**WGS Lifecycle State:** Planning  
**Project Class:** Command Tool / Analysis Tool  
**Primary Governing Standard:** PPS  
**Expected Delivery Standard:** CTS  
**Working Name:** Single-Project Evaluator  
**Final Project Name:** TBD

## Project Theme

Deep, evidence-backed evaluation of one project against its intent, implementation, governance obligations, lifecycle, and intended level of adoption.

---

## Problem Statement

City Hall already supports governance-oriented analysis across multiple projects. That approach is useful for portfolio-scale inspection, identifying missing governance artifacts, checking release gates, and comparing many projects efficiently.

It is not intended to answer a deeper question about one individual project:

> Given what this project says it is, where it is in its lifecycle, which City Hall rules actually govern it, how broadly it is intended to be used, and what its implementation actually does: what is sound, what is deficient, what will cause trouble, what deserves improvement, and what is merely an optional opportunity?

Individual projects require a different kind of examination.

A project may be functionally complete and well engineered while remaining blocked from release because it has not satisfied a delivery standard. Another project may satisfy its governance artifacts while containing weak architecture or unnecessary complexity. A personal tool may be entirely appropriate despite assumptions that would make an adoptable project difficult for independent users.

A single score or release-gate result obscures these distinctions.

The existing multi-project analysis pipeline should remain suited to broad governance analysis. A separate evaluator is needed for deliberate, infrequent, high-depth examination of one project at a time.

---

## Mission Statement

The Single-Project Evaluator is a read-only project examination system that evaluates one project at a time by combining the project's declared intent, WGS lifecycle state, applicable City Hall governance, declared adoption posture, implementation, operational behavior, documentation, and available verification evidence. It produces a multidimensional assessment and detailed evidence-backed report that distinguishes project completeness, engineering quality, governance conformance, adoption fitness, and release eligibility without collapsing them into a single overall score or modifying the project being evaluated.

---

# Design Boundaries

## In Scope

The Evaluator will:

- Evaluate exactly one project per evaluation run.
- Establish the project's declared purpose and authoritative project intent before evaluating implementation.
- Consider the project's current WGS lifecycle state.
- Determine which City Hall standards are applicable to the project and its individual delivery surfaces.
- Evaluate applicable governance requirements against evidence.
- Inspect source code and implementation rather than limiting evaluation to governance documents.
- Evaluate functional completeness independently from implementation quality.
- Evaluate architecture and engineering quality.
- Evaluate correctness, resilience, failure behavior, and state handling where relevant.
- Evaluate security and trust concerns where relevant to the project.
- Evaluate performance and resource behavior where relevant.
- Evaluate testing, validation, and available verification evidence.
- Compare documentation with actual implementation.
- Evaluate operational workflow quality.
- Identify creator-specific assumptions.
- Evaluate adoption concerns according to a declared project posture.
- Evaluate lifecycle fitness.
- Evaluate release eligibility when release evaluation is applicable.
- Identify missing responsibilities and improvement opportunities.
- Distinguish requirements from recommendations.
- Preserve evidence and provenance for significant conclusions.
- Produce both a concise project-condition profile and a detailed narrative report.
- Preserve sufficient evaluation-run metadata to understand what project state, governance versions, evidence, configuration, and reasoning model produced an assessment.

## Out of Scope

The Evaluator will not:

- Modify source code.
- Rewrite project documentation as part of evaluation.
- Create missing governance artifacts as part of evaluation.
- Automatically remediate findings.
- Automatically advance or change WGS lifecycle state.
- Automatically approve or release a project.
- Replace the existing multi-project analysis pipeline.
- Evaluate multiple projects as a portfolio in one run.
- Treat optional improvements as requirements.
- Treat external adoption as an inherent goal of every project.
- Require every project to satisfy release obligations when no release is currently claimed or applicable.
- Produce a universal overall project score.
- Optimize projects toward generic commercial, enterprise, growth, or market conventions unless the project itself establishes such requirements.

## Explicit Non-Goals

The Evaluator is not:

- An implementation agent.
- A remediation agent.
- A project manager.
- A code-generation system.
- A release automation system.
- A universal static analyzer.
- A replacement for deterministic validators, tests, linters, or City Hall standards.
- A mechanism for forcing personal projects to become generally adoptable software.
- A feature-generation engine.

The Evaluator may recommend specific implementation changes and explain preferable technical approaches. Recommendation authority ends at the report.

---

# Evaluation Context

Every evaluation must establish its context before judging the project.

At minimum, the context includes:

- Project identity.
- Project class or classes.
- Current WGS lifecycle state.
- PPS mission and problem statement where available.
- Success criteria.
- Failure criteria.
- Design boundaries and non-goals.
- Constraints.
- Operational personas.
- Technical direction.
- Relationships to other projects or standards where relevant.
- Applicable City Hall governance.
- Available implementation and verification evidence.
- Declared adoption posture.

The Evaluator must not infer project purpose from source code alone when authoritative project records exist.

Missing or contradictory project intent is itself an evaluation finding and must not be silently resolved by inventing intent.

---

# Adoption Posture

Each evaluation run requires the operator to declare the project's current adoption posture.

The permanent posture options are:

## Personal

The project is deliberately built primarily for its creator or a narrowly known operator.

Personal conventions, environmental assumptions, fixed workflows, and creator preferences are not deficiencies merely because unrelated users would find them unusual.

External onboarding, portability, configurability, and generalized usability are evaluated only where required by the project's own intent, governance, or actual use.

## Shared

The project is intended to be usable by other people with similar needs and reasonably comparable technical context.

The evaluation expands to consider undocumented assumptions, setup friction, portability, discoverability, documentation sufficiency, configuration, recovery, and obstacles that another expected operator would encounter.

## Adoptable

The project is intended to stand independently for unrelated users who share the problem it solves.

The evaluation gives substantial weight to independent installation or acquisition, onboarding, documentation, configuration, safe defaults, portability, compatibility, error comprehension, recovery, trust, upgrade expectations, and removal of unnecessary creator-specific assumptions.

## Posture Rules

Personal, Shared, and Adoptable are not maturity levels.

A Personal project is not an immature Adoptable project.

A project may change posture over time.

The posture is declared for each evaluation run so that the evaluation reflects current intent. A previous evaluation's posture does not permanently bind later evaluations.

Posture changes both:

1. How findings are interpreted.
2. Which evaluation concerns are applicable or receive substantial examination.

The Evaluator must not penalize a project for failing expectations that belong only to a posture it does not claim.

---

# Applicability Model

Evaluation is conditional.

A concern or governance requirement must first be determined applicable before its satisfaction is judged.

Applicability depends on:

- Project class and delivery surfaces.
- Declared adoption posture.
- WGS lifecycle state.
- Project claims and boundaries.
- Applicable City Hall standards.
- Whether a release, stability level, publication state, or other governed transition is actually being claimed.

Governance controls and evaluation concerns may receive these states:

**Satisfied** — Applicable and supported by sufficient evidence.

**Unsatisfied** — Applicable now and not satisfied.

**Deferred** — Relevant to a later legitimate lifecycle or transition but not currently required.

**N/A** — Not applicable to the project's current class, posture, lifecycle, scope, or claims.

A blocker is a consequence, not a satisfaction state.

An Unsatisfied requirement becomes a **Blocker** only when the governing standard or claimed transition makes that deficiency blocking.

The core evaluation sequence is:

> Applicability → Evidence → Satisfaction → Consequence

N/A and Deferred must not be treated as failures or assigned zero scores.

---

# Core Evaluation Areas

## Project and Intent

Evaluate:

- Mission fidelity.
- Problem fidelity.
- Scope.
- Design boundaries.
- Success and failure criteria.
- Constraints.
- Technical direction.
- Operational personas.
- Project relationships.
- Contradictions between authoritative project records and actual implementation.

Primary question:

> Is this still the project it says it is?

## Functional Completeness

Evaluate:

- Declared capabilities that exist.
- Declared capabilities that are incomplete.
- Broken workflows.
- Partial implementations.
- Stubs and placeholders.
- Missing core behavior.
- Whether the primary workflows accomplish the project's stated mission.

Functional completeness is judged against declared scope, not an imagined ideal version of the project.

## Architecture and Implementation

Evaluate where applicable:

- Architectural structure.
- Component boundaries.
- Separation of concerns.
- Coupling and cohesion.
- Abstraction quality.
- Duplication.
- Dead or obsolete paths.
- Error handling.
- State mutation.
- Resource handling.
- Configuration design.
- Persistence and data handling.
- Concurrency.
- Dependency use.
- Testability.
- Maintainability.
- Disproportionate complexity.
- Consistency between documented and actual architecture.
- Cases where a materially simpler, safer, or clearer implementation exists.

Unconventional design is not inherently deficient.

A recommendation to replace an existing implementation must identify an actual engineering advantage.

## Correctness and Resilience

Evaluate relevant failure conditions, including:

- Invalid or malformed input.
- Missing resources.
- Permission failures.
- Partial state.
- Interrupted operations.
- Failed reads and writes.
- Unavailable dependencies.
- Invalid configuration.
- Corrupted persisted data.
- Unexpected versions.
- Destructive operations.
- Recovery behavior.

Determine whether failures are detected, communicated, contained, recoverable, destructive, silent, or capable of leaving ambiguous state.

## Security and Trust

Evaluate only to the extent appropriate to the project's actual behavior and threat surface.

Relevant concerns may include:

- Trust boundaries.
- Credential and secret handling.
- Permissions.
- Unsafe input handling.
- Data exposure.
- Dependency risks.
- Destructive authority.
- Untrusted content.
- Claims of security unsupported by evidence.

This area must not become a generic security checklist detached from project reality.

## Performance and Resource Behavior

Evaluate when meaningful to the project:

- Responsiveness.
- Computational cost.
- Memory behavior.
- Disk behavior.
- Network behavior.
- Scaling characteristics.
- Unnecessary repeated work.
- Pathological cases.
- Performance characteristics that contradict project constraints or workflows.

Projects without meaningful performance concerns should not be penalized for the absence of performance engineering.

## Testing and Verification

Evaluate:

- Presence and relevance of tests.
- Test quality.
- Integration verification.
- Validators.
- Build evidence.
- Fixtures and examples.
- Manual verification records.
- Release evidence where applicable.
- Important behavior that remains unverified.

Absence of evidence must not be reported as evidence of failure.

The Evaluator must distinguish:

> "This behavior is broken."

from:

> "I found insufficient evidence that this behavior has been verified."

## Documentation and Recoverability

Evaluate whether documentation accurately describes the project that actually exists.

Consider:

- Missing information.
- Stale information.
- Contradictions.
- Undocumented behavior.
- Documentation for removed behavior.
- Architectural rationale where needed.
- Broken examples.
- Missing operational knowledge.
- Missing recovery knowledge.
- Ability to recover project context after dormancy.

Documentation expectations scale with project posture and applicable governance.

## Operator and User Workflow

Evaluate:

- Setup.
- Configuration.
- Startup.
- Primary workflows.
- Discoverability.
- Feedback during operation.
- Error presentation.
- Recovery.
- Repeated-use friction.
- Shutdown, cleanup, or removal where relevant.

The expected operator depends on project intent and declared posture.

## Creator-Assumption Analysis

Explicitly identify knowledge embedded in the project because its creator already knows it.

Examples include:

- Hard-coded environment assumptions.
- Expected directory structures.
- Unstated prerequisites.
- Unexplained terminology.
- Environment variables not documented.
- Implicit operation ordering.
- Configuration values whose meaning is undocumented.
- Recovery procedures preserved only in creator knowledge.
- Relationships to other projects that are not discoverable.
- Defaults derived from one machine or workflow.
- Errors understandable only with internal implementation knowledge.

For Personal projects, many such assumptions may be appropriate.

For Shared projects, they may create friction.

For Adoptable projects, they may become substantial deficiencies.

## Adoption Fitness

Adoption examination scales with posture.

Potential concerns include:

- First-use experience.
- Acquisition and installation.
- Prerequisites.
- Configuration.
- Portability.
- Defaults.
- Documentation.
- Examples.
- Error comprehensibility.
- Compatibility.
- Upgrade or migration expectations.
- Cleanup or removal.
- Trust expectations.
- Distribution and licensing considerations where applicable.
- Amount of creator-specific knowledge required.

Adoptable does not mean commercial, enterprise-ready, universally configurable, or suitable for every user.

It means an independent person who shares the relevant problem can reasonably adopt the project.

## Governance

Determine applicable standards from the actual project and its surfaces.

Evaluate each applicable standard independently.

Do not combine all City Hall governance into one undifferentiated compliance score.

Mixed projects may require separate governance evaluation for separate surfaces.

Governance evaluation must preserve the distinction between:

- Explicit standard requirements.
- Project-specific requirements.
- Evaluator engineering judgment.
- Adoption recommendations.

## Release Readiness

Evaluate release readiness only when applicable to the project's lifecycle, claims, and intended transition.

A functioning project that is not attempting a governed release must not be penalized for release artifacts it has no present responsibility to create.

When release evaluation is applicable, release blockers remain blockers regardless of otherwise high project quality or completeness.

## Improvement and Opportunity

Only after understanding the project should the Evaluator identify potential changes.

It must not begin with feature brainstorming.

Potential improvements must remain inside project intent unless explicitly identified as possible future scope.

---

# Assessment Profile

The Evaluator must not produce a single overall project score.

Every evaluation produces a multidimensional project-condition profile.

## Functional Completeness

**Format:** Percentage.

Answers:

> How much of the project's declared intended functionality actually exists and works?

Release documentation, packaging, or governance deficiencies must not artificially reduce Functional Completeness unless they are themselves declared project functionality.

## Implementation Quality

**Format:** Percentage.

Answers:

> How well is the implemented portion of the project engineered relative to the project's actual requirements and scale?

The score synthesizes relevant architecture, clarity, complexity, maintainability, correctness, state handling, dependency use, security, performance, and implementation concerns.

More architecture is not inherently better architecture.

Overengineering may reduce Implementation Quality.

## Intent Fidelity

**Format:** Categorical.

Expected vocabulary:

- Strong
- Moderate
- Weak
- Contradictory

Answers:

> Does the project that exists correspond to the project described by its authoritative intent records?

## Verification Confidence

**Format:** Categorical.

Expected vocabulary:

- Strong
- Substantial
- Partial
- Weak
- Unverified

Answers:

> How much confidence does the available evidence justify in claims about project functionality and correctness?

Verification Confidence is independent of apparent Implementation Quality.

## Posture Fitness

**Format:** Declared posture plus categorical fitness.

Expected fitness vocabulary:

- Strong
- Adequate
- Marginal
- Weak

Examples:

`Personal — Strong`

`Shared — Adequate`

`Adoptable — Weak`

Answers:

> How well does the project satisfy the expectations created by its currently declared adoption posture?

## Governance Conformance

**Format:** Percentage plus satisfied/applicable count, separately for every applicable standard.

Example:

`DRS Conformance: 94% — 31/33 applicable requirements satisfied`

Governance conformance measures how much applicable responsibility has been satisfied.

It does not determine whether a blocking requirement remains.

N/A and legitimately Deferred controls are excluded from the applicable denominator.

## Lifecycle Fitness

**Format:** Categorical.

Expected vocabulary:

- Appropriate
- Ahead of Evidence
- Behind Actual State
- Ambiguous

Answers:

> Does the project's actual condition justify its claimed WGS lifecycle state?

## Release Eligibility

**Format:**

- PASS
- BLOCKED
- NOT APPLICABLE

When blocked, the blocker count must be reported prominently.

Example:

`Release Eligibility: BLOCKED`

`Blockers: 2`

Release Eligibility must not be represented as a percentage.

---

# Example Project Condition Summary

A valid top-level result may resemble:

**Functional Completeness:** 95%  
**Implementation Quality:** 93%  
**Intent Fidelity:** Strong  
**Verification Confidence:** Substantial  
**Posture Fitness:** Shared — Adequate  
**WGS Conformance:** 100% — 18/18 applicable requirements satisfied  
**DRS Conformance:** 94% — 31/33 applicable requirements satisfied  
**Lifecycle Fitness:** Appropriate  
**Release Eligibility:** BLOCKED  
**Blockers:** 2  

**Findings:** 2 Required · 6 Should · 9 Could · 4 Observations

These results coexist without being mathematically collapsed into an overall score.

A project may therefore be highly complete, well engineered, and still legitimately blocked from release.

---

# Finding Model

Detailed findings bridge evidence to the assessment profile.

Every significant finding should identify, where applicable:

- Finding title.
- Finding class.
- Evaluation area.
- Authority/provenance.
- Applicability.
- Satisfaction state where governance-related.
- Evidence.
- Impact.
- Consequence.
- Recommendation.
- Relevant project posture.
- Relevant governing standard and version.
- Relevant files, artifacts, tests, or source locations.

## Finding Classes

### Required

A change is necessary because of:

- Applicable governance.
- Correctness.
- Safety.
- A contradiction of explicit project requirements.
- A requirement of the project's claimed lifecycle, stability, publication, or release state.

### Should

A meaningful deficiency exists relative to project mission, engineering quality, operational fitness, or declared posture.

There must be a defensible reason the change materially improves the project.

### Could

A legitimate improvement or extension fits project intent but is discretionary.

Could findings must not be presented as deficiencies merely because the evaluator can imagine additional functionality.

### Observation

A relevant fact, tradeoff, unusual design choice, emerging debt, uncertainty, or future concern that does not justify prescribing a change.

## Do Not Change

The Evaluator may explicitly identify an unusual or tempting-to-modify design as appropriate.

This is not a fifth severity level.

It is an affirmative evaluator judgment used when changing the design would add complexity, violate project intent, or solve a problem the project does not have.

---

# Finding Authority and Provenance

The Evaluator must distinguish at least these sources of authority:

## Governance Requirement

The finding derives from an applicable City Hall standard.

The report must identify the standard and relevant evidence.

## Project Requirement

The finding derives from the project's own PPS, constraints, boundaries, success/failure criteria, architecture, or other authoritative project record.

## Engineering Recommendation

The finding is evaluator judgment based on implementation evidence and engineering reasoning.

It must not be phrased as a City Hall mandate.

## Adoption Recommendation

The finding derives from obstacles or improvements associated with the declared Personal, Shared, or Adoptable posture.

It must not be presented as governance unless an applicable standard independently establishes the same requirement.

This provenance distinction is mandatory for significant prescriptive findings.

---

# Report Contract

Each evaluation must produce two complementary views.

## Project Condition Summary

A concise assessment showing:

- Project identity and evaluated version/state.
- Declared adoption posture.
- WGS lifecycle.
- Applicable governance.
- Assessment profile.
- Governance conformance by standard.
- Release eligibility when applicable.
- Blocker count.
- Finding counts.

This section answers:

> Where does the project stand?

## Detailed Evaluation Report

A narrative and evidence-backed examination explaining:

- What is sound.
- What is deficient.
- What is incomplete.
- What is unverified.
- What creates operational or adoption friction.
- What violates governance.
- What blocks a lifecycle or release transition.
- What should be improved.
- What could optionally be improved.
- What unusual decisions are appropriate and should remain unchanged.

This section answers:

> Why does the project stand there, and what deserves attention?

The report must prioritize meaningful conclusions rather than producing an indiscriminate wall of equally weighted observations.

---

# Evaluation Run Record

Each evaluation should preserve enough provenance to reproduce or interpret the assessment later.

The run record should include, at minimum:

- Project identity.
- Project version, commit, snapshot, or equivalent examined state where available.
- Evaluation timestamp.
- Declared adoption posture.
- WGS lifecycle state.
- Applicable standards and their versions.
- Evidence or project material supplied.
- Deterministic validators, tests, or checks whose results were used.
- Reasoning provider.
- Model identifier.
- Relevant reasoning/evaluation configuration.
- Report identity.

The purpose is to distinguish changes caused by:

- Project evolution.
- Governance evolution.
- Evaluator configuration changes.
- Reasoning-model changes.

The exact storage schema and artifact format are deferred to implementation design.

---

# Reasoning Backend

The Evaluator is expected to use a high-capability reasoning model for deep project examination.

The reasoning backend must be configurable.

The initial implementation is expected to support a frontier hosted model suitable for large-context, high-reasoning code and document analysis. OpenAI is the expected normal provider, but OpenAI is not a permanent architectural dependency.

Provider and model selection must not be embedded in the evaluation methodology.

Changing the configured reasoning backend must not require redefining:

- Evaluation criteria.
- Adoption postures.
- Applicability rules.
- Finding classes.
- Governance semantics.
- Assessment profile.
- Report contract.

Provider, model, reasoning level, context behavior, timeout/retry policy, and credential references may be implementation configuration.

Credentials must not be stored directly in evaluation reports or committed project configuration.

A small provider boundary is sufficient.

A generalized plugin ecosystem or universal LLM-provider abstraction is not required.

---

# Deterministic Evidence and Model Judgment

The Evaluator should use deterministic evidence where deterministic tooling is appropriate.

Examples include:

- Existing City Hall validators.
- Tests.
- Build results.
- Linters.
- Manifest parsers.
- File inventories.
- Hash verification.
- Schema validation.
- Static-analysis output.

The reasoning model should not replace deterministic checks merely because it can approximate them.

The preferred responsibility split is:

> Local/deterministic preparation → reasoning evaluation → local report preservation

City Hall and project records determine responsibility.

Deterministic tools establish facts where practical.

The reasoning model interprets the project as a whole and makes engineering judgments.

The report records both evidence and judgment.

---

# Operational Personas

## Project Operator

Initiates an evaluation, supplies or selects the project, declares its current adoption posture, and uses the resulting report to decide what deserves attention.

## Project Maintainer

Uses detailed findings to understand deficiencies, technical debt, governance responsibilities, and potential improvements.

The operator and maintainer may be the same person.

## Implementation Agent

Consumes the evaluation report as input to later remediation or development work.

The Implementation Agent is outside the Evaluator's authority boundary. The Evaluator may recommend; another explicitly authorized agent performs changes.

## Reasoning Backend

Consumes prepared project context and evidence and returns structured and narrative analysis according to the Evaluator's contract.

The backend is an implementation participant, not the authority that defines City Hall requirements.

---

# Technical Direction

The project should be implemented as a command-oriented analysis tool unless implementation discovery identifies a material reason to choose another primary delivery shape.

Expected governance:

- **PPS** for project intent.
- **WGS** for workspace registration, lifecycle, manifests, and placement.
- **CTS** for the evaluator's command surface if implemented as a CLI.
- Other standards only where the evaluator's eventual implementation actually creates a governed surface requiring them.

The implementation should separate:

1. Project/evidence preparation.
2. Governance applicability and deterministic evidence.
3. Reasoning-backend invocation.
4. Assessment/report interpretation.
5. Evaluation artifact preservation.

This is an architectural direction, not a prescribed class structure or repository layout.

The implementation language, concrete framework, serialization format, exact provider API, report storage format, and internal module design are deliberately deferred to implementation architecture.

---

# Constraints

The Evaluator must:

- Evaluate one project at a time.
- Remain read-only with respect to the evaluated project.
- Never silently remediate findings.
- Preserve the distinction between fact, governance requirement, project requirement, and evaluator judgment.
- Determine applicability before treating an absent requirement as deficient.
- Treat N/A and Deferred as legitimate states.
- Preserve governance blockers even when project completeness and quality are high.
- Avoid a single overall project score.
- Use numeric scores only where the underlying property can be meaningfully expressed numerically.
- Preserve categorical assessments where numerical precision would be misleading.
- Scale evaluation scope and expectations according to Personal, Shared, or Adoptable posture.
- Avoid penalizing Personal projects for intentionally personal design choices.
- Preserve evidence for significant conclusions.
- Identify uncertainty rather than inventing evidence.
- Allow the reasoning provider/model to be changed through configuration.
- Preserve provider/model identity in evaluation provenance.
- Avoid embedding secrets in reports or committed configuration.
- Remain understandable and maintainable without requiring an elaborate provider/plugin architecture.
- Prefer existing deterministic validation evidence over model inference when the fact can be established deterministically.

---

# Success Criteria

The project is successful when:

1. An operator can submit one governed project for deliberate deep evaluation.

2. The operator can declare the project as Personal, Shared, or Adoptable and receive an evaluation appropriate to that intent.

3. The Evaluator can establish project intent, lifecycle, applicable governance, implementation state, and available evidence before issuing conclusions.

4. The Evaluator can distinguish Functional Completeness from Implementation Quality.

5. A project can receive a high completeness or quality score while simultaneously being reported as release-blocked when an applicable standard requires it.

6. Governance conformance is reported separately for each applicable standard using both a percentage and satisfied/applicable counts.

7. Governance controls can be represented as Satisfied, Unsatisfied, Deferred, or N/A without treating Deferred or N/A as failures.

8. Release eligibility is reported plainly as PASS, BLOCKED, or NOT APPLICABLE.

9. The Evaluator produces meaningful implementation and architectural feedback that goes beyond checking governance artifacts.

10. The Evaluator identifies creator-specific assumptions and judges their importance according to declared adoption posture.

11. Significant findings identify whether their authority comes from governance, project requirements, engineering judgment, or adoption concerns.

12. The report distinguishes Required, Should, Could, and Observation findings.

13. The Evaluator can explicitly recognize appropriate designs that should not be changed.

14. The report distinguishes unsupported claims from demonstrated failures.

15. The report provides enough evidence and reasoning that a maintainer or later implementation agent can understand why a conclusion was reached.

16. An evaluation run preserves enough provenance to identify the project state, governance versions, evidence, and reasoning model that produced it.

17. Changing the configured reasoning provider or model does not require changing the evaluation methodology or report semantics.

18. The Evaluator completes its work without modifying the evaluated project.

---

# Failure Criteria

The project has failed or requires proposal rework if:

- It becomes primarily a release-gate checker equivalent to the existing multi-project pipeline.
- It collapses project condition into one overall score.
- It treats release readiness, functional completeness, and implementation quality as the same property.
- It treats every City Hall standard as applicable to every project.
- It penalizes projects for requirements that are legitimately N/A or Deferred.
- It treats Personal projects as deficient merely because they are not independently adoptable.
- It cannot distinguish governance requirements from evaluator recommendations.
- It reports model judgment as deterministic fact without evidence.
- It treats missing verification evidence as proof that functionality is broken.
- It generates large numbers of speculative features instead of evaluating the project that exists.
- It automatically modifies or remediates evaluated projects.
- It requires a specific permanent reasoning provider or model for the evaluation methodology to function.
- Provider abstraction grows into a major subsystem unrelated to the evaluation mission.
- Reports become too shallow to explain their scores and findings.
- Reports become so exhaustive and unprioritized that meaningful findings are obscured.
- Evaluation results cannot be traced to the project state and governance context that produced them.

---

# Risk Assessment

## Technical Risk — Context Volume

Large projects may exceed the practical context available to the configured reasoning backend.

**Mitigation:** Implementation architecture should support deliberate evidence preparation, prioritization, and project-aware context selection without reducing the evaluation to isolated snippets.

The exact context-management strategy is deferred.

## Technical Risk — Model Variability

Different reasoning models or model versions may produce different engineering judgments or scores from substantially identical evidence.

**Mitigation:** Preserve model/provider provenance, maintain stable evaluation criteria and report semantics, use deterministic evidence where possible, and avoid implying that subjective scores are mathematically exact.

## Technical Risk — False Precision

Percentage scores can appear more objective than the underlying evidence supports.

**Mitigation:** Limit percentages to dimensions where they provide useful state information, accompany them with narrative justification, and use categorical assessments elsewhere.

## Governance Risk — Applicability Errors

The Evaluator may incorrectly apply a standard or control to a project whose class, lifecycle, posture, or current claim does not activate it.

**Mitigation:** Make applicability an explicit evaluation stage and preserve N/A and Deferred states.

## Governance Risk — Recommendation Inflation

Model-generated engineering preferences may be phrased as if City Hall requires them.

**Mitigation:** Require finding provenance and distinguish Governance Requirement, Project Requirement, Engineering Recommendation, and Adoption Recommendation.

## Project Risk — Feature-Generation Drift

A powerful reasoning model may generate extensive possible enhancements unrelated to project mission.

**Mitigation:** Improvement analysis occurs only after project intent is established. Could findings must remain compatible with existing intent, and the Evaluator may explicitly recommend Do Not Change.

## Project Risk — Evaluation Bloat

Deep evaluation may produce reports so large that important conclusions become difficult to identify.

**Mitigation:** Require a compact Project Condition Summary, prioritized findings, and detailed evidence beneath them rather than treating every observation equally.

## Security/Trust Risk — Sensitive Project Material

Project source, configuration, or documentation sent to a hosted reasoning provider may contain sensitive material.

**Mitigation:** The implementation must make provider selection explicit and must not silently send credentials or known secrets as evaluation material. Detailed secret-detection and redaction behavior is deferred to implementation/security design.

## Dependency Risk — Hosted Reasoning Provider

Hosted API availability, pricing, model names, context limits, and capabilities may change.

**Mitigation:** Keep provider/model selection configurable and preserve a small backend boundary without making universal provider compatibility a primary project goal.

## Maintenance Risk — Governance Evolution

City Hall standards will change over time.

**Mitigation:** Evaluations record the standard versions applied. Evaluation logic should consume current governance rather than silently freezing old requirements into model instructions.

## Maintenance Risk — Score Drift

Changes to prompts, reasoning models, or evaluation methodology may alter scores over time.

**Mitigation:** Preserve evaluation configuration and model provenance. Scores are project-condition indicators, not immutable scientific measurements.

---

# Roadmap

## Phase 1 — Evaluation Spine

Establish the minimum durable structures required to represent an evaluation.

This phase should establish:

- Project evaluation identity.
- Evaluation-run record.
- Adoption posture.
- Applicability states.
- Assessment profile.
- Finding model and provenance.
- Governance/evidence inputs.
- Reasoning-backend configuration boundary.
- Report artifact contract.

The objective is to make the evaluation itself a coherent, preservable object before attempting sophisticated analysis.

## Phase 2 — Core Evaluation Workflow

Implement the end-to-end one-project evaluation workflow.

The minimum workflow should:

- Accept/select one project.
- Establish project context.
- Accept Personal/Shared/Adoptable posture.
- Identify applicable governance.
- Collect available deterministic evidence.
- Prepare project material for reasoning.
- Invoke the configured reasoning backend.
- Produce the multidimensional assessment profile.
- Produce detailed findings.
- Produce the narrative evaluation report.
- Preserve the evaluation-run record.

The first complete version should prove that a project can be highly complete and well engineered while independently reporting governance deficiencies and a blocked release state.

## Phase 3 — Verification

Verify that the evaluator itself produces trustworthy and stable-enough results.

Verification should include representative project cases such as:

- Personal project with intentionally creator-specific assumptions.
- Shared project with moderate external-user friction.
- Adoptable project with meaningful onboarding requirements.
- Functionally complete project blocked by a delivery standard.
- Low-completeness but high-quality implementation.
- Governance-compliant project with implementation-quality problems.
- Project with insufficient verification evidence.
- Mixed-surface project governed by more than one delivery standard.
- Project with legitimately Deferred and N/A controls.

Verification should test both deterministic evaluation behavior and the quality of model-produced reasoning.

## Phase 4 — Release Readiness

Apply the Evaluator's own applicable City Hall delivery standard.

If the implementation remains a command tool, CTS governs its public command contract, output behavior, machine-readable mode, exit codes, destructive-operation posture, examples, and release verification.

Release work must not be confused with evaluation-engine completeness.

---

# First-Version Success Boundary

The first version does not need to solve every possible project-analysis problem.

A successful first version must be able to take one reasonably sized City Hall project, its relevant governance and evidence, and produce a useful report containing:

- Declared posture.
- Functional Completeness.
- Implementation Quality.
- Intent Fidelity.
- Verification Confidence.
- Posture Fitness.
- Governance Conformance by applicable standard.
- Lifecycle Fitness.
- Release Eligibility when applicable.
- Blocker count.
- Required/Should/Could/Observation findings.
- Evidence-backed narrative explanation.
- Evaluation-run provenance.

It must inspect implementation deeply enough to produce meaningful engineering findings beyond governance conformance.

It must remain read-only.

---

# Relationship to Existing Work

The existing multi-project analysis pipeline remains a separate system optimized for evaluating multiple projects and identifying governance/release condition at portfolio scale.

The Single-Project Evaluator does not replace it.

The systems may eventually share standards, validators, evidence formats, or project metadata where doing so is naturally useful, but shared implementation is not required by this proposal.

No integration between the two systems is required for the first version.

---

# Implementation Handoff

This proposal is the authoritative design boundary for initial implementation.

The formation conversation accompanying this proposal should be retained as supporting rationale and design history.

Before broad implementation, the implementation agent should scaffold the remaining City Hall project records required by WGS/PPS and the selected delivery standard, including the entity-named project manifest and agent/read-first documentation.

The implementation agent may choose implementation details that this proposal deliberately leaves unresolved, including:

- Final project name.
- Programming language.
- Concrete framework.
- Repository layout.
- Internal classes/modules.
- Provider adapter implementation.
- API request structure.
- Context-management strategy.
- Report serialization/storage format.
- Evaluation-run schema.
- Exact score calculation methodology.
- CLI command names and flags.
- Credential mechanism.
- Testing framework.

Those choices must remain consistent with the mission, boundaries, constraints, success/failure criteria, and evaluation semantics defined here.

If implementation discovery shows that one of those choices would materially change the project's mission, authority boundary, posture model, assessment model, or evaluation semantics, the PPS should be revised rather than allowing implementation to redefine the project silently.

---

# Proposal Exit

This proposal is **Ready** for implementation handoff.

The remaining unresolved matters are implementation decisions rather than unresolved project identity.

The entity-named project manifest is intentionally **queued for scaffolding during City Hall project initialization** rather than invented inside this proposal.

Broad implementation may begin after the required WGS/PPS project records have been scaffolded and the project has been registered according to City Hall governance.