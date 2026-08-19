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
            standard_path.write_text("# Desktop Application Release Standard\n\nRelease rules.\n", encoding="utf-8")
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
            "uncertainties": ["No tests were supplied."],
        }

        assessment, findings, governance, uncertainties = parse_backend_response(response)

        self.assertEqual(assessment.functional_completeness, 80)
        self.assertEqual(findings[0].finding_class.value, "observation")
        self.assertEqual(governance["DRS"], "not evaluated")
        self.assertEqual(uncertainties, ["No tests were supplied."])

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
                        "governance_conformance": {"PPS": "not evaluated"},
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
            run_dirs = list((output / "runs").iterdir())
            materialized_run_dirs = [path for path in run_dirs if path.is_dir()]
            self.assertEqual(len(materialized_run_dirs), 1)
            self.assertTrue((materialized_run_dirs[0] / "evaluation.json").exists())
            self.assertTrue((materialized_run_dirs[0] / "report.md").exists())
            self.assertTrue((output / "runs" / "index.json").exists())
            self.assertTrue((output / "runs" / "index.md").exists())

            data = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
            run_data = json.loads((materialized_run_dirs[0] / "evaluation.json").read_text(encoding="utf-8"))
            run_index = json.loads((output / "runs" / "index.json").read_text(encoding="utf-8"))
            bundle = json.loads((output / "context-bundle.json").read_text(encoding="utf-8"))
            reasoning_request = json.loads((output / "reasoning-request.json").read_text(encoding="utf-8"))
            self.assertEqual(data, run_data)
            self.assertEqual(len(run_index["runs"]), 1)
            self.assertEqual(run_index["runs"][0]["report_id"], data["run"]["report_id"])
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

    def test_cli_reports_missing_run_index_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as out_tmp:
            stderr = StringIO()

            with redirect_stderr(stderr), redirect_stdout(StringIO()):
                exit_code = main(["list-runs", "--out", str(Path(out_tmp) / "reports")])

            self.assertEqual(exit_code, 1)
            self.assertIn("error:", stderr.getvalue())
            self.assertIn("run index not found", stderr.getvalue())
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
                        "governance_conformance": {"PPS": "not evaluated"},
                        "uncertainties": ["The response was supplied from a test fixture."],
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
            self.assertEqual(data["assessment"]["functional_completeness"], 90)
            self.assertEqual(data["governance_conformance"]["PPS"], "not evaluated")
            self.assertEqual(data["uncertainties"], ["The response was supplied from a test fixture."])
            self.assertIn("PPS: not evaluated", report)
            self.assertIn("The response was supplied from a test fixture.", report)
            self.assertIn("This report uses a parsed backend response.", report)

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
