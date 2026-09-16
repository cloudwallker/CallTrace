from test_contract import run_project, data
import pytest


def test_python_all_elif_else_arms_retained(tmp_path):
    source = "def a(): pass\ndef b(): pass\ndef c(): pass\ndef main(x):\n    if x==1: a()\n    elif x==2: b()\n    else: c()"
    result, out = run_project(tmp_path, {"a.py": source})
    assert result.returncode == 0, result.stderr
    assert {e["target"] for e in data(out)["edges"]} == {"a", "b", "c"}
    assert [e["target"] for e in sorted(data(out)["edges"], key=lambda e: e["order"])] == ["a", "b", "c"]
    steps = data(out, "sequence.json")["steps"]
    assert steps[0]["else_steps"][0]["else_steps"][0]["method"] == "c"


@pytest.mark.parametrize("file,source,target", [
    ("a.js", "function leaf(){} const main = leaf => leaf();", "leaf"),
    ("a.py", "class A:\n    def leaf(self): pass\ndef main(A):\n    a=A()\n    a.leaf()", "a.leaf"),
    ("a.py", "def leaf(): pass\ndef main(cm):\n    with cm as leaf:\n        leaf()", "leaf"),
    ("a.js", "function leaf(){} function main(){try{throw other;}catch(leaf){leaf();}}", "leaf"),
])
def test_review_shadowed_values_never_exact(tmp_path, file, source, target):
    result, out = run_project(tmp_path, {file: source})
    assert result.returncode == 0, result.stderr
    edge = next(e for e in data(out)["edges"] if e["target"] == target)
    assert edge["resolution"] == "unresolved"


@pytest.mark.parametrize("extension", ["js", "ts"])
def test_nonexported_class_not_importable(tmp_path, extension):
    result, out = run_project(tmp_path, {"a." + extension: "import {B} from './b'; function main(){B.leaf()}", "b." + extension: "class B {static leaf(){}}"})
    assert result.returncode == 0, result.stderr
    assert data(out)["edges"][0]["resolution"] == "unresolved"
