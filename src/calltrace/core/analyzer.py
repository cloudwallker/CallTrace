from pathlib import Path
import re
from .discovery import discover
from .models import Project, SourceUnit
from .resolution import Resolver
from calltrace.languages.treesitter import parse_source


def analyze(root: Path, output: Path | None = None) -> Project:
    units = []
    for path, language in discover(root, output):
        relative = path.relative_to(root).as_posix()
        try:
            source = path.read_bytes()
            source.decode("utf-8")
            units.append(parse_source(relative, language, source))
        except (OSError, UnicodeError) as error:
            unit = SourceUnit(relative, language, "")
            unit.diagnostics.append({"file": relative, "line": 1, "message": type(error).__name__ + ": unable to read UTF-8 source"})
            units.append(unit)
    go_module = ""
    manifest = root / "go.mod"
    if manifest.is_file():
        try:
            match = re.search(r'^\s*module\s+([^\s]+)', manifest.read_text(encoding="utf-8"), re.MULTILINE)
            if match:
                go_module = match[1].strip('"')
        except (OSError, UnicodeError):
            unit = SourceUnit("go.mod", "go", "")
            unit.diagnostics.append({"file": "go.mod", "line": 1, "message": "unable to read module manifest"})
            units.append(unit)
    return Resolver(Project(units, go_module)).resolve()
