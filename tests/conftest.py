"""Export each integration diagram for validation by the official parser."""
import hashlib
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def export_diagrams(request, tmp_path):
    yield
    root = tmp_path
    output = Path(__file__).resolve().parents[1] / "artifacts" / "mermaid"
    for path in root.rglob("*.mmd"):
        output.mkdir(parents=True, exist_ok=True)
        key = request.node.nodeid + "/" + path.relative_to(root).as_posix()
        (output / (hashlib.sha256(key.encode()).hexdigest()[:20] + ".mmd")).write_bytes(path.read_bytes())
