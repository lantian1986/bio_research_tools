from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = (
    ROOT / ".agents/skills/literature-review/scripts/literature_helpers.py"
)


def load_helper():
    spec = importlib.util.spec_from_file_location("literature_helpers", HELPER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_dois_and_style_pass() -> None:
    helper = load_helper()
    assert helper.extract_dois(
        {"text": "See https://doi.org/10.1038/s41586-020-2649-2."}
    ) == ["10.1038/s41586-020-2649-2"]
    result = helper.style_pass({"draft": "DOIs were verified against CrossRef."})
    assert result["ok"] is False
    assert {issue["code"] for issue in result["issues"]} == {"PROCNOTE"}


def test_cli_rejects_malformed_json(tmp_path: Path) -> None:
    request = tmp_path / "bad.json"
    request.write_text("{", encoding="utf-8")
    process = subprocess.run(
        [sys.executable, str(HELPER_PATH), "verify-dois", str(request)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 2
    payload = json.loads(process.stdout)
    assert payload["version"] == 1
    assert payload["ok"] is False
    assert "literature-helper:" in process.stderr


def test_cli_requires_schema_version(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"dois": []}), encoding="utf-8")
    process = subprocess.run(
        [sys.executable, str(HELPER_PATH), "verify-dois", str(request)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 2
    assert json.loads(process.stdout)["ok"] is False
