# CallTrace

### Static sequence diagrams with source evidence and visible unknowns

**Follow calls from a selected function and generate Mermaid diagrams with source locations, control flow, and unresolved targets—without executing the project or using an LLM.**

English | [简体中文](README.md)

[Installation](#install-from-source) · [Usage](#usage) · [Support matrix](docs/support.md)

```bash
calltrace sequence examples/python --entry "UserService.login" --depth 4
```

CallTrace does not use an LLM to decide whether function A calls function B. It does not execute the analyzed project or install its dependencies.

## What v0.1 supports

- Python, JavaScript, TypeScript, Java and Go through Tree-sitter grammars.
- Entry selection by short name, qualified name or a file-qualified symbol ID. Ambiguous entries list candidates instead of guessing.
- Basic cross-file imports, lexical bindings and provable local receivers.
- Ordered nested calls, branches, loops, async/await annotations and recursion boundaries.
- Depth-limited traversal with retained unknown calls and source evidence.
- Deterministic JSON and Mermaid output, with no LLM or network service required during analysis.

The diagram represents static structure, not recorded runtime execution. Dynamic dispatch, external libraries, reflection, ambiguous overloads and unsupported bindings remain unresolved.

## Install from source

Requires Python 3.11 or later.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m calltrace sequence examples/python --entry UserService.login --depth 4
```

Node.js is only needed for development-time Mermaid validation and rendering.

## Usage

```bash
calltrace sequence PROJECT --entry "Class.method" --depth 4
calltrace trace PROJECT --entry "src/auth.py::login" --depth 3 --output output/login
```

`trace` is an alias for `sequence`. Depth defaults to `3`; the entry is depth `0`. Depth `0` shows only the entry, and depth `1` includes its direct calls. A complete symbol ID can disambiguate overloaded or same-named functions.

The default output directory is `PROJECT/.calltrace/<entry>/`:

| File | Contents |
| --- | --- |
| `callgraph.json` | Symbols and unique call sites within the selected traversal, with source evidence and project diagnostics |
| `sequence.json` | Sequence intermediate representation; the renderer's only input |
| `sequence.mmd` | Generated Mermaid sequence diagram |
| `unresolved.json` | Unknown targets, source expressions, reasons and candidates |
| `report.md` | Counts, unresolved calls, expansion boundaries and diagnostics |

An explicit output directory replaces the default; its five generated files are overwritten on subsequent runs. JSON schema version is `0.1`. Paths in artifacts are project-relative, and source files are decoded as UTF-8.

### Resolution states

| State | Meaning |
| --- | --- |
| `exact` | A unique binding under the supported static rules; not a proof of runtime behavior |
| `heuristic` | Reserved in the data model; v0.1 does not generate heuristic guesses |
| `unresolved` | The target cannot be established; the call remains visible and is not expanded |

`confidence=1.0` is a rule marker for `exact`, not a calibrated probability. An empty unresolved list does not establish whole-program completeness.

Exit codes: `0` means output was generated without project diagnostics; `1` indicates diagnostics or an I/O failure; `2` indicates invalid arguments or a missing/ambiguous entry. Exit code `0` may still include unresolved calls and depth boundaries.

## Reproducible example

```bash
calltrace sequence examples/python --entry UserService.login --depth 4
```

The included fixture produces five resolved call sites and one unresolved call. The diagram retains `await find_user(email)`, both branches, the recursive `audit` call and the unknown `provider.notify(email)` target. The [Chinese README](README.md) includes the generated Mermaid diagram in full.

## Example and build

```bash
calltrace sequence examples/python --entry UserService.login --depth 4
npm ci
npm run validate:mermaid
python -m build
```

The first command generates the example diagram. Validation uses the pinned official Mermaid parser and fails if no diagrams are present.

To render the example:

```bash
npx --no-install mmdc -i examples/python/.calltrace/UserService.login/sequence.mmd -o examples/python/.calltrace/UserService.login/sequence.svg
```

If browser downloads are unavailable, set `PUPPETEER_SKIP_DOWNLOAD=true` during npm installation and point `PUPPETEER_EXECUTABLE_PATH` to an installed Chrome executable. Syntax validation does not launch a browser.

## Design and limits

Source discovery, syntax extraction, reference resolution, call graph traversal, sequence IR and rendering are separate layers. The analyzer never renders Mermaid directly, and the renderer never reads project source.

There is no whole-program type inference, runtime instrumentation, framework-specific dependency injection, UI or distributed tracing. Constructor internals are not expanded. `self`/`this`, callbacks and unknown receivers are treated conservatively. Anonymous IDs depend on source positions. Go build tags/workspaces and TypeScript path mappings are not fully modeled.

See the detailed [support matrix](docs/support.md) and [upstream review](docs/upstream-review.md) for supported import patterns and design references (currently in Chinese).

## License

[MIT](LICENSE). The implementation is original; the upstream review records conceptual references rather than copied code. Dependencies retain their own licenses.
