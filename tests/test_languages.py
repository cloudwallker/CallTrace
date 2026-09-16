"""Shared behavior matrix across five real grammars."""
from pathlib import Path
import pytest
from test_contract import run_project, data


SOURCES = [
    ("a.py", "def leaf(): pass\ndef inner(x): pass\ndef main(x):\n    inner(leaf())\n    if x:\n        leaf()\n    else:\n        leaf()\n    while leaf():\n        leaf()\n    main(x)\n", "main"),
    ("a.js", "function leaf(){} function inner(x){} function main(x){inner(leaf());if(x){leaf()}else{leaf()}while(leaf()){leaf()}main(x)}", "main"),
    ("a.ts", "function leaf(): boolean{return true} function inner(x: boolean){} function main(x: boolean){inner(leaf());if(x){leaf()}else{leaf()}while(leaf()){leaf()}main(x)}", "main"),
    ("A.java", "class A {static boolean leaf(){return true;} static void inner(boolean x){} static void main(boolean x){inner(leaf());if(x){leaf();}else{leaf();}while(leaf()){leaf();}main(x);}}", "A.main"),
    ("a.go", "package demo\nfunc leaf() bool{return true}\nfunc inner(x bool){}\nfunc main(x bool){inner(leaf());if x{leaf()}else{leaf()};for leaf(){leaf()};main(x)}", "main"),
]


@pytest.mark.parametrize("filename,source,entry", SOURCES)
def test_shared_control_and_order(tmp_path, filename, source, entry):
    result, output = run_project(tmp_path, {filename: source}, entry)
    assert result.returncode == 0, result.stderr
    graph = data(output)
    caller = next(s["symbol_id"] for s in graph["symbols"] if s["name"] == "main")
    calls = sorted([e for e in graph["edges"] if e["caller"] == caller], key=lambda e: e["order"])
    assert [c["target"] for c in calls] == ["leaf", "inner", "leaf", "leaf", "leaf", "leaf", "main"]
    assert all(c["resolution"] == "exact" for c in calls)
    mmd = (output / "sequence.mmd").read_text(encoding="utf-8")
    for token in ["alt ", "else", "loop ", "recursive"]:
        assert token in mmd


@pytest.mark.parametrize("ext,source", [
    ("py", "async def leaf(): pass\nasync def main():\n    await leaf()\n"),
    ("js", "async function leaf(){} async function main(){await leaf()}"),
    ("ts", "async function leaf(){} async function main(){await leaf()}"),
    ("go", "package demo\nfunc leaf(){}\nfunc main(){go leaf()}"),
])
def test_async_call_context(tmp_path, ext, source):
    result, output = run_project(tmp_path, {"a." + ext: source})
    assert result.returncode == 0, result.stderr
    assert data(output)["edges"][0]["context"].get("async" if ext == "go" else "await") is True


@pytest.mark.parametrize("ext,source", [
    ("py", "def leaf(): pass\ndef main():\n    def unused():\n        leaf()\n    leaf()\n"),
    ("js", "function leaf(){} function main(){function unused(){leaf()}leaf()}"),
    ("ts", "function leaf(){} function main(){const unused=()=>{leaf()};leaf()}"),
])
def test_nested_definition_not_executed(tmp_path, ext, source):
    result, output = run_project(tmp_path, {"a." + ext: source})
    assert result.returncode == 0, result.stderr
    assert len(data(output)["edges"]) == 1


@pytest.mark.parametrize("ext,source", [
    ("py", "def leaf(): pass\ndef main(leaf):\n    leaf()\n"),
    ("js", "function leaf(){} function main(leaf){leaf()}"),
    ("ts", "function leaf(){} function main(leaf: ()=>void){leaf()}"),
    ("go", "package demo\nfunc leaf(){}\nfunc main(leaf func()){leaf()}"),
])
def test_parameter_shadows_function(tmp_path, ext, source):
    result, output = run_project(tmp_path, {"a." + ext: source})
    assert result.returncode == 0, result.stderr
    assert data(output)["edges"][0]["resolution"] == "unresolved"


def test_relative_python_package(tmp_path):
    result, out = run_project(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "from .b import leaf as run\ndef main(): run()", "pkg/b.py": "def leaf(): pass"})
    assert result.returncode == 0, result.stderr
    assert data(out)["edges"][0]["callee"] == "pkg/b.py::leaf"


def test_imported_java_class(tmp_path):
    result, out = run_project(tmp_path, {"A.java": "package a; import b.B; class A {static void main(){B.leaf();}}", "b/B.java": "package b; public class B {public static void leaf(){}}"}, "A.main")
    assert result.returncode == 0, result.stderr
    assert data(out)["edges"][0]["callee"] == "b/B.java::B.leaf()"


def test_go_import_alias(tmp_path):
    result, out = run_project(tmp_path, {"go.mod": "module example.com/demo\n", "a.go": 'package main\nimport b "example.com/demo/service"\nfunc main(){b.Leaf()}', "service/b.go": "package service\nfunc Leaf(){}"})
    assert result.returncode == 0, result.stderr
    assert data(out)["edges"][0]["callee"] == "service/b.go::Leaf"
