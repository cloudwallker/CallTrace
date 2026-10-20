from pathlib import Path

import pytest

from calltrace.core.analyzer import analyze


@pytest.mark.parametrize(
    ("import_line", "expression"),
    [
        ("from service import send", "send()"),
        ("import service", "service.send()"),
    ],
)
@pytest.mark.parametrize(
    ("wildcard_import", "resolution", "callee"),
    [
        ("from alternate import *\n", "unresolved", None),
        ("", "exact", "service.py::send"),
    ],
)
def test_imported_function_is_not_exact_when_wildcard_import_can_replace_it(
    tmp_path: Path,
    import_line: str,
    expression: str,
    wildcard_import: str,
    resolution: str,
    callee: str | None,
) -> None:
    (tmp_path / "service.py").write_text(
        "def send():\n    pass\n" + wildcard_import, encoding="utf-8"
    )
    (tmp_path / "alternate.py").write_text("def send():\n    pass\n", encoding="utf-8")
    (tmp_path / "entry.py").write_text(
        f"{import_line}\ndef main():\n    {expression}\n", encoding="utf-8"
    )

    project = analyze(tmp_path)
    (call,) = project.calls.values()

    assert project.diagnostics == []
    assert call.expression == expression
    assert call.resolution == resolution
    assert call.callee == callee
