from dataclasses import dataclass, field, asdict
from typing import Literal

Resolution = Literal["exact", "heuristic", "unresolved"]


@dataclass
class Symbol:
    symbol_id: str
    name: str
    qualified_name: str
    kind: str
    language: str
    file: str
    line: int
    module: str = ""
    owner: str = ""
    scope: str = ""
    signature: str = ""
    static: bool = False
    exported: bool = False
    bindings: dict[str, str] = field(default_factory=dict)
    blocked: list[str] = field(default_factory=list)
    body: list[dict] = field(default_factory=list)


@dataclass
class Call:
    call_id: str
    caller: str
    expression: str
    target: str
    file: str
    line: int
    column: int
    end_line: int
    end_column: int
    order: int
    context: dict = field(default_factory=dict)
    callee: str | None = None
    resolution: Resolution = "unresolved"
    confidence: float = 0.0
    rule: str = "unresolved"
    reason: str = "target could not be resolved"
    candidates: list[str] = field(default_factory=list)


@dataclass
class SourceUnit:
    file: str
    language: str
    module: str
    symbols: list[Symbol] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    imports: dict[str, dict] = field(default_factory=dict)
    exports: dict[str, dict] = field(default_factory=dict)
    classes: list[str] = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)


@dataclass
class Project:
    units: list[SourceUnit]
    go_module: str = ""

    @property
    def symbols(self):
        return {s.symbol_id: s for u in self.units for s in u.symbols}

    @property
    def calls(self):
        return {c.call_id: c for u in self.units for c in u.calls}

    @property
    def diagnostics(self):
        return [d for u in self.units for d in u.diagnostics]


def public_symbol(symbol: Symbol):
    result = asdict(symbol)
    for name in ("bindings", "blocked", "body"):
        result.pop(name)
    return result
