"""Command line orchestration; analysis and rendering remain separate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from .core.analyzer import analyze
from .core.resolution import EntryError, select_entry
from .core.sequence import build_sequence
from .core.render import render_mermaid


def report(graph, sequence, unresolved):
    edges = graph["edges"]
    status = "incomplete" if graph["diagnostics"] else "complete (within documented static model)"
    counts = {kind: sum(e["resolution"] == kind for e in edges) for kind in ("exact", "heuristic", "unresolved")}
    lines = ["# CallTrace report", "", f"Entry: `{graph['entry']}`", "", f"Status: {status}", "",
             f"Depth: {sequence['depth']} (entry = 0)", "", "## Unique call sites", "",
             *(f"- {kind}: {count}" for kind, count in counts.items()), "", "## Unresolved calls", ""]
    for call in unresolved["calls"]:
        expression = call["expression"].replace("`", "'").replace("\n", " ")
        lines.append(f"- `{call['file']}:{call['line']}:{call['column']}` `{expression}` — {call['reason']}")
    if not unresolved["calls"]:
        lines.append("None.")
    lines += ["", "## Expansion boundaries", ""]
    def boundaries(steps):
        for step in steps:
            if step.get("recursive") or step.get("truncated"):
                lines.append(f"- `{step['call_id']}`: {'recursion' if step.get('recursive') else 'depth limit'}")
            for key in ("steps", "else_steps"):
                boundaries(step.get(key, []))
    boundaries(sequence["steps"])
    if sequence["depth"] == 0:
        lines.append("- Entry body not expanded (depth 0).")
    lines += ["", "## Project-wide diagnostics", ""]
    lines += [f"- {d['file']}:{d['line']}: {d['message']}" for d in graph["diagnostics"]] or ["None."]
    lines += ["", "This is a structural static diagram, not a recorded runtime trace.",
              "exact means unique binding under supported static rules; runtime mutation is not modeled.",
              "CallTrace does not use an LLM to decide whether function A calls function B.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="calltrace", description="Evidence-backed static sequence diagrams")
    parser.add_argument("command", choices=["sequence", "trace"])
    parser.add_argument("project", type=Path)
    parser.add_argument("--entry", required=True)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.depth < 0:
        parser.error("--depth must be nonnegative")
    root = args.project.resolve()
    if not root.is_dir():
        parser.error("project must be an existing directory")
    try:
        project = analyze(root, args.output)
        entry = select_entry(project, args.entry)
        graph, sequence, unresolved = build_sequence(project, entry, args.depth)
        mermaid = render_mermaid(sequence)
        if args.output:
            output = args.output.resolve()
        else:
            safe = re.sub(r"[^\w.-]", "_", entry.qualified_name).strip(".") or "entry"
            collision = sum(s.qualified_name == entry.qualified_name for s in project.symbols.values()) > 1
            if collision:
                safe += "-" + hashlib.sha256(entry.symbol_id.encode()).hexdigest()[:8]
            output = root / ".calltrace" / safe
        output.mkdir(parents=True, exist_ok=True)
        for name, content in [("callgraph.json", graph), ("sequence.json", sequence), ("unresolved.json", unresolved)]:
            (output / name).write_text(json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        (output / "sequence.mmd").write_text(mermaid, encoding="utf-8", newline="\n")
        (output / "report.md").write_text(report(graph, sequence, unresolved), encoding="utf-8", newline="\n")
        print(f"Entry: {entry.qualified_name}")
        def tree(steps, level=1):
            for step in steps:
                if step["type"] == "call":
                    print("  " * level + f"{step['expression']} [{step['resolution']}]")
                tree(step.get("steps", []), level + (step["type"] == "call"))
                tree(step.get("else_steps", []), level)
        tree(sequence["steps"])
        for state in ("exact", "heuristic", "unresolved"):
            print(f"{state}: {sum(e['resolution'] == state for e in graph['edges'])}")
        print(f"Mermaid: {output / 'sequence.mmd'}")
        return 1 if graph["diagnostics"] else 0
    except EntryError as error:
        print(str(error), file=sys.stderr)
        return 2
    except OSError as error:
        print(f"I/O error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
