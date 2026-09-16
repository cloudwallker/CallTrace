import pytest
from test_contract import run_project, data


@pytest.mark.parametrize("extension", ["js", "ts"])
def test_named_arrow_binding(tmp_path, extension):
    result, out = run_project(tmp_path, {"a." + extension: "const leaf = () => {}; function main(){leaf()}"})
    assert result.returncode == 0, result.stderr
    assert data(out)["edges"][0]["resolution"] == "exact"


def test_python_relative_module_import(tmp_path):
    result, out = run_project(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "from . import b\ndef main(): b.leaf()", "pkg/b.py": "def leaf(): pass"})
    assert result.returncode == 0, result.stderr
    assert data(out)["edges"][0]["callee"] == "pkg/b.py::leaf"


def test_python_dotted_module_import(tmp_path):
    result, out = run_project(tmp_path, {"pkg/__init__.py": "", "a.py": "import pkg.b\ndef main(): pkg.b.leaf()", "pkg/b.py": "def leaf(): pass"})
    assert result.returncode == 0, result.stderr
    assert data(out)["edges"][0]["callee"] == "pkg/b.py::leaf"


@pytest.mark.parametrize("import_text,expected", [("import leaf from './b'", "exact"), ("import {leaf} from './b'", "unresolved")])
def test_default_export_is_not_named_export(tmp_path, import_text, expected):
    result, out = run_project(tmp_path, {"a.js": import_text + "; function main(){leaf()}", "b.js": "export default function leaf(){}"})
    assert result.returncode == 0, result.stderr
    assert data(out)["edges"][0]["resolution"] == expected
