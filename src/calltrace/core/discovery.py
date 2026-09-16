import os
from pathlib import Path

EXTENSIONS = {".py": "python", ".js": "javascript", ".mjs": "javascript",
              ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript",
              ".java": "java", ".go": "go"}
EXCLUDED = {".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
            "vendor", "dist", "build", "target", ".cache", ".calltrace",
            "__pycache__", ".pytest_cache", ".tox"}


def discover(root: Path, output: Path | None = None):
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED
                         and not (Path(directory) / d).is_symlink()
                         and (output is None or (Path(directory) / d).resolve() != output.resolve()))
        for name in sorted(files):
            path = Path(directory) / name
            if path.suffix in EXTENSIONS and not path.is_symlink():
                yield path, EXTENSIONS[path.suffix]
