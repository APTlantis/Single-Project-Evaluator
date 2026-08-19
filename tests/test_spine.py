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
            self.assertIn("docs/Project Proposal - Example.md", all_paths)
            self.assertIn("docs/Desktop Application Release Standard.md", all_paths)
            self.assertNotIn("bin/Release/net10.0-windows/win-x64/netstandard.dll", all_paths)
            self.assertEqual(
                evidence.detected_records["governance"],
                ["docs/Desktop Application Release Standard.md"],
            )

    def test_git_commit_uses_command_scoped_safe_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()

            with patch("single_project_evaluator.collector.subprocess.run") as run:
                run.return_value.stdout = "abc123\n"

                commit = _git_commit(root)

            self.assertEqual(commit, "abc123")
            args = run.call_args.args[0]
            self.assertEqual(args[:3], ["git", "-c", f"safe.directory={root.as_posix()}"])

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


if __name__ == "__main__":
    unittest.main()
