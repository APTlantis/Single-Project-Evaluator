from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from single_project_evaluator.cli import main
from single_project_evaluator.collector import _git_commit, collect_project_evidence
from single_project_evaluator.context import extract_project_context
from single_project_evaluator.analysis import prepare_evaluation_context
from single_project_evaluator.backend import create_backend
from single_project_evaluator.models import AdoptionPosture, ApplicabilityState, SurfaceKind
from single_project_evaluator.request_package import build_reasoning_request
from single_project_evaluator.response_parser import ResponseValidationError, parse_backend_response


class SpineTests(unittest.TestCase):
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
                        'additional_standards = ["WGS", "PPS", "AAMHS"]',
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

    def test_prepare_evaluation_context_summarizes_surfaces_and_governance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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
            "governance_conformance": {"DRS": "not evaluated"},
        }

        assessment, findings, governance = parse_backend_response(response)

        self.assertEqual(assessment.functional_completeness, 80)
        self.assertEqual(findings[0].finding_class.value, "observation")
        self.assertEqual(governance["DRS"], "not evaluated")

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

            data = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
            bundle = json.loads((output / "context-bundle.json").read_text(encoding="utf-8"))
            reasoning_request = json.loads((output / "reasoning-request.json").read_text(encoding="utf-8"))
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
                        "governance_conformance": {"PPS": "not evaluated"},
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
            self.assertEqual(data["run"]["reasoning_provider"], "response-file")
            self.assertEqual(data["assessment"]["functional_completeness"], 90)
            self.assertEqual(data["governance_conformance"]["PPS"], "not evaluated")

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


if __name__ == "__main__":
    unittest.main()
