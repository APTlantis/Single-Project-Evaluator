from __future__ import annotations

import json
import hashlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from single_project_evaluator.cli import main
from single_project_evaluator.collector import _git_commit, collect_project_evidence
from single_project_evaluator.context import extract_project_context
from single_project_evaluator.analysis import prepare_evaluation_context
from single_project_evaluator.backend import create_backend
from single_project_evaluator.models import AdoptionPosture, ApplicabilityState, SurfaceKind
from single_project_evaluator.request_package import build_reasoning_request, build_response_template
from single_project_evaluator.response_parser import ResponseValidationError, parse_backend_response
from single_project_evaluator.serialization import evaluation_from_dict
from single_project_evaluator import __version__


def _assessment(
    *,
    posture_fitness: str,
    release_eligibility: str = "NOT APPLICABLE",
    blockers: int = 0,
    functional_completeness: int | None = 80,
    implementation_quality: int | None = 75,
    intent_fidelity: str = "Strong",
    verification_confidence: str = "Partial",
    lifecycle_fitness: str = "Appropriate",
) -> dict:
    return {
        "functional_completeness": functional_completeness,
        "implementation_quality": implementation_quality,
        "intent_fidelity": intent_fidelity,
        "verification_confidence": verification_confidence,
        "posture_fitness": posture_fitness,
        "lifecycle_fitness": lifecycle_fitness,
        "release_eligibility": release_eligibility,
        "blockers": blockers,
    }


def _finding(
    *,
    title: str,
    finding_class: str = "observation",
    authority: str = "engineering_recommendation",
    applicability: str | None = None,
    recommendation: str | None = None,
    evidence: list[str] | None = None,
) -> dict:
    return {
        "title": title,
        "finding_class": finding_class,
        "area": "Adoption Posture",
        "authority": authority,
        "applicability": applicability,
        "evidence": evidence or ["README.md"],
        "impact": "This verifies posture-specific evaluator semantics.",
        "consequence": "The report should preserve the distinction without collapsing it into one score.",
        "recommendation": recommendation,
    }


def _response(
    *,
    posture_fitness: str,
    release_eligibility: str = "NOT APPLICABLE",
    blockers: int = 0,
    findings: list[dict] | None = None,
    functional_completeness: int | None = 80,
    implementation_quality: int | None = 75,
    governance_conformance: dict[str, str] | None = None,
) -> dict:
    return {
        "assessment": _assessment(
            posture_fitness=posture_fitness,
            release_eligibility=release_eligibility,
            blockers=blockers,
            functional_completeness=functional_completeness,
            implementation_quality=implementation_quality,
        ),
        "findings": findings or [],
        "governance_conformance": governance_conformance or {},
        "uncertainties": ["Fixture response intentionally limits evidence to a small project shape."],
        "narrative": "## Fixture Narrative\n\nThis fixture exercises posture-specific evaluation semantics.",
    }


