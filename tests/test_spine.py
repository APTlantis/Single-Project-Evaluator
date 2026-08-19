from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from single_project_evaluator.cli import main
from single_project_evaluator.collector import _git_commit, collect_project_evidence
from single_project_evaluator.context import extract_project_context
from single_project_evaluator.models import AdoptionPosture


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
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue((output / "evaluation.json").exists())
            self.assertTrue((output / "report.md").exists())
            self.assertTrue((output / "run-record.json").exists())

            data = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
            self.assertEqual(data["run"]["declared_posture"], "shared")
            self.assertEqual(data["run"]["reasoning_provider"], "none")
            self.assertEqual(data["context"]["project_name"]["value"], project.name)


if __name__ == "__main__":
    unittest.main()
