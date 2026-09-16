"""Acceptance contracts: a false exact edge must break these tests."""
from pathlib import Path
import json
import subprocess
import sys
import os

import pytest


def run_project(tmp_path, files, entry="main", depth=3):
    for name, source in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "calltrace", "sequence", str(tmp_path),
         "--entry", entry, "--depth", str(depth), "--output", str(tmp_path / "out")],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    return result, tmp_path / "out"


def data(out, name="callgraph.json"):
    return json.loads((out / name).read_text(encoding="utf-8"))


CASES = [
    ({"a.py": "from b import leaf\ndef main():\n    leaf()\n", "b.py": "def leaf():\n    pass\n"}, "main"),
    ({"a.js": "import {leaf} from './b.js'; function main(){leaf();}", "b.js": "export function leaf(){}"}, "main"),
    ({"a.ts": "import {leaf as run} from './b'; function main(){run();}", "b.ts": "export function leaf(): void {}"}, "main"),
    ({"A.java": "package demo; class A { static void main(){ B.leaf(); } }", "B.java": "package demo; class B { static void leaf(){} }"}, "A.main"),
    ({"a.go": "package demo\nfunc main(){ leaf() }", "b.go": "package demo\nfunc leaf(){}"}, "main"),
]


@pytest.mark.parametrize("files,entry", CASES)
def test_cross_file_evidence(tmp_path, files, entry):
    result, out = run_project(tmp_path, files, entry)
    assert result.returncode == 0, result.stderr
    graph = data(out)
    assert len(graph["edges"]) == 1
    edge = graph["edges"][0]
    assert edge["resolution"] == "exact"
    assert edge["callee"].endswith("leaf") or "leaf(" in edge["callee"]
    assert edge["file"] and edge["line"] >= 1 and edge["rule"]
    assert data(out, "unresolved.json")["calls"] == []
    assert (out / "sequence.mmd").read_text(encoding="utf-8").startswith("sequenceDiagram")


def test_unknown_never_matches_global_name(tmp_path):
    result, out = run_project(tmp_path, {"a.py": "def leaf(): pass\ndef main(provider):\n    provider.leaf()\n"})
    assert result.returncode == 0, result.stderr
    edge = data(out)["edges"][0]
    assert edge["resolution"] == "unresolved" and edge["callee"] is None
    assert data(out, "unresolved.json")["calls"][0]["reason"]
    assert "unresolved" in (out / "sequence.mmd").read_text(encoding="utf-8")


def test_nested_order_cycles_depth_and_repeat(tmp_path):
    files = {"a.py": "def g(): pass\ndef f(x): pass\ndef main():\n    f(g())\n    g()\n    main()\n"}
    result, out = run_project(tmp_path, files)
    assert result.returncode == 0, result.stderr
    edges = data(out)["edges"]
    assert [e["expression"] for e in sorted(edges, key=lambda e: e["order"])] == ["g()", "f(g())", "g()", "main()"]
    assert "recursive" in (out / "sequence.mmd").read_text(encoding="utf-8")
    result, out = run_project(tmp_path, files, depth=0)
    assert result.returncode == 0
    assert data(out)["edges"] == []


def test_branches_loops_await_and_early_return(tmp_path):
    source = "async def leaf(): pass\nasync def main(x):\n    if x:\n        await leaf()\n    else:\n        leaf()\n    while leaf():\n        leaf()\n        return\n    leaf()\n"
    result, out = run_project(tmp_path, {"a.py": source})
    assert result.returncode == 0, result.stderr
    mmd = (out / "sequence.mmd").read_text(encoding="utf-8")
    for expected in ["alt ", "else", "loop ", "await", "return"]:
        assert expected in mmd


def test_ambiguous_entry(tmp_path):
    result, out = run_project(tmp_path, {"a.py": "def main(): pass", "b.py": "def main(): pass"})
    assert result.returncode == 2
    assert "a.py::main" in result.stderr and "b.py::main" in result.stderr
    assert not out.exists()


def test_invalid_source_diagnosed(tmp_path):
    result, out = run_project(tmp_path, {"a.py": "def main():\n    unknown()\n", "bad.py": "def broken(\n"})
    assert result.returncode == 1
    assert data(out)["diagnostics"]
    assert "incomplete" in (out / "report.md").read_text(encoding="utf-8")


def test_relocation_and_determinism(tmp_path):
    files = {"中文.py": "def main():\n    missing()\n"}
    a, out_a = run_project(tmp_path / "a", files)
    b, out_b = run_project(tmp_path / "b", files)
    assert a.returncode == b.returncode == 0
    for name in ["callgraph.json", "sequence.json", "sequence.mmd", "unresolved.json", "report.md"]:
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes()
