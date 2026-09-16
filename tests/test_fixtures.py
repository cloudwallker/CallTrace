from pathlib import Path
import pytest
from test_contract import run_project, data


@pytest.mark.parametrize("language", ["python", "javascript", "typescript", "java", "go"])
def test_fixture_project(tmp_path, language):
    fixture = Path(__file__).parent / "fixtures" / language
    files = {p.relative_to(fixture).as_posix(): p.read_text(encoding="utf-8") for p in fixture.rglob("*") if p.is_file()}
    result, out = run_project(tmp_path, files, "Main.main" if language == "java" else "main")
    assert result.returncode == 0, result.stderr
    graph = data(out)
    assert sum(e["resolution"] == "unresolved" for e in graph["edges"]) == 1
    assert any(e["callee"] and ("service" in e["callee"].lower()) for e in graph["edges"])
    mmd = (out / "sequence.mmd").read_text(encoding="utf-8")
    assert "recursive" in mmd and "loop " in mmd and "alt " in mmd


def test_repeated_output_is_identical(tmp_path):
    files = {"a.py": "def main():\n    unknown()\n"}
    first, output = run_project(tmp_path, files)
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    second, output = run_project(tmp_path, files)
    assert first.returncode == second.returncode == 0
    assert before == {p.name: p.read_bytes() for p in output.iterdir()}
