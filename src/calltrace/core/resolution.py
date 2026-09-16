"""Scope/import based resolution. Never fall back to global name matching."""
import posixpath
import re
from .models import Project


class EntryError(ValueError):
    pass


def select_entry(project: Project, query: str):
    matches = []
    for s in project.symbols.values():
        names = {s.symbol_id, s.name, s.qualified_name,
                 f"{s.file}::{s.qualified_name}", f"{s.module}.{s.qualified_name}"}
        if query in names:
            matches.append(s)
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise EntryError(f"Entry not found: {query}")
    candidates = "\n".join(f"  {s.symbol_id} ({s.file}:{s.line})" for s in sorted(matches, key=lambda x: x.symbol_id))
    raise EntryError(f"Ambiguous entry: {query}\nChoose an exact symbol ID:\n{candidates}")


class Resolver:
    def __init__(self, project):
        self.project = project
        self.units = {u.file: u for u in project.units}
        self.symbols = project.symbols

    def imported_units(self, unit, module):
        lang = unit.language
        if lang == "python":
            if module.startswith("."):
                dots = len(module) - len(module.lstrip("."))
                package = unit.module.split(".") if unit.file.endswith("/__init__.py") else unit.module.split(".")[:-1]
                if dots > len(package):
                    return []
                module = ".".join(package[:len(package) - dots + 1] + ([module[dots:]] if module[dots:] else []))
            return [u for u in self.units.values() if u.language == lang and u.module == module]
        if lang in {"javascript", "typescript"}:
            if not module.startswith("."):
                return []
            base = posixpath.normpath(posixpath.join(posixpath.dirname(unit.file), module))
            paths = {base} if posixpath.splitext(base)[1] else {base + ext for ext in (".js", ".mjs", ".jsx", ".ts", ".tsx")} | {base + "/index" + ext for ext in (".js", ".ts", ".tsx")}
            return [u for u in self.units.values() if u.file in paths and u.language in {"javascript", "typescript"}]
        if lang == "go":
            prefix = self.project.go_module
            if not prefix or not (module == prefix or module.startswith(prefix + "/")):
                return []
            directory = module[len(prefix):].lstrip("/")
            return [u for u in self.units.values() if u.language == lang and posixpath.dirname(u.file) == directory]
        return []

    def named(self, units, name, owner="", exported=False):
        return [s for u in units for s in u.symbols if s.name == name and s.owner == owner
                and not s.scope and (not exported or s.exported)
                and "*" not in s.blocked and name not in u.blocked]

    def exported(self, units, name, seen=frozenset()):
        result = []
        for unit in units:
            key = (unit.file, name)
            if key in seen:
                continue
            binding = unit.exports.get(name)
            if binding:
                if binding["module"]:
                    result += self.exported(self.imported_units(unit, binding["module"]), binding["name"], seen | {key})
                elif binding["name"] in unit.imports:
                    imp = unit.imports[binding["name"]]
                    result += self.exported(self.imported_units(unit, imp["module"]), imp["name"], seen | {key})
                else:
                    result += self.named([unit], binding["name"])
            else:
                result += self.named([unit], name, exported=True)
        return result

    def class_locations(self, unit, target):
        # Return the declared class and the files that belong to its package/module.
        if "." in target:
            head, tail = target.split(".", 1)
            imp = unit.imports.get(head)
            if imp and imp["kind"] == "module":
                if unit.language in {"javascript", "typescript"}:
                    return self.exported_classes(self.imported_units(unit, imp["module"]), tail)
                return [(u, tail) for u in self.imported_units(unit, imp["module"]) if tail in u.classes]
            return []
        imp = unit.imports.get(target)
        if imp:
            if unit.language == "java" and imp["kind"] == "class":
                package, _, name = imp["module"].rpartition(".")
                return [(u, name) for u in self.units.values() if u.language == "java" and u.module == package and name in u.classes]
            if imp["kind"] == "symbol":
                if unit.language in {"javascript", "typescript"}:
                    return self.exported_classes(self.imported_units(unit, imp["module"]), imp["name"])
                return [(u, imp["name"]) for u in self.imported_units(unit, imp["module"]) if imp["name"] in u.classes]
            return []
        pool = [unit]
        if unit.language == "java":
            pool = [u for u in self.units.values() if u.language == "java" and u.module == unit.module]
        if unit.language == "go":
            pool = self.same_go_package(unit)
            # Go method sets expose owner types, including structs and aliases.
            return [(u, target) for u in pool if any(s.owner == target for s in u.symbols)]
        return [(u, target) for u in pool if target in u.classes]

    def exported_classes(self, units, name, seen=frozenset()):
        result = []
        for unit in units:
            key = (unit.file, name)
            binding = unit.exports.get(name)
            if key in seen or not binding:
                continue
            if binding["module"]:
                result += self.exported_classes(self.imported_units(unit, binding["module"]), binding["name"], seen | {key})
            elif binding["name"] in unit.classes and binding["name"] not in unit.blocked:
                result.append((unit, binding["name"]))
        return result

    def same_go_package(self, unit):
        return [u for u in self.units.values() if u.language == "go" and u.module == unit.module
                and posixpath.dirname(u.file) == posixpath.dirname(unit.file)]

    def resolve(self):
        for call in self.project.calls.values():
            caller = self.symbols[call.caller]
            unit = self.units[caller.file]
            target = re.sub(r"\s+", "", call.target)
            head = target.split(".")[0]
            if call.context.get("invalid"):
                continue
            if call.context.get("deferred"):
                call.reason = "deferred execution is outside v0.1 ordering model"
                continue
            if head in caller.blocked or head in unit.blocked or "*" in unit.blocked:
                call.reason = "name is shadowed, assigned, or imported dynamically"
                continue
            if "." not in target and target in caller.bindings:
                call.reason = "local value shadows function name"
                continue
            enclosing = [s for s in unit.symbols if s.qualified_name == caller.scope or caller.scope.startswith(s.qualified_name + ".")]
            if any(head in s.blocked or head in s.bindings for s in enclosing):
                call.reason = "enclosing scope shadows target"
                continue
            candidates, rule, reason = [], "", "target has no supported lexical or import binding"
            if "." not in target and re.fullmatch(r"[\w$]+", target):
                imp = unit.imports.get(target)
                if imp:
                    if unit.language == "java" and imp["kind"] == "static":
                        package, cls, name = imp["module"].rsplit(".", 2)
                        pool = [u for u in self.units.values() if u.language == "java" and u.module == package]
                        candidates = [s for s in self.named(pool, name, cls) if s.static]
                    elif imp["kind"] == "symbol":
                        pool = self.imported_units(unit, imp["module"])
                        candidates = self.exported(pool, imp["name"]) if unit.language in {"javascript", "typescript"} else self.named(pool, imp["name"])
                    rule = "explicit-import"
                    reason = "import target is external, unsupported, or ambiguous"
                else:
                    # Nested scopes are lexical, never arbitrary project matches.
                    scope = caller.qualified_name
                    while scope:
                        candidates = [s for s in unit.symbols if s.scope == scope and s.name == target and "*" not in s.blocked]
                        if candidates:
                            break
                        scope = scope.rpartition(".")[0]
                    if not candidates:
                        pool = self.same_go_package(unit) if unit.language == "go" else [unit]
                        candidates = self.named(pool, target)
                    if not candidates and unit.language == "java" and caller.owner:
                        candidates = [s for s in self.named([unit], target, caller.owner) if s.static]
                    rule = "lexical-binding" if unit.language != "go" else "same-package"
            elif "." in target:
                receiver, _, method = target.rpartition(".")
                imp = unit.imports.get(receiver)
                if imp and imp["kind"] == "symbol" and unit.language == "python":
                    base = self.imported_units(unit, imp["module"])
                    # `from pkg import submodule` is a module binding only when
                    # no declaration/assignment in pkg competes for that name.
                    declared = any(imp["name"] in u.classes or imp["name"] in u.blocked or any(s.name == imp["name"] for s in u.symbols) for u in base)
                    if not declared:
                        combined = imp["module"] + ("" if imp["module"].endswith(".") else ".") + imp["name"]
                        if self.imported_units(unit, combined):
                            imp = {"module": combined, "kind": "module"}
                if imp and imp["kind"] == "module":
                    pool = self.imported_units(unit, imp["module"])
                    candidates = self.exported(pool, method) if unit.language in {"javascript", "typescript"} else self.named(pool, method)
                    if unit.language == "go" and not method[:1].isupper():
                        candidates = []
                    rule = "module-import"
                    reason = "import target is external, unsupported, or ambiguous"
                else:
                    receiver_type = caller.bindings.get(receiver)
                    concrete = False
                    if receiver_type:
                        concrete = True
                        if "@" in receiver_type:
                            receiver_type, offset = receiver_type.rsplit("@", 1)
                            if call.context.get("byte", 0) < int(offset):
                                receiver_type = None
                                reason = "receiver assignment occurs after call"
                        constructor_head = receiver_type.split(".")[0] if receiver_type else ""
                        if constructor_head in caller.blocked or constructor_head in caller.bindings or constructor_head in unit.blocked or any(constructor_head in s.blocked or constructor_head in s.bindings for s in enclosing):
                            receiver_type = None
                            reason = "constructor name is shadowed"
                        locations = self.class_locations(unit, receiver_type) if receiver_type else []
                    else:
                        locations = self.class_locations(unit, receiver)
                    for location, owner in locations:
                        candidates += [s for s in self.named([location], method, owner)
                                       if concrete or s.static or unit.language == "go"]
                    rule = "concrete-receiver" if concrete else "static-method"
                    reason = "receiver type or dispatch target could not be resolved"
            # Constructors are retained without invented implicit __init__ edges.
            if call.context.get("constructor"):
                candidates = []
                reason = "constructor dispatch is not expanded in v0.1"
            unique = {s.symbol_id: s for s in candidates}
            call.candidates = sorted(unique)
            if len(unique) == 1:
                call.callee = next(iter(unique))
                call.resolution = "exact"
                call.confidence = 1.0
                call.rule = rule
                call.reason = ""
            else:
                call.reason = "multiple possible targets" if unique else reason
        return self.project