class SpineTests(unittest.TestCase):
    def test_cli_can_print_version(self) -> None:
        stdout = StringIO()

        with redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn(__version__, stdout.getvalue())

    def test_collect_project_evidence_detects_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Example\n", encoding="utf-8")
            (root / "project.manifest.toml").write_text("[project]\nname='Example'\n", encoding="utf-8")

            evidence = collect_project_evidence(root)

            self.assertEqual(evidence.project_name, root.name)
            self.assertEqual(evidence.files_examined, 2)
            self.assertIn("readme", evidence.detected_records)
            self.assertIn("manifest", evidence.detected_records)
            self.assertEqual(len(evidence.authority_records), 2)
            self.assertTrue(evidence.authority_records[0].sha256)

    def test_collect_project_evidence_detects_named_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "File Cabinet.manifest.toml").write_text("[project]\nname='File Cabinet'\n", encoding="utf-8")

            evidence = collect_project_evidence(root)

            self.assertEqual(evidence.detected_records["manifest"], ["File Cabinet.manifest.toml"])

    def test_collect_project_evidence_ignores_generated_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "docs"
            generated = root / "bin" / "Release" / "net10.0-windows" / "win-x64"
            docs.mkdir()
            generated.mkdir(parents=True)
            (docs / "Project Proposal - Example.md").write_text("# PPS\n", encoding="utf-8")
            (docs / "Desktop Application Release Standard.md").write_text("# DRS\n", encoding="utf-8")
            (generated / "netstandard.dll").write_bytes(b"binary")
            (generated / "README.md").write_text("# Generated readme\n", encoding="utf-8")

            evidence = collect_project_evidence(root)

            all_paths = [file.path for file in evidence.files]
            roles = {file.path: file.role for file in evidence.files}
            self.assertIn("docs/Project Proposal - Example.md", all_paths)
            self.assertIn("docs/Desktop Application Release Standard.md", all_paths)
            self.assertNotIn("bin/Release/net10.0-windows/win-x64/netstandard.dll", all_paths)
            self.assertEqual(roles["docs/Project Proposal - Example.md"], "documentation")
            self.assertEqual(
                evidence.detected_records["governance"],
                ["docs/Desktop Application Release Standard.md"],
            )
            self.assertEqual(len(evidence.authority_records), 2)
            records_by_path = {record.path: record for record in evidence.authority_records}
            self.assertIn("# PPS", records_by_path["docs/Project Proposal - Example.md"].excerpt)

    def test_collect_project_evidence_classifies_release_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_dir = root / "artifacts" / "publish" / "win-x64"
            artifact_dir.mkdir(parents=True)
            (artifact_dir / "README.md").write_text("# Packaged readme\n", encoding="utf-8")

            evidence = collect_project_evidence(root)

            self.assertEqual(evidence.files[0].path, "artifacts/publish/win-x64/README.md")
            self.assertEqual(evidence.files[0].role, "release_artifact")
            self.assertEqual(
                evidence.detected_records["release_documentation"],
                ["artifacts/publish/win-x64/README.md"],
            )
            self.assertNotIn("readme", evidence.detected_records)

    def test_git_commit_uses_command_scoped_safe_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()

            with patch("single_project_evaluator.collector.subprocess.run") as run:
                run.return_value.stdout = "abc123\n"

                commit = _git_commit(root)

            self.assertEqual(commit, "abc123")
            args = run.call_args.args[0]
            self.assertEqual(args[:3], ["git", "-c", f"safe.directory={root.as_posix()}"])

    def test_extract_project_context_prefers_manifest_then_pps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "docs"
            docs.mkdir()
            (root / "project.manifest.toml").write_text(
                "\n".join(
                    [
                        "[project]",
                        'name = "Manifest Name"',
                        'class = ["Command Tool", "Analysis Tool"]',
                        'lifecycle_state = "Planning"',
                        'adoption_posture = "Shared"',
                        "",
                        "[governance]",
                        'primary_standard = "PPS"',
                        'expected_delivery_standard = "CTS"',
                        'applicable = ["WGS", "PPS", "CTS"]',
                        "",
                        "[intent]",
                        'pps = "docs/Project Proposal - Example.md"',
                    ]
                ),
                encoding="utf-8",
            )
            (docs / "Project Proposal - Example.md").write_text(
                "\n".join(
                    [
                        "# Project Proposal - Example",
                        "",
                        "**WGS Lifecycle State:** Implementation",
                        "**Primary Governing Standard:** DRS",
                    ]
                ),
                encoding="utf-8",
            )

            evidence = collect_project_evidence(root)
            context = extract_project_context(root, evidence)

            self.assertEqual(context.project_name.value, "Manifest Name")
            self.assertEqual(context.lifecycle_state.value, "Planning")
            self.assertEqual(context.primary_standard.value, "PPS")
            self.assertEqual(context.pps_path.value, "docs/Project Proposal - Example.md")

    def test_extract_project_context_reads_city_hall_manifest_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            drs_path = root / "standards" / "DRS" / "README.md"
            wgs_path = root / "standards" / "WGS" / "README.md"
            drs_path.parent.mkdir(parents=True)
            wgs_path.parent.mkdir(parents=True)
            (root / "File Cabinet.manifest.toml").write_text(
                "\n".join(
                    [
                        "[entity]",
                        'title = "File Cabinet"',
                        'kind = "project"',
                        "",
                        "[project]",
                        'title = "File Cabinet"',
                        'type = "tool"',
                        'stage = "production"',
                        "",
                        "[governance]",
                        'primary_standard = "DRS"',
                        f'primary_standard_path = "{drs_path.as_posix()}"',
                        'additional_standards = ["WGS", "PPS", "AAMHS"]',
                        f'additional_standard_paths = ["{wgs_path.as_posix()}"]',
                    ]
                ),
                encoding="utf-8",
            )

            evidence = collect_project_evidence(root)
            context = extract_project_context(root, evidence)

            self.assertEqual(context.project_name.value, "File Cabinet")
            self.assertEqual(context.project_classes.value, ["tool", "project"])
            self.assertEqual(context.lifecycle_state.value, "production")
            self.assertEqual(context.primary_standard.value, "DRS")
            self.assertEqual(context.applicable_governance.value, ["DRS", "WGS", "PPS", "AAMHS"])
            self.assertEqual(
                context.governance_standard_paths.value,
                {"DRS": drs_path.as_posix(), "WGS": wgs_path.as_posix()},
            )

    def test_prepare_evaluation_context_summarizes_surfaces_and_governance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            standard_path = root / "standards" / "DRS" / "README.md"
            standard_path.parent.mkdir(parents=True)
            standard_path.write_text(
                "# Desktop Application Release Standard\n\n**Version:** 2026.08\n\nRelease rules.\n",
                encoding="utf-8",
            )
            (root / "File Cabinet.manifest.toml").write_text(
                "\n".join(
                    [
                        "[project]",
                        'title = "File Cabinet"',
                        'type = "tool"',
                        'stage = "production"',
                        "",
                        "[governance]",
                        'primary_standard = "DRS"',
                        f'primary_standard_path = "{standard_path.as_posix()}"',
                        'additional_standards = ["WGS", "PPS"]',
                    ]
                ),
                encoding="utf-8",
            )
            (root / "FileCabinet.vbproj").write_text("<Project />\n", encoding="utf-8")
            (root / "MainWindow.xaml").write_text("<Window />\n", encoding="utf-8")
            (root / "Program.vb").write_text("Module Program\nEnd Module\n", encoding="utf-8")

            evidence = collect_project_evidence(root)
            context = extract_project_context(root, evidence)
            prepared = prepare_evaluation_context(evidence, context)

            self.assertEqual(prepared.inventory_summary.role_counts["source"], 2)
            self.assertGreater(prepared.inventory_summary.total_size_bytes, 0)
            self.assertEqual(prepared.surfaces[0].kind, SurfaceKind.DESKTOP_APP)
            self.assertEqual(prepared.surfaces[0].confidence, "strong")
            self.assertEqual(prepared.representative_files[0].path, "File Cabinet.manifest.toml")
            self.assertEqual(prepared.representative_files[0].reason, "authority record: manifest")
            snippets_by_path = {snippet.path: snippet for snippet in prepared.text_snippets}
            self.assertIn("Program.vb", snippets_by_path)
            self.assertTrue(snippets_by_path["Program.vb"].sha256)
            records = {record.standard: record for record in prepared.governance_applicability}
            self.assertEqual(records["DRS"].state, ApplicabilityState.DEFERRED)
            self.assertIn("WGS", records)
            self.assertEqual(len(prepared.governance_materials), 1)
            self.assertEqual(prepared.governance_materials[0].standard, "DRS")
            self.assertEqual(prepared.governance_materials[0].path, standard_path.as_posix())
            self.assertIn("Release rules.", prepared.governance_materials[0].excerpt)
            self.assertEqual(prepared.governance_materials[0].standard_version, "2026.08")
            self.assertTrue(prepared.governance_materials[0].sha256)

    def test_prepare_evaluation_context_records_missing_governance_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_standard = root / "standards" / "DRS" / "README.md"
            (root / "project.manifest.toml").write_text(
                "\n".join(
                    [
                        "[project]",
                        'name = "Example"',
                        "",
                        "[governance]",
                        'primary_standard = "DRS"',
                        f'primary_standard_path = "{missing_standard.as_posix()}"',
                    ]
                ),
                encoding="utf-8",
            )

            evidence = collect_project_evidence(root)
            context = extract_project_context(root, evidence)
            prepared = prepare_evaluation_context(evidence, context)

            self.assertEqual(len(prepared.governance_materials), 1)
            material = prepared.governance_materials[0]
            self.assertEqual(material.standard, "DRS")
            self.assertEqual(material.size_bytes, 0)
            self.assertEqual(material.sha256, "")
            self.assertIsNotNone(material.read_error)

    def test_prepare_evaluation_context_infers_deterministic_evidence_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tests_dir = root / "tests"
            verification_dir = root / "artifacts" / "verification"
            publish_dir = root / "artifacts" / "publish"
            tests_dir.mkdir()
            verification_dir.mkdir(parents=True)
            publish_dir.mkdir(parents=True)
            (root / "pyproject.toml").write_text("[project]\nname='Example'\n", encoding="utf-8")
            (tests_dir / "test_example.py").write_text("def test_example():\n    assert True\n", encoding="utf-8")
            (verification_dir / "release-hash.txt").write_text("abc  artifact\n", encoding="utf-8")
            (publish_dir / "Example.exe").write_bytes(b"binary")

            evidence = collect_project_evidence(root)
            context = extract_project_context(root, evidence)
            prepared = prepare_evaluation_context(evidence, context)

            categories_by_path = {
                (signal.category, signal.path)
                for signal in prepared.deterministic_evidence
            }
            self.assertIn(("build_configuration", "pyproject.toml"), categories_by_path)
            self.assertIn(("test_source", "tests/test_example.py"), categories_by_path)
            self.assertIn(("verification_record", "artifacts/verification/release-hash.txt"), categories_by_path)
            self.assertIn(("release_artifact", "artifacts/publish/Example.exe"), categories_by_path)

    def test_prepare_evaluation_context_infers_mixed_surface_governance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text("[project]\nname='Example'\n", encoding="utf-8")
            (root / "package.json").write_text('{"scripts":{"build":"vite build"}}\n', encoding="utf-8")
            (root / "app.py").write_text("print('command surface')\n", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "App.tsx").write_text("export function App() { return null }\n", encoding="utf-8")

            evidence = collect_project_evidence(root)
            context = extract_project_context(root, evidence)
            prepared = prepare_evaluation_context(evidence, context)

            surface_kinds = {surface.kind for surface in prepared.surfaces}
            governance_states = {
                applicability.standard: applicability.state for applicability in prepared.governance_applicability
            }
            self.assertIn(SurfaceKind.COMMAND_TOOL, surface_kinds)
            self.assertIn(SurfaceKind.WEBSITE, surface_kinds)
            self.assertEqual(governance_states["CTS"], ApplicabilityState.DEFERRED)
            self.assertEqual(governance_states["WDS"], ApplicabilityState.DEFERRED)

    def test_prepare_evaluation_context_bounds_text_snippets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("A" * 2000, encoding="utf-8")

            evidence = collect_project_evidence(root)
            context = extract_project_context(root, evidence)
            prepared = prepare_evaluation_context(evidence, context)

            self.assertEqual(len(prepared.text_snippets), 1)
            self.assertTrue(prepared.text_snippets[0].truncated)
            self.assertLessEqual(prepared.text_snippets[0].chars, 1220)

    def test_create_backend_returns_noop_backend(self) -> None:
        backend = create_backend("none")

        self.assertEqual(backend.identity.provider, "none")
        self.assertEqual(backend.identity.model_identifier, "phase-1-spine")

    def test_create_backend_requires_response_file_for_file_backend(self) -> None:
        with self.assertRaises(ValueError):
            create_backend("response-file")

    def test_create_backend_requires_api_key_for_openai_backend(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError):
                create_backend("openai", model="gpt-test")

    def test_create_backend_requires_model_for_openai_backend(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=True):
            with self.assertRaises(ValueError):
                create_backend("openai")

    def test_create_backend_rejects_invalid_openai_retries(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=True):
            with self.assertRaises(ValueError):
                create_backend("openai", model="gpt-test", retries=4)

    def test_openai_backend_blocks_likely_sensitive_outbound_context(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp) / "out"
            (project / "README.md").write_text(
                "# Example\n\nOPENAI_API_KEY = \"sk-" + ("a" * 32) + "\"\n",
                encoding="utf-8",
            )
            stdout = StringIO()
            stderr = StringIO()

            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=True):
                with patch("single_project_evaluator.backend.urlopen") as openai_call:
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        exit_code = main(
                            [
                                "evaluate",
                                "--project",
                                str(project),
                                "--posture",
                                AdoptionPosture.SHARED.value,
                                "--out",
                                str(output),
                                "--backend",
                                "openai",
                                "--model",
                                "gpt-test",
                                "--json",
                            ]
                        )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(openai_call.call_count, 0)
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error_type"], "ValueError")
            self.assertIn("Hosted OpenAI evaluation blocked", payload["error"])
            self.assertIn("openai_api_key", payload["error"])
            self.assertIn("README.md", payload["error"])
            self.assertFalse(output.exists())

    def test_reasoning_request_wraps_context_without_assessment(self) -> None:
        context_bundle = {
            "run": {
                "project_root": "D:/Example",
                "declared_posture": "shared",
            },
            "evidence": {},
            "context": {},
            "prepared_context": {},
        }

        request = build_reasoning_request(context_bundle)

        self.assertEqual(request["purpose"], "single_project_evaluation")
        self.assertEqual(request["context_bundle"], context_bundle)
        self.assertNotIn("assessment", request["context_bundle"])
        self.assertIn("response_contract", request)
        self.assertIn("instructions", request)

    def test_examples_readme_documents_core_workflows(self) -> None:
        examples_readme = Path(__file__).resolve().parents[1] / "examples" / "README.md"
        text = examples_readme.read_text(encoding="utf-8")

        for command in [
            "--version",
            "evaluate --project",
            "--backend none",
            "validate-response",
            "--backend response-file",
            "complete-run",
            "--backend openai",
            "list-runs",
            "show-run",
            "validate-run",
        ]:
            self.assertIn(command, text)
        self.assertIn("place `--out` outside the target project tree", text)
        self.assertIn("uncertainty:", text)

    def test_response_template_matches_parser_contract(self) -> None:
        template = build_response_template()

        assessment, findings, governance, uncertainties, narrative = parse_backend_response(template)

        self.assertIsNone(assessment.functional_completeness)
        self.assertEqual(findings[0].finding_class.value, "observation")
        self.assertEqual(governance, {})
        self.assertEqual(len(uncertainties), 1)
        self.assertIsNotNone(narrative)

    def test_response_template_uses_declared_posture(self) -> None:
        template = build_response_template("personal")

        assessment, _, _, _, _ = parse_backend_response(template, expected_posture="personal")

        self.assertEqual(assessment.posture_fitness, "Personal - Adequate")

    def test_parse_backend_response_accepts_valid_shape(self) -> None:
        response = {
            "assessment": {
                "functional_completeness": 80,
                "implementation_quality": 75,
                "intent_fidelity": "Strong",
                "verification_confidence": "Partial",
                "posture_fitness": "Shared - Adequate",
                "lifecycle_fitness": "Appropriate",
                "release_eligibility": "NOT APPLICABLE",
                "blockers": 0,
            },
            "findings": [
                {
                    "title": "Example",
                    "finding_class": "observation",
                    "area": "Testing",
                    "authority": "engineering_recommendation",
                    "applicability": None,
                    "evidence": ["README.md"],
                    "impact": "Useful context.",
                    "consequence": "No action required.",
                    "recommendation": None,
                }
            ],
            "governance_conformance": {"DRS": "80% (4/5 applicable controls satisfied)"},
            "uncertainties": ["No tests were supplied."],
        }

        assessment, findings, governance, uncertainties, narrative = parse_backend_response(response)

        self.assertEqual(assessment.functional_completeness, 80)
        self.assertEqual(findings[0].finding_class.value, "observation")
        self.assertEqual(governance["DRS"], "80% (4/5 applicable controls satisfied)")
        self.assertEqual(uncertainties, ["No tests were supplied."])
        self.assertIsNone(narrative)

    def test_parse_backend_response_rejects_invalid_scores(self) -> None:
        response = {
            "assessment": {
                "functional_completeness": 101,
                "implementation_quality": None,
                "intent_fidelity": "Strong",
                "verification_confidence": "Partial",
                "posture_fitness": "Shared - Adequate",
                "lifecycle_fitness": "Appropriate",
                "release_eligibility": "NOT APPLICABLE",
                "blockers": 0,
            },
            "findings": [],
        }

        with self.assertRaises(ResponseValidationError):
            parse_backend_response(response)

    def test_parse_backend_response_rejects_invalid_assessment_vocabulary(self) -> None:
        response = {
            "assessment": {
                "functional_completeness": None,
                "implementation_quality": None,
                "intent_fidelity": "Pretty Good",
                "verification_confidence": "Partial",
                "posture_fitness": "Shared - Adequate",
                "lifecycle_fitness": "Appropriate",
                "release_eligibility": "NOT APPLICABLE",
                "blockers": 0,
            },
            "findings": [],
        }

        with self.assertRaises(ResponseValidationError):
            parse_backend_response(response)

    def test_parse_backend_response_rejects_blocked_without_blockers(self) -> None:
        response = {
            "assessment": {
                "functional_completeness": None,
                "implementation_quality": None,
                "intent_fidelity": "Strong",
                "verification_confidence": "Partial",
                "posture_fitness": "Shared - Adequate",
                "lifecycle_fitness": "Appropriate",
                "release_eligibility": "BLOCKED",
                "blockers": 0,
            },
            "findings": [],
        }

        with self.assertRaises(ResponseValidationError):
            parse_backend_response(response)

    def test_parse_backend_response_rejects_pass_with_blockers(self) -> None:
        response = {
            "assessment": {
                "functional_completeness": None,
                "implementation_quality": None,
                "intent_fidelity": "Strong",
                "verification_confidence": "Partial",
                "posture_fitness": "Shared - Adequate",
                "lifecycle_fitness": "Appropriate",
                "release_eligibility": "PASS",
                "blockers": 1,
            },
            "findings": [],
        }

        with self.assertRaises(ResponseValidationError):
            parse_backend_response(response)

    def test_parse_backend_response_rejects_blockers_without_required_unsatisfied_findings(self) -> None:
        response = _response(
            posture_fitness="Shared - Adequate",
            release_eligibility="BLOCKED",
            blockers=1,
            findings=[
                _finding(
                    title="Deferred release checklist mapping",
                    finding_class="observation",
                    authority="governance_requirement",
                    applicability="deferred",
                )
            ],
        )

        with self.assertRaises(ResponseValidationError):
            parse_backend_response(response)

    def test_parse_backend_response_rejects_hidden_required_unsatisfied_finding(self) -> None:
        response = _response(
            posture_fitness="Shared - Adequate",
            release_eligibility="PASS",
            blockers=0,
            findings=[
                _finding(
                    title="Required release checklist is absent",
                    finding_class="required",
                    authority="governance_requirement",
                    applicability="unsatisfied",
                )
            ],
        )

        with self.assertRaises(ResponseValidationError):
            parse_backend_response(response)

    def test_parse_backend_response_accepts_uncertainty_backed_observation(self) -> None:
        response = _response(
            posture_fitness="Shared - Adequate",
            findings=[
                _finding(
                    title="Verification evidence is incomplete",
                    finding_class="observation",
                    applicability=None,
                    evidence=["uncertainty: no test execution record was supplied"],
                )
            ],
        )

        assessment, findings, _, _, _ = parse_backend_response(response)

        self.assertEqual(assessment.release_eligibility, "NOT APPLICABLE")
        self.assertEqual(findings[0].evidence, ["uncertainty: no test execution record was supplied"])

    def test_parse_backend_response_rejects_required_unsatisfied_when_only_uncertain(self) -> None:
        response = _response(
            posture_fitness="Shared - Adequate",
            release_eligibility="BLOCKED",
            blockers=1,
            findings=[
                _finding(
                    title="Feature may be broken but evidence is missing",
                    finding_class="required",
                    authority="project_requirement",
                    applicability="unsatisfied",
                    evidence=["uncertainty: no runtime verification evidence was supplied"],
                )
            ],
        )

        with self.assertRaises(ResponseValidationError):
            parse_backend_response(response)

    def test_parse_backend_response_rejects_invalid_posture_fitness(self) -> None:
        response = {
            "assessment": {
                "functional_completeness": None,
                "implementation_quality": None,
                "intent_fidelity": "Strong",
                "verification_confidence": "Partial",
                "posture_fitness": "Shared - Pretty Good",
                "lifecycle_fitness": "Appropriate",
                "release_eligibility": "NOT APPLICABLE",
                "blockers": 0,
            },
            "findings": [],
        }

        with self.assertRaises(ResponseValidationError):
            parse_backend_response(response)

    def test_parse_backend_response_rejects_invalid_narrative(self) -> None:
        response = {
            "assessment": {
                "functional_completeness": None,
                "implementation_quality": None,
                "intent_fidelity": "Strong",
                "verification_confidence": "Partial",
                "posture_fitness": "Shared - Adequate",
                "lifecycle_fitness": "Appropriate",
                "release_eligibility": "NOT APPLICABLE",
                "blockers": 0,
            },
            "findings": [],
            "narrative": ["not", "a", "string"],
        }

        with self.assertRaises(ResponseValidationError):
            parse_backend_response(response)

    def test_parse_backend_response_rejects_finding_without_evidence(self) -> None:
        response = {
            "assessment": {
                "functional_completeness": None,
                "implementation_quality": None,
                "intent_fidelity": "Strong",
                "verification_confidence": "Partial",
                "posture_fitness": "Shared - Adequate",
                "lifecycle_fitness": "Appropriate",
                "release_eligibility": "NOT APPLICABLE",
                "blockers": 0,
            },
            "findings": [
                {
                    "title": "Unsupported finding",
                    "finding_class": "required",
                    "area": "Evidence",
                    "authority": "engineering_recommendation",
                    "applicability": None,
                    "evidence": [],
                    "impact": "This would be unsupported.",
                    "consequence": "The response should be rejected.",
                    "recommendation": None,
                }
            ],
        }

        with self.assertRaises(ResponseValidationError):
            parse_backend_response(response)

    def test_parse_backend_response_rejects_unstructured_governance_conformance(self) -> None:
        response = {
            "assessment": {
                "functional_completeness": None,
                "implementation_quality": None,
                "intent_fidelity": "Strong",
                "verification_confidence": "Partial",
                "posture_fitness": "Shared - Adequate",
                "lifecycle_fitness": "Appropriate",
                "release_eligibility": "NOT APPLICABLE",
                "blockers": 0,
            },
            "findings": [],
            "governance_conformance": {"PPS": "not evaluated"},
        }

        with self.assertRaises(ResponseValidationError):
            parse_backend_response(response)

    def test_parse_backend_response_rejects_inconsistent_governance_conformance_math(self) -> None:
        response = {
            "assessment": {
                "functional_completeness": None,
                "implementation_quality": None,
                "intent_fidelity": "Strong",
                "verification_confidence": "Partial",
                "posture_fitness": "Shared - Adequate",
                "lifecycle_fitness": "Appropriate",
                "release_eligibility": "NOT APPLICABLE",
                "blockers": 0,
            },
            "findings": [],
            "governance_conformance": {"PPS": "80% (3/4 applicable controls satisfied)"},
        }

        with self.assertRaises(ResponseValidationError):
            parse_backend_response(response)

    def test_parse_backend_response_rejects_impossible_governance_conformance_count(self) -> None:
        response = {
            "assessment": {
                "functional_completeness": None,
                "implementation_quality": None,
                "intent_fidelity": "Strong",
                "verification_confidence": "Partial",
                "posture_fitness": "Shared - Adequate",
                "lifecycle_fitness": "Appropriate",
                "release_eligibility": "NOT APPLICABLE",
                "blockers": 0,
            },
            "findings": [],
            "governance_conformance": {"PPS": "100% (4/3 applicable controls satisfied)"},
        }

        with self.assertRaises(ResponseValidationError):
            parse_backend_response(response)

    def test_cli_validate_response_accepts_valid_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            response_file = Path(tmp) / "response.json"
            response_file.write_text(
                json.dumps(
                    {
                        "assessment": {
                            "functional_completeness": 80,
                            "implementation_quality": 75,
                            "intent_fidelity": "Strong",
                            "verification_confidence": "Partial",
                            "posture_fitness": "Shared - Adequate",
                            "lifecycle_fitness": "Appropriate",
                            "release_eligibility": "NOT APPLICABLE",
                            "blockers": 0,
                        },
                        "findings": [],
                        "governance_conformance": {"PPS": "N/A (0/0 applicable controls satisfied)"},
                        "uncertainties": [],
                    }
                ),
                encoding="utf-8",
            )
            stdout = StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["validate-response", "--response-file", str(response_file)])

            self.assertEqual(exit_code, 0)
            self.assertIn("Valid response:", stdout.getvalue())
            self.assertIn("Findings: 0", stdout.getvalue())

    def test_cli_validate_response_can_print_json_success_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            response_file = Path(tmp) / "response.json"
            response_file.write_text(
                json.dumps(
                    {
                        "assessment": {
                            "functional_completeness": 80,
                            "implementation_quality": 75,
                            "intent_fidelity": "Strong",
                            "verification_confidence": "Partial",
                            "posture_fitness": "Shared - Adequate",
                            "lifecycle_fitness": "Appropriate",
                            "release_eligibility": "NOT APPLICABLE",
                            "blockers": 0,
                        },
                        "findings": [],
                        "governance_conformance": {"PPS": "N/A (0/0 applicable controls satisfied)"},
                        "uncertainties": [],
                    }
                ),
                encoding="utf-8",
            )
            stdout = StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["validate-response", "--response-file", str(response_file), "--json"])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(Path(payload["response_file"]), response_file)
            self.assertEqual(payload["findings"], 0)
            self.assertEqual(payload["release_eligibility"], "NOT APPLICABLE")
            self.assertFalse(payload["has_narrative"])

    def test_cli_validate_response_can_require_declared_posture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            response_file = Path(tmp) / "response.json"
            response_file.write_text(json.dumps(build_response_template("adoptable")), encoding="utf-8")
            stdout = StringIO()

            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "validate-response",
                        "--response-file",
                        str(response_file),
                        "--posture",
                        AdoptionPosture.ADOPTABLE.value,
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "ok")

    def test_cli_validate_response_rejects_mismatched_declared_posture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            response_file = Path(tmp) / "response.json"
            response_file.write_text(json.dumps(build_response_template("shared")), encoding="utf-8")
            stderr = StringIO()

            with redirect_stderr(stderr), redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "validate-response",
                        "--response-file",
                        str(response_file),
                        "--posture",
                        AdoptionPosture.PERSONAL.value,
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("posture_fitness", stderr.getvalue())
            self.assertIn("personal", stderr.getvalue())

    def test_cli_validate_response_rejects_invalid_file_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            response_file = Path(tmp) / "response.json"
            response_file.write_text(
                json.dumps(
                    {
                        "assessment": {
                            "functional_completeness": 80,
                            "implementation_quality": 75,
                            "intent_fidelity": "Pretty Good",
                            "verification_confidence": "Partial",
                            "posture_fitness": "Shared - Adequate",
                            "lifecycle_fitness": "Appropriate",
                            "release_eligibility": "NOT APPLICABLE",
                            "blockers": 0,
                        },
                        "findings": [],
                    }
                ),
                encoding="utf-8",
            )
            stderr = StringIO()

            with redirect_stderr(stderr), redirect_stdout(StringIO()):
                exit_code = main(["validate-response", "--response-file", str(response_file)])

            self.assertEqual(exit_code, 1)
            self.assertIn("error:", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_cli_validate_response_rejects_invalid_file_with_json_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            response_file = Path(tmp) / "response.json"
            response_file.write_text(
                json.dumps(
                    {
                        "assessment": {
                            "functional_completeness": 80,
                            "implementation_quality": 75,
                            "intent_fidelity": "Pretty Good",
                            "verification_confidence": "Partial",
                            "posture_fitness": "Shared - Adequate",
                            "lifecycle_fitness": "Appropriate",
                            "release_eligibility": "NOT APPLICABLE",
                            "blockers": 0,
                        },
                        "findings": [],
                    }
                ),
                encoding="utf-8",
            )
            stderr = StringIO()
            stdout = StringIO()

            with redirect_stderr(stderr), redirect_stdout(stdout):
                exit_code = main(["validate-response", "--response-file", str(response_file), "--json"])

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error_type"], "ResponseValidationError")
            self.assertIn("intent_fidelity", payload["error"])
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_cli_validate_response_rejects_finding_without_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            response_file = Path(tmp) / "response.json"
            response = _response(
                posture_fitness="Shared - Adequate",
                findings=[
                    {
                        "title": "Unsupported finding",
                        "finding_class": "required",
                        "area": "Evidence",
                        "authority": "engineering_recommendation",
                        "applicability": None,
                        "evidence": [" "],
                        "impact": "This would be unsupported.",
                        "consequence": "The response should be rejected.",
                        "recommendation": None,
                    }
                ],
            )
            response_file.write_text(json.dumps(response), encoding="utf-8")
            stdout = StringIO()
            stderr = StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["validate-response", "--response-file", str(response_file), "--json"])

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error_type"], "ResponseValidationError")
            self.assertIn("evidence", payload["error"])

    def test_cli_validate_response_rejects_unstructured_governance_conformance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            response_file = Path(tmp) / "response.json"
            response = _response(
                posture_fitness="Shared - Adequate",
                governance_conformance={"PPS": "not evaluated"},
            )
            response_file.write_text(json.dumps(response), encoding="utf-8")
            stdout = StringIO()
            stderr = StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["validate-response", "--response-file", str(response_file), "--json"])

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error_type"], "ResponseValidationError")
            self.assertIn("governance_conformance", payload["error"])

    def test_cli_writes_phase_1_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue((output / "evaluation.json").exists())
            self.assertTrue((output / "report.md").exists())
            self.assertTrue((output / "run-record.json").exists())
            self.assertTrue((output / "context-bundle.json").exists())
            self.assertTrue((output / "reasoning-request.json").exists())
            self.assertTrue((output / "reasoning-request.md").exists())
            self.assertTrue((output / "response-template.json").exists())
            self.assertTrue((output / "artifact-manifest.json").exists())
            run_dirs = list((output / "runs").iterdir())
            materialized_run_dirs = [path for path in run_dirs if path.is_dir()]
            self.assertEqual(len(materialized_run_dirs), 1)
            self.assertTrue((materialized_run_dirs[0] / "evaluation.json").exists())
            self.assertTrue((materialized_run_dirs[0] / "report.md").exists())
            self.assertTrue((materialized_run_dirs[0] / "response-template.json").exists())
            self.assertTrue((materialized_run_dirs[0] / "artifact-manifest.json").exists())
            self.assertTrue((output / "runs" / "index.json").exists())
            self.assertTrue((output / "runs" / "index.md").exists())

            data = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
            run_data = json.loads((materialized_run_dirs[0] / "evaluation.json").read_text(encoding="utf-8"))
            run_index = json.loads((output / "runs" / "index.json").read_text(encoding="utf-8"))
            bundle = json.loads((output / "context-bundle.json").read_text(encoding="utf-8"))
            reasoning_request = json.loads((output / "reasoning-request.json").read_text(encoding="utf-8"))
            response_template = json.loads((output / "response-template.json").read_text(encoding="utf-8"))
            artifact_manifest = json.loads((output / "artifact-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(data, run_data)
            self.assertEqual(len(run_index["runs"]), 1)
            self.assertEqual(run_index["runs"][0]["report_id"], data["run"]["report_id"])
            self.assertEqual(artifact_manifest["report_id"], data["run"]["report_id"])
            self.assertIn("evaluation.json", artifact_manifest["artifacts"])
            self.assertIn("sha256", artifact_manifest["artifacts"]["evaluation.json"])
            self.assertEqual(data["run"]["declared_posture"], "shared")
            self.assertEqual(data["run"]["reasoning_provider"], "none")
            self.assertEqual(data["run"]["configuration"]["backend"], "none")
            self.assertEqual(data["context"]["project_name"]["value"], project.name)
            self.assertIn("prepared_context", data)
            self.assertNotIn("assessment", bundle)
            self.assertIn("prepared_context", bundle)
            self.assertIn("text_snippets", bundle["prepared_context"])
            self.assertEqual(reasoning_request["context_bundle"], bundle)
            self.assertIn("response_contract", reasoning_request)
            self.assertEqual(response_template, build_response_template("shared"))
            parse_backend_response(response_template, expected_posture="shared")

    def test_cli_report_orders_priority_findings(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp) / "out"
            response_file = Path(out_tmp) / "response.json"
            (project / "README.md").write_text("# Example\n", encoding="utf-8")
            response_file.write_text(
                json.dumps(
                    _response(
                        posture_fitness="Shared - Marginal",
                        release_eligibility="BLOCKED",
                        blockers=1,
                        findings=[
                            _finding(title="Optional polish", finding_class="could"),
                            _finding(title="Release checklist missing", finding_class="required", applicability="unsatisfied"),
                            _finding(title="Useful implementation context", finding_class="observation"),
                            _finding(title="Setup documentation is thin", finding_class="should"),
                        ],
                    )
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "response-file",
                        "--response-file",
                        str(response_file),
                    ]
                )

            self.assertEqual(exit_code, 0)
            report = (output / "report.md").read_text(encoding="utf-8")
            priority_index = report.index("## Priority Findings")
            required_index = report.index("- Required: Release checklist missing", priority_index)
            should_index = report.index("- Should: Setup documentation is thin", priority_index)
            could_index = report.index("- Could: Optional polish", priority_index)
            observation_index = report.index("- Observation: Useful implementation context", priority_index)
            self.assertLess(required_index, should_index)
            self.assertLess(should_index, could_index)
            self.assertLess(could_index, observation_index)

    def test_evaluation_from_dict_roundtrips_preserved_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            self.assertEqual(exit_code, 0)
            data = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
            evaluation = evaluation_from_dict(data)
            self.assertEqual(evaluation.run.report_id, data["run"]["report_id"])
            self.assertEqual(evaluation.run.declared_posture, AdoptionPosture.SHARED)
            self.assertEqual(evaluation.evidence.project_name, project.name)
            self.assertEqual(evaluation.context.project_name.value, project.name)
            self.assertEqual(evaluation.to_dict(), data)

    def test_cli_evaluate_can_print_json_success_output(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")
            stdout = StringIO()

            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "ok")
            self.assertTrue(Path(payload["run_dir"]).exists())
            self.assertEqual(Path(payload["artifacts"]["latest_evaluation"]), output / "evaluation.json")
            self.assertEqual(Path(payload["artifacts"]["latest_response_template"]), output / "response-template.json")
            self.assertNotIn("Wrote run directory", stdout.getvalue())

    def test_cli_writes_response_template_for_declared_posture(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.PERSONAL.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            self.assertEqual(exit_code, 0)
            response_template = json.loads((output / "response-template.json").read_text(encoding="utf-8"))
            self.assertEqual(response_template["assessment"]["posture_fitness"], "Personal - Adequate")
            parse_backend_response(response_template, expected_posture="personal")

    def test_cli_lists_preserved_runs(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            stdout = StringIO()
            with redirect_stdout(stdout):
                list_exit = main(["list-runs", "--out", str(output)])

            self.assertEqual(evaluate_exit, 0)
            self.assertEqual(list_exit, 0)
            output_text = stdout.getvalue()
            run_index = json.loads((output / "runs" / "index.json").read_text(encoding="utf-8"))
            self.assertIn("Timestamp | Project | Posture | Backend | Release | Blockers | Findings | Run", output_text)
            self.assertIn(project.name, output_text)
            self.assertIn("shared", output_text)
            self.assertIn("none", output_text)
            self.assertIn(run_index["runs"][0]["run_dir"], output_text)

    def test_cli_list_runs_can_print_json_success_output(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            stdout = StringIO()
            with redirect_stdout(stdout):
                list_exit = main(["list-runs", "--out", str(output), "--json"])

            self.assertEqual(evaluate_exit, 0)
            self.assertEqual(list_exit, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(Path(payload["index_path"]), output / "runs" / "index.json")
            self.assertEqual(len(payload["runs"]), 1)
            self.assertEqual(payload["runs"][0]["project_root"], str(project.resolve()))

    def test_cli_show_run_displays_latest_run(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            stdout = StringIO()
            with redirect_stdout(stdout):
                show_exit = main(["show-run", "--out", str(output)])

            self.assertEqual(evaluate_exit, 0)
            self.assertEqual(show_exit, 0)
            output_text = stdout.getvalue()
            run_index = json.loads((output / "runs" / "index.json").read_text(encoding="utf-8"))
            self.assertIn(f"Run: {run_index['runs'][0]['run_dir']}", output_text)
            self.assertIn("Release eligibility: NOT APPLICABLE", output_text)
            self.assertIn("response_template:", output_text)

    def test_cli_show_run_can_select_run_and_print_json(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                first_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )
                second_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.PERSONAL.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            run_index = json.loads((output / "runs" / "index.json").read_text(encoding="utf-8"))
            selected = run_index["runs"][1]
            stdout = StringIO()
            with redirect_stdout(stdout):
                show_exit = main(["show-run", "--out", str(output), "--run", selected["report_id"][:8], "--json"])

            self.assertEqual(first_exit, 0)
            self.assertEqual(second_exit, 0)
            self.assertEqual(show_exit, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["run"]["report_id"], selected["report_id"])
            self.assertEqual(payload["run"]["declared_posture"], selected["declared_posture"])
            self.assertTrue(Path(payload["artifacts"]["evaluation"]).exists())
            self.assertTrue(Path(payload["artifacts"]["response_template"]).exists())

    def test_cli_show_run_reports_missing_selector_with_json_error(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                show_exit = main(["show-run", "--out", str(output), "--run", "missing-run", "--json"])

            self.assertEqual(evaluate_exit, 0)
            self.assertEqual(show_exit, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error_type"], "ValueError")
            self.assertIn("run not found", payload["error"])

    def test_cli_validate_run_checks_latest_run(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            stdout = StringIO()
            with redirect_stdout(stdout):
                validate_exit = main(["validate-run", "--out", str(output)])

            self.assertEqual(evaluate_exit, 0)
            self.assertEqual(validate_exit, 0)
            output_text = stdout.getvalue()
            self.assertIn("Valid run:", output_text)
            self.assertIn("required_artifacts_exist: ok", output_text)
            self.assertIn("response_template_contract: ok", output_text)

    def test_cli_validate_run_can_print_json_success_output(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            stdout = StringIO()
            with redirect_stdout(stdout):
                validate_exit = main(["validate-run", "--out", str(output), "--json"])

            self.assertEqual(evaluate_exit, 0)
            self.assertEqual(validate_exit, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "ok")
            check_names = {check["name"] for check in payload["checks"]}
            self.assertIn("required_artifacts_exist", check_names)
            self.assertIn("report_id_consistency", check_names)
            self.assertIn("run_index_entry_consistency", check_names)
            self.assertIn("run_record_consistency", check_names)
            self.assertIn("response_template_contract", check_names)
            self.assertIn("backend_response_metadata_hygiene", check_names)
            self.assertIn("artifact_manifest_integrity", check_names)
            self.assertIn("latest_alias_consistency", check_names)

    def test_cli_validate_run_rejects_run_index_summary_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            index_path = output / "runs" / "index.json"
            run_index = json.loads(index_path.read_text(encoding="utf-8"))
            run_index["runs"][0]["finding_count"] = 999
            index_path.write_text(json.dumps(run_index, indent=2), encoding="utf-8")

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                validate_exit = main(["validate-run", "--out", str(output), "--json"])

            self.assertEqual(evaluate_exit, 0)
            self.assertEqual(validate_exit, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertIn("run index entry field `finding_count`", payload["error"])

    def test_cli_validate_run_rejects_stale_latest_alias(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            (output / "report.md").write_text("# Stale latest alias\n", encoding="utf-8")

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                validate_exit = main(["validate-run", "--out", str(output), "--json"])

            self.assertEqual(evaluate_exit, 0)
            self.assertEqual(validate_exit, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertIn("latest alias does not match", payload["error"])
            self.assertIn("report.md", payload["error"])

    def test_cli_validate_run_reports_missing_artifact_with_json_error(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            run_index = json.loads((output / "runs" / "index.json").read_text(encoding="utf-8"))
            missing_template = output / "runs" / run_index["runs"][0]["run_dir"] / "response-template.json"
            missing_template.unlink()
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                validate_exit = main(["validate-run", "--out", str(output), "--json"])

            self.assertEqual(evaluate_exit, 0)
            self.assertEqual(validate_exit, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error_type"], "ValueError")
            self.assertIn("missing required artifacts", payload["error"])
            self.assertIn("response_template", payload["error"])

    def test_cli_validate_run_rejects_artifact_manifest_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            run_index = json.loads((output / "runs" / "index.json").read_text(encoding="utf-8"))
            run_dir = output / "runs" / run_index["runs"][0]["run_dir"]
            (run_dir / "report.md").write_text("# Tampered report\n", encoding="utf-8")

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                validate_exit = main(["validate-run", "--out", str(output), "--json"])

            self.assertEqual(evaluate_exit, 0)
            self.assertEqual(validate_exit, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertIn("mismatch", payload["error"])
            self.assertIn("report.md", payload["error"])

    def test_cli_validate_run_rejects_artifact_manifest_missing_required_record(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            run_index = json.loads((output / "runs" / "index.json").read_text(encoding="utf-8"))
            run_dir = output / "runs" / run_index["runs"][0]["run_dir"]
            manifest_path = run_dir / "artifact-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            del manifest["artifacts"]["report.md"]
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                validate_exit = main(["validate-run", "--out", str(output), "--json"])

            self.assertEqual(evaluate_exit, 0)
            self.assertEqual(validate_exit, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertIn("missing artifact records", payload["error"])
            self.assertIn("report.md", payload["error"])

    def test_cli_validate_run_requires_response_template_posture_to_match_run(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.PERSONAL.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            run_index = json.loads((output / "runs" / "index.json").read_text(encoding="utf-8"))
            template = output / "runs" / run_index["runs"][0]["run_dir"] / "response-template.json"
            template.write_text(json.dumps(build_response_template("shared")), encoding="utf-8")
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                validate_exit = main(["validate-run", "--out", str(output), "--json"])

            self.assertEqual(evaluate_exit, 0)
            self.assertEqual(validate_exit, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error_type"], "ResponseValidationError")
            self.assertIn("posture_fitness", payload["error"])
            self.assertIn("personal", payload["error"])

    def test_cli_validate_run_rejects_raw_backend_response_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            run_index = json.loads((output / "runs" / "index.json").read_text(encoding="utf-8"))
            run_dir = output / "runs" / run_index["runs"][0]["run_dir"]
            evaluation_path = run_dir / "evaluation.json"
            run_record_path = run_dir / "run-record.json"
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
            evaluation["run"]["configuration"]["backend_response"] = {
                "id": "resp_example",
                "output_text": json.dumps(build_response_template("shared")),
            }
            evaluation_path.write_text(json.dumps(evaluation, indent=2), encoding="utf-8")
            run_record_path.write_text(json.dumps(evaluation["run"], indent=2), encoding="utf-8")

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                validate_exit = main(["validate-run", "--out", str(output), "--json"])

            self.assertEqual(evaluate_exit, 0)
            self.assertEqual(validate_exit, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error_type"], "ValueError")
            self.assertIn("forbidden metadata key", payload["error"])
            self.assertIn("output_text", payload["error"])

    def test_cli_validate_run_rejects_sensitive_backend_response_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            run_index = json.loads((output / "runs" / "index.json").read_text(encoding="utf-8"))
            run_dir = output / "runs" / run_index["runs"][0]["run_dir"]
            evaluation_path = run_dir / "evaluation.json"
            run_record_path = run_dir / "run-record.json"
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
            evaluation["run"]["configuration"]["backend_response"] = {
                "id": "resp_example",
                "status": "completed",
                "diagnostic": "Authorization: Bearer " + ("a" * 24),
            }
            evaluation_path.write_text(json.dumps(evaluation, indent=2), encoding="utf-8")
            run_record_path.write_text(json.dumps(evaluation["run"], indent=2), encoding="utf-8")

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                validate_exit = main(["validate-run", "--out", str(output), "--json"])

            self.assertEqual(evaluate_exit, 0)
            self.assertEqual(validate_exit, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error_type"], "ValueError")
            self.assertIn("likely sensitive metadata", payload["error"])
            self.assertIn("bearer_token", payload["error"])

    def test_cli_validate_run_rejects_invalid_response_file_metadata_hash(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp)
            response_file = Path(out_tmp) / "response.json"
            (project / "README.md").write_text("# Example\n", encoding="utf-8")
            response_file.write_text(json.dumps(build_response_template("shared")), encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "response-file",
                        "--response-file",
                        str(response_file),
                    ]
                )

            run_index = json.loads((output / "runs" / "index.json").read_text(encoding="utf-8"))
            run_dir = output / "runs" / run_index["runs"][0]["run_dir"]
            evaluation_path = run_dir / "evaluation.json"
            run_record_path = run_dir / "run-record.json"
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
            evaluation["run"]["configuration"]["backend_response"]["response_file_sha256"] = "not-a-hash"
            evaluation_path.write_text(json.dumps(evaluation, indent=2), encoding="utf-8")
            run_record_path.write_text(json.dumps(evaluation["run"], indent=2), encoding="utf-8")

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                validate_exit = main(["validate-run", "--out", str(output), "--json"])

            self.assertEqual(evaluate_exit, 0)
            self.assertEqual(validate_exit, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error_type"], "ValueError")
            self.assertIn("response_file_sha256", payload["error"])

    def test_cli_complete_run_reuses_preserved_context_without_recollecting_project(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp) / "out"
            response_file = Path(out_tmp) / "response.json"
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            source_index = json.loads((output / "runs" / "index.json").read_text(encoding="utf-8"))
            source_entry = source_index["runs"][0]
            source_evaluation = json.loads(
                (output / "runs" / source_entry["run_dir"] / "evaluation.json").read_text(encoding="utf-8")
            )
            (project / "README.md").write_text("# Changed after preserved run\n", encoding="utf-8")
            response_file.write_text(
                json.dumps(
                    {
                        "assessment": {
                            "functional_completeness": 91,
                            "implementation_quality": 86,
                            "intent_fidelity": "Strong",
                            "verification_confidence": "Partial",
                            "posture_fitness": "Shared - Adequate",
                            "lifecycle_fitness": "Appropriate",
                            "release_eligibility": "NOT APPLICABLE",
                            "blockers": 0,
                        },
                        "findings": [
                            {
                                "title": "Preserved context was reusable",
                                "finding_class": "observation",
                                "area": "Evaluation Workflow",
                                "authority": "engineering_recommendation",
                                "applicability": None,
                                "evidence": ["reasoning-request.json"],
                                "impact": "The completed report can be produced from a saved evidence package.",
                                "consequence": "Manual reasoning can be attached without changing the evidence snapshot.",
                                "recommendation": None,
                            }
                        ],
                        "governance_conformance": {"PPS": "N/A (0/0 applicable controls satisfied)"},
                        "uncertainties": ["The response was supplied from a test fixture."],
                        "narrative": "## Evaluation Narrative\n\nThe saved bundle was completed without recollecting.",
                    }
                ),
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                complete_exit = main(
                    [
                        "complete-run",
                        "--out",
                        str(output),
                        "--run",
                        source_entry["report_id"][:8],
                        "--response-file",
                        str(response_file),
                        "--json",
                    ]
                )

            self.assertEqual(evaluate_exit, 0)
            self.assertEqual(complete_exit, 0)
            payload = json.loads(stdout.getvalue())
            completed_path = Path(payload["artifacts"]["evaluation"])
            completed = json.loads(completed_path.read_text(encoding="utf-8"))
            self.assertNotEqual(completed["run"]["report_id"], source_entry["report_id"])
            self.assertEqual(completed["run"]["reasoning_provider"], "response-file")
            self.assertEqual(completed["run"]["configuration"]["completed_from_report_id"], source_entry["report_id"])
            self.assertTrue(completed["run"]["configuration"]["reused_preserved_context"])
            response_bytes = response_file.read_bytes()
            self.assertEqual(completed["run"]["configuration"]["response_file_size_bytes"], len(response_bytes))
            self.assertEqual(
                completed["run"]["configuration"]["response_file_sha256"],
                hashlib.sha256(response_bytes).hexdigest(),
            )
            self.assertEqual(completed["run"]["project_root"], source_evaluation["run"]["project_root"])
            self.assertEqual(completed["evidence"], source_evaluation["evidence"])
            self.assertEqual(completed["context"], source_evaluation["context"])
            self.assertEqual(completed["prepared_context"], source_evaluation["prepared_context"])
            self.assertEqual(completed["assessment"]["functional_completeness"], 91)
            report = Path(payload["artifacts"]["report"]).read_text(encoding="utf-8")
            self.assertIn("The saved bundle was completed without recollecting.", report)
            refreshed_index = json.loads((output / "runs" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(refreshed_index["runs"]), 2)
            self.assertTrue((output / "runs" / source_entry["run_dir"] / "evaluation.json").exists())

    def test_cli_complete_run_rejects_mismatched_response_posture(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp) / "out"
            response_file = Path(out_tmp) / "response.json"
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.PERSONAL.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            response_file.write_text(json.dumps(build_response_template("shared")), encoding="utf-8")
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                complete_exit = main(
                    [
                        "complete-run",
                        "--out",
                        str(output),
                        "--response-file",
                        str(response_file),
                        "--json",
                    ]
                )

            self.assertEqual(evaluate_exit, 0)
            self.assertEqual(complete_exit, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error_type"], "ResponseValidationError")
            self.assertIn("posture_fitness", payload["error"])
            refreshed_index = json.loads((output / "runs" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(refreshed_index["runs"]), 1)

    def test_cli_complete_run_rejects_corrupt_preserved_source_run(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp) / "out"
            response_file = Path(out_tmp) / "response.json"
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_exit = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            run_index = json.loads((output / "runs" / "index.json").read_text(encoding="utf-8"))
            source_run_dir = output / "runs" / run_index["runs"][0]["run_dir"]
            (source_run_dir / "report.md").write_text("# Corrupt source report\n", encoding="utf-8")
            response_file.write_text(json.dumps(build_response_template("shared")), encoding="utf-8")

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                complete_exit = main(
                    [
                        "complete-run",
                        "--out",
                        str(output),
                        "--response-file",
                        str(response_file),
                        "--json",
                    ]
                )

            self.assertEqual(evaluate_exit, 0)
            self.assertEqual(complete_exit, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertIn("mismatch", payload["error"])
            refreshed_index = json.loads((output / "runs" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(refreshed_index["runs"]), 1)

    def test_cli_can_use_mocked_openai_backend(self) -> None:
        class FakeHTTPResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "id": "resp_mocked_123",
                        "status": "completed",
                        "created_at": 1800000000,
                        "model": "gpt-test",
                        "service_tier": "default",
                        "usage": {
                            "input_tokens": 321,
                            "output_tokens": 123,
                            "total_tokens": 444,
                        },
                        "output_text": json.dumps(
                            {
                                "assessment": {
                                    "functional_completeness": 88,
                                    "implementation_quality": 84,
                                    "intent_fidelity": "Strong",
                                    "verification_confidence": "Partial",
                                    "posture_fitness": "Shared - Adequate",
                                    "lifecycle_fitness": "Appropriate",
                                    "release_eligibility": "NOT APPLICABLE",
                                    "blockers": 0,
                                },
                                "findings": [
                                    {
                                        "title": "Mocked OpenAI response parsed",
                                        "finding_class": "observation",
                                        "area": "Reasoning Backend",
                                        "authority": "engineering_recommendation",
                                        "applicability": None,
                                        "evidence": ["reasoning-request.json"],
                                        "impact": "The OpenAI backend can parse a structured model response.",
                                        "consequence": "The live API boundary can share the response-file contract.",
                                        "recommendation": None,
                                    }
                                ],
                                "governance_conformance": {"PPS": "N/A (0/0 applicable controls satisfied)"},
                                "uncertainties": ["The API was mocked in this test."],
                                "narrative": "## Evaluation Narrative\n\nThe mocked API result was parsed.",
                            }
                        )
                    }
                ).encode("utf-8")

        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp) / "out"
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=True):
                with patch("single_project_evaluator.backend.urlopen", return_value=FakeHTTPResponse()) as openai_call:
                    with redirect_stdout(StringIO()):
                        exit_code = main(
                            [
                                "evaluate",
                                "--project",
                                str(project),
                                "--posture",
                                AdoptionPosture.SHARED.value,
                                "--out",
                                str(output),
                                "--backend",
                                "openai",
                                "--model",
                                "gpt-test",
                                "--api-base",
                                "https://api.example.test/v1/responses",
                            ]
                        )

            self.assertEqual(exit_code, 0)
            self.assertEqual(openai_call.call_count, 1)
            request = openai_call.call_args.args[0]
            self.assertEqual(request.full_url, "https://api.example.test/v1/responses")
            body = json.loads(request.data.decode("utf-8"))
            self.assertEqual(body["model"], "gpt-test")
            self.assertIn("input", body)
            self.assertEqual(body["text"]["format"]["type"], "json_schema")
            self.assertEqual(body["text"]["format"]["name"], "single_project_evaluation_response")
            self.assertFalse(body["text"]["format"]["strict"])
            self.assertEqual(
                body["text"]["format"]["schema"]["properties"]["assessment"]["properties"]["release_eligibility"][
                    "enum"
                ],
                ["PASS", "BLOCKED", "NOT APPLICABLE"],
            )
            data = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
            self.assertEqual(data["run"]["reasoning_provider"], "openai")
            self.assertEqual(data["run"]["model_identifier"], "gpt-test")
            self.assertEqual(data["run"]["configuration"]["api_base"], "https://api.example.test/v1/responses")
            self.assertEqual(data["run"]["configuration"]["backend_response"]["id"], "resp_mocked_123")
            self.assertEqual(data["run"]["configuration"]["backend_response"]["status"], "completed")
            self.assertEqual(data["run"]["configuration"]["backend_response"]["usage"]["total_tokens"], 444)
            self.assertNotIn("output_text", data["run"]["configuration"]["backend_response"])
            self.assertEqual(data["assessment"]["functional_completeness"], 88)
            self.assertEqual(data["governance_conformance"]["PPS"], "N/A (0/0 applicable controls satisfied)")
            self.assertIn("The mocked API result was parsed.", (output / "report.md").read_text(encoding="utf-8"))

    def test_cli_retries_transient_openai_transport_error(self) -> None:
        class FakeHTTPResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return json.dumps({"output_text": json.dumps(build_response_template("shared"))}).encode("utf-8")

        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp) / "out"
            (project / "README.md").write_text("# Example\n", encoding="utf-8")

            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=True):
                with patch(
                    "single_project_evaluator.backend.urlopen",
                    side_effect=[URLError("temporary network issue"), FakeHTTPResponse()],
                ) as openai_call:
                    with redirect_stdout(StringIO()):
                        exit_code = main(
                            [
                                "evaluate",
                                "--project",
                                str(project),
                                "--posture",
                                AdoptionPosture.SHARED.value,
                                "--out",
                                str(output),
                                "--backend",
                                "openai",
                                "--model",
                                "gpt-test",
                                "--retries",
                                "1",
                            ]
                        )

            self.assertEqual(exit_code, 0)
            self.assertEqual(openai_call.call_count, 2)
            data = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
            self.assertEqual(data["run"]["configuration"]["retries"], 1)

    def test_cli_can_explicitly_allow_sensitive_hosted_context(self) -> None:
        class FakeHTTPResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return json.dumps({"output_text": json.dumps(build_response_template("shared"))}).encode("utf-8")

        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp) / "out"
            (project / "README.md").write_text(
                "# Example\n\nOPENAI_API_KEY = \"sk-" + ("b" * 32) + "\"\n",
                encoding="utf-8",
            )

            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=True):
                with patch("single_project_evaluator.backend.urlopen", return_value=FakeHTTPResponse()) as openai_call:
                    with redirect_stdout(StringIO()):
                        exit_code = main(
                            [
                                "evaluate",
                                "--project",
                                str(project),
                                "--posture",
                                AdoptionPosture.SHARED.value,
                                "--out",
                                str(output),
                                "--backend",
                                "openai",
                                "--model",
                                "gpt-test",
                                "--allow-sensitive-hosted",
                            ]
                        )

            self.assertEqual(exit_code, 0)
            self.assertEqual(openai_call.call_count, 1)
            data = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
            self.assertTrue(data["run"]["configuration"]["allow_sensitive_hosted"])

    def test_cli_reports_missing_run_index_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as out_tmp:
            stderr = StringIO()

            with redirect_stderr(stderr), redirect_stdout(StringIO()):
                exit_code = main(["list-runs", "--out", str(Path(out_tmp) / "reports")])

            self.assertEqual(exit_code, 1)
            self.assertIn("error:", stderr.getvalue())
            self.assertIn("run index not found", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_cli_reports_missing_run_index_with_json_error(self) -> None:
        with tempfile.TemporaryDirectory() as out_tmp:
            stderr = StringIO()
            stdout = StringIO()

            with redirect_stderr(stderr), redirect_stdout(stdout):
                exit_code = main(["list-runs", "--out", str(Path(out_tmp) / "reports"), "--json"])

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error_type"], "FileNotFoundError")
            self.assertIn("run index not found", payload["error"])
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_cli_can_use_structured_response_file_backend(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp) / "out"
            response_file = Path(out_tmp) / "response.json"
            (project / "README.md").write_text("# Example\n", encoding="utf-8")
            response_file.write_text(
                json.dumps(
                    {
                        "assessment": {
                            "functional_completeness": 90,
                            "implementation_quality": 85,
                            "intent_fidelity": "Strong",
                            "verification_confidence": "Partial",
                            "posture_fitness": "Shared - Adequate",
                            "lifecycle_fitness": "Appropriate",
                            "release_eligibility": "NOT APPLICABLE",
                            "blockers": 0,
                        },
                        "findings": [
                            {
                                "title": "Evidence bundle is usable",
                                "finding_class": "observation",
                                "area": "Evaluation Spine",
                                "authority": "engineering_recommendation",
                                "applicability": None,
                                "evidence": ["context-bundle.json"],
                                "impact": "The response-file backend can exercise report generation.",
                                "consequence": "No live model call is required for parser integration tests.",
                                "recommendation": None,
                            }
                        ],
                        "governance_conformance": {"PPS": "N/A (0/0 applicable controls satisfied)"},
                        "uncertainties": ["The response was supplied from a test fixture."],
                        "narrative": "## Evaluation Narrative\n\nThe supplied response describes a usable evidence bundle.",
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "response-file",
                        "--response-file",
                        str(response_file),
                    ]
                )

            self.assertEqual(exit_code, 0)
            data = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
            report = (output / "report.md").read_text(encoding="utf-8")
            self.assertEqual(data["run"]["reasoning_provider"], "response-file")
            response_bytes = response_file.read_bytes()
            self.assertEqual(data["run"]["configuration"]["backend_response"]["response_file_size_bytes"], len(response_bytes))
            self.assertEqual(
                data["run"]["configuration"]["backend_response"]["response_file_sha256"],
                hashlib.sha256(response_bytes).hexdigest(),
            )
            self.assertEqual(data["assessment"]["functional_completeness"], 90)
            self.assertEqual(data["governance_conformance"]["PPS"], "N/A (0/0 applicable controls satisfied)")
            self.assertEqual(data["uncertainties"], ["The response was supplied from a test fixture."])
            self.assertEqual(
                data["narrative"],
                "## Evaluation Narrative\n\nThe supplied response describes a usable evidence bundle.",
            )
            self.assertIn("PPS: N/A (0/0 applicable controls satisfied)", report)
            self.assertIn("The response was supplied from a test fixture.", report)
            self.assertIn("## Backend Narrative", report)
            self.assertIn("The supplied response describes a usable evidence bundle.", report)
            self.assertIn("This report uses a parsed backend response.", report)

    def test_personal_fixture_does_not_treat_non_adoptability_as_defect(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp) / "out"
            response_file = Path(out_tmp) / "personal-response.json"
            (project / "README.md").write_text(
                "# Personal Helper\n\nA one-operator script with local paths documented for its creator.\n",
                encoding="utf-8",
            )
            response_file.write_text(
                json.dumps(
                    _response(
                        posture_fitness="Personal - Strong",
                        findings=[
                            _finding(
                                title="Creator-specific operation is acceptable for personal posture",
                                finding_class="observation",
                                authority="adoption_recommendation",
                                applicability="not_applicable",
                                recommendation="Do not broaden onboarding until the declared posture changes.",
                            )
                        ],
                    )
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.PERSONAL.value,
                        "--out",
                        str(output),
                        "--backend",
                        "response-file",
                        "--response-file",
                        str(response_file),
                    ]
                )

            self.assertEqual(exit_code, 0)
            data = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
            report = (output / "report.md").read_text(encoding="utf-8")
            self.assertEqual(data["assessment"]["posture_fitness"], "Personal - Strong")
            self.assertEqual(data["assessment"]["release_eligibility"], "NOT APPLICABLE")
            self.assertEqual(data["findings"][0]["applicability"], "not_applicable")
            self.assertEqual(data["findings"][0]["authority"], "adoption_recommendation")
            self.assertIn("Do not broaden onboarding until the declared posture changes.", report)

    def test_shared_fixture_preserves_deferred_governance_without_release_block(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp) / "out"
            response_file = Path(out_tmp) / "shared-response.json"
            (project / "README.md").write_text(
                "# Shared Tool\n\nA small tool intended for similar operators, with governance still being mapped.\n",
                encoding="utf-8",
            )
            response_file.write_text(
                json.dumps(
                    _response(
                        posture_fitness="Shared - Adequate",
                        findings=[
                            _finding(
                                title="Governance control mapping remains deferred",
                                finding_class="observation",
                                authority="governance_requirement",
                                applicability="deferred",
                                recommendation="Complete control mapping before treating conformance as measured.",
                            )
                        ],
                        governance_conformance={"CTS": "N/A (0/0 applicable controls satisfied)"},
                    )
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "response-file",
                        "--response-file",
                        str(response_file),
                    ]
                )

            self.assertEqual(exit_code, 0)
            data = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
            report = (output / "report.md").read_text(encoding="utf-8")
            self.assertEqual(data["assessment"]["posture_fitness"], "Shared - Adequate")
            self.assertEqual(data["assessment"]["release_eligibility"], "NOT APPLICABLE")
            self.assertEqual(data["assessment"]["blockers"], 0)
            self.assertEqual(data["findings"][0]["applicability"], "deferred")
            self.assertEqual(data["governance_conformance"]["CTS"], "N/A (0/0 applicable controls satisfied)")
            self.assertIn("Governance control mapping remains deferred", report)

    def test_adoptable_fixture_can_be_high_quality_and_release_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp) / "out"
            response_file = Path(out_tmp) / "adoptable-response.json"
            (project / "README.md").write_text(
                "# Adoptable Tool\n\nA polished package candidate that lacks a required release checklist.\n",
                encoding="utf-8",
            )
            response_file.write_text(
                json.dumps(
                    _response(
                        posture_fitness="Adoptable - Adequate",
                        release_eligibility="BLOCKED",
                        blockers=1,
                        functional_completeness=94,
                        implementation_quality=91,
                        findings=[
                            _finding(
                                title="Release checklist is required before adoptable release",
                                finding_class="required",
                                authority="governance_requirement",
                                applicability="unsatisfied",
                                recommendation="Add release checklist evidence before release.",
                            )
                        ],
                        governance_conformance={"DRS": "75% (3/4 applicable controls satisfied)"},
                    )
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.ADOPTABLE.value,
                        "--out",
                        str(output),
                        "--backend",
                        "response-file",
                        "--response-file",
                        str(response_file),
                    ]
                )

            self.assertEqual(exit_code, 0)
            data = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
            report = (output / "report.md").read_text(encoding="utf-8")
            self.assertEqual(data["assessment"]["functional_completeness"], 94)
            self.assertEqual(data["assessment"]["implementation_quality"], 91)
            self.assertEqual(data["assessment"]["posture_fitness"], "Adoptable - Adequate")
            self.assertEqual(data["assessment"]["release_eligibility"], "BLOCKED")
            self.assertEqual(data["assessment"]["blockers"], 1)
            self.assertEqual(data["findings"][0]["finding_class"], "required")
            self.assertEqual(data["findings"][0]["applicability"], "unsatisfied")
            self.assertIn("Functional Completeness: 94%", report)
            self.assertIn("Release Eligibility: BLOCKED", report)

    def test_fixture_can_be_low_completeness_but_high_quality(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp) / "out"
            response_file = Path(out_tmp) / "low-completeness-response.json"
            (project / "README.md").write_text(
                "# Small Core\n\nA carefully built project with only one planned workflow implemented so far.\n",
                encoding="utf-8",
            )
            response_file.write_text(
                json.dumps(
                    _response(
                        posture_fitness="Shared - Marginal",
                        functional_completeness=35,
                        implementation_quality=88,
                        findings=[
                            _finding(
                                title="Implemented slice is narrow but coherent",
                                finding_class="observation",
                                authority="engineering_recommendation",
                                applicability="satisfied",
                                recommendation="Keep implementation quality separate from remaining scope.",
                            ),
                            _finding(
                                title="Additional declared workflows remain unimplemented",
                                finding_class="should",
                                authority="project_requirement",
                                applicability="unsatisfied",
                                recommendation="Complete the remaining declared workflows before broadening use.",
                            ),
                        ],
                    )
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "response-file",
                        "--response-file",
                        str(response_file),
                    ]
                )

            self.assertEqual(exit_code, 0)
            data = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
            report = (output / "report.md").read_text(encoding="utf-8")
            self.assertEqual(data["assessment"]["functional_completeness"], 35)
            self.assertEqual(data["assessment"]["implementation_quality"], 88)
            self.assertEqual(data["assessment"]["release_eligibility"], "NOT APPLICABLE")
            self.assertIn("Functional Completeness: 35%", report)
            self.assertIn("Implementation Quality: 88%", report)
            self.assertLess(
                report.index("- Should: Additional declared workflows remain unimplemented"),
                report.index("- Observation: Implemented slice is narrow but coherent"),
            )

    def test_fixture_distinguishes_insufficient_verification_from_failure(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp) / "out"
            response_file = Path(out_tmp) / "verification-limits-response.json"
            (project / "README.md").write_text(
                "# Verification Limited Tool\n\nThe project has source evidence but no preserved test execution log.\n",
                encoding="utf-8",
            )
            response_file.write_text(
                json.dumps(
                    _response(
                        posture_fitness="Shared - Adequate",
                        findings=[
                            _finding(
                                title="Runtime behavior is not verified by supplied evidence",
                                finding_class="observation",
                                authority="engineering_recommendation",
                                applicability=None,
                                evidence=[
                                    "uncertainty: no test execution log or runtime verification record was supplied"
                                ],
                                recommendation="Preserve a verification record before relying on runtime behavior claims.",
                            )
                        ],
                    )
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "response-file",
                        "--response-file",
                        str(response_file),
                    ]
                )

            self.assertEqual(exit_code, 0)
            data = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
            report = (output / "report.md").read_text(encoding="utf-8")
            self.assertEqual(data["assessment"]["release_eligibility"], "NOT APPLICABLE")
            self.assertEqual(data["assessment"]["blockers"], 0)
            self.assertEqual(data["findings"][0]["finding_class"], "observation")
            self.assertEqual(
                data["findings"][0]["evidence"],
                ["uncertainty: no test execution log or runtime verification record was supplied"],
            )
            self.assertIn("Runtime behavior is not verified by supplied evidence", report)
            self.assertNotIn("Required: Runtime behavior is not verified by supplied evidence", report)

    def test_fixture_can_be_governance_compliant_with_implementation_quality_problem(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp) / "out"
            response_file = Path(out_tmp) / "governance-compliant-quality-response.json"
            (project / "README.md").write_text(
                "# Compliant Tool\n\nGovernance records are complete, but the implementation is hard to maintain.\n",
                encoding="utf-8",
            )
            response_file.write_text(
                json.dumps(
                    _response(
                        posture_fitness="Shared - Adequate",
                        functional_completeness=82,
                        implementation_quality=42,
                        findings=[
                            _finding(
                                title="Central workflow mixes parsing, state mutation, and reporting",
                                finding_class="should",
                                authority="engineering_recommendation",
                                applicability="unsatisfied",
                                recommendation="Separate parsing, state mutation, and report rendering responsibilities.",
                            )
                        ],
                        governance_conformance={"CTS": "100% (5/5 applicable controls satisfied)"},
                    )
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "response-file",
                        "--response-file",
                        str(response_file),
                    ]
                )

            self.assertEqual(exit_code, 0)
            data = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
            report = (output / "report.md").read_text(encoding="utf-8")
            self.assertEqual(data["governance_conformance"]["CTS"], "100% (5/5 applicable controls satisfied)")
            self.assertEqual(data["assessment"]["implementation_quality"], 42)
            self.assertEqual(data["assessment"]["release_eligibility"], "NOT APPLICABLE")
            self.assertEqual(data["findings"][0]["authority"], "engineering_recommendation")
            self.assertIn("CTS: 100% (5/5 applicable controls satisfied)", report)
            self.assertIn("Implementation Quality: 42%", report)
            self.assertIn("Should: Central workflow mixes parsing, state mutation, and reporting", report)

    def test_cli_rejects_response_file_with_mismatched_declared_posture(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            output = Path(out_tmp) / "out"
            response_file = Path(out_tmp) / "response.json"
            (project / "README.md").write_text("# Example\n", encoding="utf-8")
            response_file.write_text(
                json.dumps(
                    {
                        "assessment": {
                            "functional_completeness": 90,
                            "implementation_quality": 85,
                            "intent_fidelity": "Strong",
                            "verification_confidence": "Partial",
                            "posture_fitness": "Shared - Adequate",
                            "lifecycle_fitness": "Appropriate",
                            "release_eligibility": "NOT APPLICABLE",
                            "blockers": 0,
                        },
                        "findings": [],
                    }
                ),
                encoding="utf-8",
            )
            stderr = StringIO()

            with redirect_stderr(stderr), redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.PERSONAL.value,
                        "--out",
                        str(output),
                        "--backend",
                        "response-file",
                        "--response-file",
                        str(response_file),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("posture_fitness", stderr.getvalue())
            self.assertIn("personal", stderr.getvalue())
            self.assertFalse(output.exists())

    def test_cli_reports_missing_project_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as out_tmp:
            missing = Path(out_tmp) / "missing"
            stderr = StringIO()

            with redirect_stderr(stderr), redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "evaluate",
                        "--project",
                        str(missing),
                        "--posture",
                        AdoptionPosture.PERSONAL.value,
                        "--out",
                        str(Path(out_tmp) / "out"),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("error:", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_cli_refuses_output_inside_evaluated_project(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp:
            project = Path(project_tmp)
            output = project / "reports"
            (project / "README.md").write_text("# Example\n", encoding="utf-8")
            stderr = StringIO()

            with redirect_stderr(stderr), redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("output directory must be outside the evaluated project", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertFalse(output.exists())

    def test_cli_refuses_output_inside_evaluated_project_with_json_error(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp:
            project = Path(project_tmp)
            output = project / "reports"
            (project / "README.md").write_text("# Example\n", encoding="utf-8")
            stderr = StringIO()
            stdout = StringIO()

            with redirect_stderr(stderr), redirect_stdout(stdout):
                exit_code = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(output),
                        "--backend",
                        "none",
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error_type"], "ValueError")
            self.assertIn("output directory must be outside the evaluated project", payload["error"])
            self.assertFalse(output.exists())

    def test_cli_reports_invalid_response_file_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as out_tmp:
            project = Path(project_tmp)
            response = Path(out_tmp) / "bad-response.json"
            (project / "README.md").write_text("# Example\n", encoding="utf-8")
            response.write_text("{not-json", encoding="utf-8")
            stderr = StringIO()

            with redirect_stderr(stderr), redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "evaluate",
                        "--project",
                        str(project),
                        "--posture",
                        AdoptionPosture.SHARED.value,
                        "--out",
                        str(Path(out_tmp) / "out"),
                        "--backend",
                        "response-file",
                        "--response-file",
                        str(response),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("error:", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
