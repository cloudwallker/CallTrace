import pytest
from test_contract import run_project, data


@pytest.mark.parametrize("file,source", [
    ("a.py", "def leaf(): pass\ndef main():\n    unused = lambda: leaf()\n"),
    ("a.go", "package demo\nfunc leaf(){}\nfunc main(){unused:=func(){leaf()};_ = unused}"),
])
def test_anonymous_body_not_executed_when_created(tmp_path, file, source):
    result, out = run_project(tmp_path, {file: source})
    assert result.returncode == 0, result.stderr
    assert data(out)["edges"] == []


def test_output_directory_and_dependency_sources_excluded(tmp_path):
    files = {"a.py": "def main(): pass", "node_modules/evil.py": "def main(): bad()", "out/evil.py": "def main(): bad()"}
    result, out = run_project(tmp_path, files)
    assert result.returncode == 0, result.stderr
    assert len(data(out)["symbols"]) == 1


@pytest.mark.parametrize("extension", ["js", "ts"])
def test_imported_static_class_method(tmp_path, extension):
    result, out = run_project(tmp_path, {"a." + extension: "import {B} from './b'; function main(){B.leaf()}", "b." + extension: "export class B {static leaf(){}}"})
    assert result.returncode == 0, result.stderr
    assert data(out)["edges"][0]["resolution"] == "exact"


def test_fully_qualified_python_entry(tmp_path):
    result, out = run_project(tmp_path, {"pkg/a.py": "class C:\n    @staticmethod\n    def leaf(): pass\n"}, "pkg.a.C.leaf")
    assert result.returncode == 0, result.stderr
    assert data(out)["entry"] == "pkg/a.py::C.leaf"
