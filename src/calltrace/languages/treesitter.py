"""Deterministic syntax adapters. No syntax node leaves this module.

Bindings deliberately use a small, conservative model: parameters and reassigned
names block resolution. Concrete local receivers must have one constructor
assignment before the call; annotations alone are not evidence of dispatch.
"""
import importlib
import posixpath
import re
from collections import Counter
from tree_sitter import Language, Parser

from calltrace.core.models import Call, SourceUnit, Symbol

FUNCTIONS = {"function_definition", "function_declaration", "method_definition",
             "method_declaration", "constructor_declaration", "arrow_function",
             "function_expression", "generator_function_declaration", "generator_function", "lambda", "func_literal"}
CLASSES = {"class_definition", "class_declaration", "interface_declaration", "enum_declaration"}
CALLS = {"call", "call_expression", "method_invocation", "new_expression", "object_creation_expression"}
LOOPS = {"for_statement", "while_statement", "for_in_statement", "enhanced_for_statement", "do_statement"}


def text(node):
    return node.text.decode("utf-8") if node else ""


def field(node, *names):
    if node:
        for name in names:
            value = node.child_by_field_name(name)
            if value is not None:
                return value
    return None


def walk(node, stop=()):
    yield node
    if node.type not in stop:
        for child in node.named_children:
            yield from walk(child, stop)


def module_name(file, language):
    if language == "python":
        return file.removesuffix(".py").replace("/", ".").removesuffix(".__init__")
    return posixpath.splitext(file)[0]


class Adapter:
    def __init__(self, language, file):
        module = importlib.import_module("tree_sitter_" + language)
        factory = (module.language_tsx if file.endswith(".tsx") else module.language_typescript) if language == "typescript" else module.language
        self.parser = Parser(Language(factory()))
        self.language = language
        self.unit = SourceUnit(file, language, module_name(file, language))
        self.definitions = []

    def parse(self, source):
        root = self.parser.parse(source).root_node
        for node in walk(root):
            if node.type == "ERROR" or node.is_missing:
                self.unit.diagnostics.append({"file": self.unit.file, "line": node.start_point.row + 1,
                                              "message": "syntax error; affected definitions are not resolved"})
        if self.language in {"java", "go"}:
            package = next((n for n in root.named_children if n.type in {"package_declaration", "package_clause"}), None)
            if package:
                self.unit.module = text(package.named_children[-1])
        self.extract_imports(root)
        self.extract_definitions(root)
        self.extract_exports(root)
        for symbol, node in self.definitions:
            self.extract_bindings(symbol, node)
            body = field(node, "body")
            if node.has_error:
                symbol.blocked.append("*")
            symbol.body = self.structure(body, symbol, {}) if body else []
        # Module writes can invalidate imported names and declarations.
        for node in walk(root, FUNCTIONS | CLASSES):
            if node.type in {"assignment", "assignment_expression", "augmented_assignment", "variable_declarator"}:
                value = field(node, "value")
                if value and value.type in FUNCTIONS:
                    continue
                name = text(field(node, "left", "name"))
                if name:
                    self.unit.blocked.append(name)
        return self.unit

    def extract_exports(self, root):
        if self.language not in {"javascript", "typescript"}:
            return
        for node in root.named_children:
            if node.type != "export_statement":
                continue
            source = text(field(node, "source")).strip("\"'")
            for item in walk(node, FUNCTIONS | CLASSES):
                if item.type == "export_specifier":
                    name = text(field(item, "name"))
                    alias = text(field(item, "alias")) or name
                    self.unit.exports[alias] = {"name": name, "module": source}
            declaration = field(node, "declaration", "value")
            if declaration and any(c.type == "default" for c in node.children):
                name = text(field(declaration, "name")) or text(declaration)
                self.unit.exports["default"] = {"name": name, "module": ""}

    def extract_imports(self, root):
        for node in root.named_children:
            t = node.type
            if self.language == "python" and t == "import_from_statement":
                module = text(field(node, "module_name"))
                for item in node.children_by_field_name("name"):
                    original = text(field(item, "name")) if item.type == "aliased_import" else text(item)
                    alias = text(field(item, "alias")) or original
                    self.unit.imports[alias] = {"module": module, "name": original, "kind": "symbol"}
                if any(n.type == "wildcard_import" for n in node.named_children):
                    self.unit.blocked.append("*")
            elif self.language == "python" and t == "import_statement":
                for item in node.children_by_field_name("name"):
                    original = text(field(item, "name")) if item.type == "aliased_import" else text(item)
                    alias = text(field(item, "alias")) or original.split(".")[0]
                    self.unit.imports[alias] = {"module": original if field(item, "alias") else alias, "name": "", "kind": "module"}
                    if not field(item, "alias") and "." in original:
                        self.unit.imports[original] = {"module": original, "name": "", "kind": "module"}
            elif self.language in {"javascript", "typescript"} and t == "import_statement":
                source = text(field(node, "source")).strip("\"'")
                for item in walk(node):
                    if item.type == "import_specifier":
                        original = text(field(item, "name"))
                        alias = text(field(item, "alias")) or original
                        self.unit.imports[alias] = {"module": source, "name": original, "kind": "symbol"}
                    elif item.type == "namespace_import":
                        alias = text(item.named_children[-1])
                        self.unit.imports[alias] = {"module": source, "name": "", "kind": "module"}
                    elif item.type == "import_clause":
                        for child in item.named_children:
                            if child.type == "identifier":
                                self.unit.imports[text(child)] = {"module": source, "name": "default", "kind": "symbol"}
            elif self.language == "java" and t == "import_declaration":
                value = text(node).removeprefix("import ").removesuffix(";").strip()
                static = value.startswith("static ")
                value = value.removeprefix("static ")
                if value.endswith(".*"):
                    continue
                self.unit.imports[value.split(".")[-1]] = {"module": value, "name": "", "kind": "static" if static else "class"}
            elif self.language == "go" and t == "import_declaration":
                for item in walk(node):
                    if item.type == "import_spec":
                        path = text(field(item, "path")).strip('"`')
                        alias = text(field(item, "name")) or path.split("/")[-1]
                        self.unit.imports[alias] = {"module": path, "name": "", "kind": "module"}

    def extract_definitions(self, root, owner="", scope="", exported=False):
        for node in root.named_children:
            if node.type in CLASSES:
                name = text(field(node, "name"))
                qualified = ".".join(filter(None, [owner, name]))
                self.unit.classes.append(qualified)
                if exported:
                    self.unit.exports[qualified] = {"name": qualified, "module": ""}
                self.extract_definitions(field(node, "body") or node, qualified, scope, exported)
            elif node.type in FUNCTIONS:
                name = text(field(node, "name"))
                if not name and node.parent and node.parent.type == "variable_declarator":
                    name = text(field(node.parent, "name"))
                if not name:
                    name = f"<anonymous@{node.start_point.row + 1}:{node.start_point.column + 1}>"
                receiver = field(node, "receiver")
                recv_owner = ""
                if receiver:
                    decl = next((n for n in walk(receiver) if n.type == "parameter_declaration"), None)
                    recv_owner = text(field(decl, "type")).lstrip("*")
                actual_owner = recv_owner or owner
                if node.type == "method_definition" and node.parent and node.parent.type == "object":
                    actual_owner = f"<object@{node.parent.start_point.row + 1}:{node.parent.start_point.column + 1}>"
                qualified = ".".join(filter(None, [scope, actual_owner if not scope or actual_owner.startswith('<object@') else '', name]))
                signature = ""
                if self.language == "java":
                    params = field(node, "parameters")
                    signature = "(" + ",".join(text(field(p, "type")) for p in params.named_children) + ")" if params else "()"
                symbol_id = f"{self.unit.file}::{qualified}{signature}"
                if any(s.symbol_id == symbol_id for s in self.unit.symbols):
                    symbol_id += f"@{node.start_point.row + 1}:{node.start_point.column + 1}"
                static = bool(re.search(r"\bstatic\b", text(node).split("(")[0]))
                if self.language == "python" and node.parent and node.parent.type == "decorated_definition":
                    decorators = [text(c) for c in node.parent.named_children if c.type == "decorator"]
                    static = "@staticmethod" in decorators
                symbol = Symbol(symbol_id, name, qualified, "method" if actual_owner else "function",
                                self.language, self.unit.file, node.start_point.row + 1, self.unit.module,
                                actual_owner, scope, signature, static, exported)
                if self.language == "python" and node.parent and node.parent.type == "decorated_definition":
                    if any(text(c) != "@staticmethod" for c in node.parent.named_children if c.type == "decorator"):
                        symbol.blocked.append("*")
                self.unit.symbols.append(symbol)
                self.definitions.append((symbol, node))
                body = field(node, "body")
                if body:
                    self.extract_definitions(body, actual_owner, qualified)
            else:
                named_export = node.type == "export_statement" and not any(c.type == "default" for c in node.children)
                self.extract_definitions(node, owner, scope, exported or named_export)

    def extract_bindings(self, symbol, definition):
        params = field(definition, "parameters", "parameter")
        if params:
            for p in ([params] if params.type == "identifier" else params.named_children):
                # Pattern nodes differ by grammar. Overblocking identifiers in a
                # parameter is safe; missing destructured/variadic names is not.
                symbol.blocked.extend(text(n) for n in walk(p) if n.type in {"identifier", "shorthand_property_identifier_pattern"})
        receiver = field(definition, "receiver")
        if receiver:
            decl = next((n for n in walk(receiver) if n.type == "parameter_declaration"), None)
            symbol.bindings[text(field(decl, "name"))] = symbol.owner
        # Python self/cls are not exact receiver types (subclasses may override).
        assignments = []
        body = field(definition, "body")
        if not body:
            return
        for node in walk(body, FUNCTIONS | CLASSES):
            left, right = None, None
            if node.type in {"as_pattern", "catch_clause"}:
                alias = field(node, "alias", "parameter")
                if alias:
                    symbol.blocked.extend(text(n) for n in walk(alias) if n.type == "identifier")
            if node.type in {"assignment", "assignment_statement", "assignment_expression", "augmented_assignment", "short_var_declaration"}:
                left, right = field(node, "left"), field(node, "right")
            elif node.type == "variable_declarator":
                left, right = field(node, "name"), field(node, "value")
            elif node.type in {"for_statement", "for_in_statement", "enhanced_for_statement"}:
                left = field(node, "left", "name")
            elif node.type in {"update_expression", "inc_statement", "dec_statement"}:
                left = node.named_children[0] if node.named_children else None
            if left:
                if left.type == "expression_list" and len(left.named_children) == 1:
                    left = left.named_children[0]
                names = [text(left)] if left.type == "identifier" else [text(n) for n in walk(left) if n.type == "identifier"]
                if right and right.type == "expression_list" and len(right.named_children) == 1:
                    right = right.named_children[0]
                target = ""
                if right and right.type in {"call", "new_expression", "object_creation_expression", "composite_literal"}:
                    target = text(field(right, "function", "constructor", "type"))
                ancestor = node.parent
                while ancestor and ancestor != body:
                    if ancestor.type in LOOPS | {"if_statement", "try_statement", "switch_statement", "catch_clause"}:
                        target = ""
                        break
                    ancestor = ancestor.parent
                for name in names:
                    assignments.append((name, target, node.end_byte))
        counts = Counter(a[0] for a in assignments)
        for name, target, end in assignments:
            if counts[name] == 1 and target and name not in symbol.blocked:
                symbol.bindings[name] = f"{target}@{end}"
            else:
                symbol.blocked.append(name)
        # Local imports shadow module bindings; do not treat them as module imports.
        for node in walk(body, FUNCTIONS | CLASSES):
            if node.type in {"import_statement", "import_from_statement"}:
                for n in walk(node):
                    if n.type == "identifier":
                        symbol.blocked.append(text(n))

    def structure(self, node, symbol, context):
        if node is None or node.type in FUNCTIONS | CLASSES:
            return []
        t = node.type
        if t in {"try_statement", "try_with_resources_statement"}:
            result = []
            for child in node.named_children:
                if child.type in {"except_clause", "catch_clause", "else_clause", "finally_clause"}:
                    label = "exception handler (conditional)" if child.type in {"except_clause", "catch_clause"} else "no exception" if child.type == "else_clause" else "finally"
                    result.append({"type": "guard", "condition": label,
                                   "steps": self.structure(child, symbol, {**context, "condition": label})})
                else:
                    result += self.structure(child, symbol, context)
            return result
        if t in {"switch_statement", "switch_expression", "expression_switch_statement", "type_switch_statement", "match_statement", "select_statement"}:
            condition = field(node, "condition", "value", "subject")
            result = self.structure(condition, symbol, context)
            body = field(node, "body") or node
            cases = [c for c in body.named_children if c != condition]
            for case in cases:
                label = "case selected / possible fallthrough: " + text(field(case, "value"))
                result.append({"type": "guard", "condition": label,
                               "steps": self.structure(case, symbol, {**context, "condition": label})})
            return result
        if t in {"if_statement", "elif_clause", "conditional_expression", "ternary_expression"}:
            condition = field(node, "condition")
            yes = field(node, "consequence", "body")
            no = field(node, "alternative")
            if t == "conditional_expression" and self.language == "python" and len(node.named_children) == 3:
                yes, condition, no = node.named_children
            label = text(condition)
            condition_steps = self.structure(condition, symbol, context)
            yes_steps = self.structure(yes, symbol, {**context, "condition": label})
            else_steps = []
            alternatives = node.children_by_field_name("alternative")
            if self.language == "python" and t == "if_statement" and alternatives:
                branches = [(alternative, self.structure(alternative, symbol, {**context, "condition": f"not ({label})"})) for alternative in alternatives]
                for alternative, branch in reversed(branches):
                    if alternative.type == "elif_clause" and branch:
                        branch[-1]["else_steps"] = else_steps
                    else_steps = branch
            else:
                else_steps = self.structure(no, symbol, {**context, "condition": f"not ({label})"})
            return condition_steps + [{"type": "alt", "condition": label,
                "steps": yes_steps,
                "else_steps": else_steps}]
        if t in LOOPS:
            body = field(node, "body")
            init = field(node, "initializer")
            cond = field(node, "condition", "right", "value")
            update = field(node, "update")
            # Go for_clause explicitly splits initializer/condition/update.
            clause = next((c for c in node.named_children if c.type in {"for_clause", "range_clause"}), None)
            if clause:
                init, cond, update = field(clause, "initializer"), field(clause, "condition", "right"), field(clause, "update")
            if self.language == "go" and cond is None:
                cond = next((c for c in node.named_children if c != body and c.type != "for_clause"), None)
            label = text(cond) or t.removesuffix("_statement")
            ctx = {**context, "loop": label}
            once = self.structure(init, symbol, context)
            repeated = self.structure(cond, symbol, ctx)
            if t in {"for_in_statement", "enhanced_for_statement"} or (self.language == "python" and t == "for_statement") or (clause and clause.type == "range_clause"):
                once += self.structure(cond, symbol, context)
                repeated = []
            content = self.structure(body, symbol, ctx)
            if t == "do_statement":
                repeated = content + repeated
            else:
                repeated += content
            repeated += self.structure(update, symbol, ctx)
            result = once + [{"type": "loop", "condition": label, "steps": repeated}]
            alternative = field(node, "alternative")
            if alternative:
                result.append({"type": "guard", "condition": "loop completes without break", "steps": self.structure(alternative, symbol, context)})
            return result
        if t in {"boolean_operator", "binary_expression"}:
            operator = text(field(node, "operator"))
            if not operator:
                operator = next((text(c) for c in node.children if not c.is_named and text(c) in {"&&", "||", "??"}), "")
            if operator in {"and", "or", "&&", "||", "??"}:
                left, right = field(node, "left"), field(node, "right")
                cond = f"{text(left)} {'truthy' if operator in {'and', '&&'} else 'nullish' if operator == '??' else 'falsy'}"
                return self.structure(left, symbol, context) + [{"type": "guard", "condition": cond,
                    "steps": self.structure(right, symbol, {**context, "condition": cond})}]
        if t in {"await", "await_expression", "go_statement", "defer_statement"}:
            key = "await" if t.startswith("await") else "async" if t == "go_statement" else "deferred"
            result = []
            for c in node.named_children:
                result += self.structure(c, symbol, {**context, key: True})
            return result
        if t in CALLS:
            result = []
            target_node = field(node, "function", "constructor", "type")
            if t == "method_invocation":
                obj = field(node, "object")
                target = ".".join(filter(None, [text(obj), text(field(node, "name"))]))
            else:
                target = text(target_node)
            # Receiver and arguments are evaluated before the outer call.
            for child in node.named_children:
                result += self.structure(child, symbol, {k: v for k, v in context.items() if k not in {"await", "async", "deferred"}})
            order = 1 + sum(c.caller == symbol.symbol_id for c in self.unit.calls)
            cid = (f"{symbol.symbol_id}#call:{node.start_point.row + 1}:{node.start_point.column + 1}"
                   f"-{node.end_point.row + 1}:{node.end_point.column + 1}")
            ctx = {**context, "byte": node.start_byte}
            if t in {"new_expression", "object_creation_expression"}:
                ctx["constructor"] = True
            call = Call(cid, symbol.symbol_id, text(node), target, self.unit.file,
                        node.start_point.row + 1, node.start_point.column + 1,
                        node.end_point.row + 1, node.end_point.column + 1, order, ctx)
            if node.has_error or "*" in symbol.blocked:
                call.reason = "syntax error in enclosing definition"
                call.context["invalid"] = True
            self.unit.calls.append(call)
            result.append({"type": "call", "call_id": cid})
            return result
        if t in {"return_statement", "raise_statement", "throw_statement", "break_statement", "continue_statement"}:
            result = []
            for c in node.named_children:
                result += self.structure(c, symbol, context)
            return result + [{"type": "exit", "label": t.removesuffix("_statement")}]
        result = []
        children = node.named_children
        for i, child in enumerate(children):
            result += self.structure(child, symbol, context)
            if child.type in {"return_statement", "raise_statement", "throw_statement", "break_statement", "continue_statement"}:
                break
            if child.type in LOOPS | {"if_statement", "try_statement", "switch_statement", "match_statement"} and any(n.type in {"return_statement", "raise_statement", "throw_statement", "break_statement", "continue_statement"} for n in walk(child, FUNCTIONS | CLASSES)):
                rest = []
                for other in children[i + 1:]:
                    rest += self.structure(other, symbol, context)
                    if other.type in {"return_statement", "raise_statement", "throw_statement", "break_statement", "continue_statement"}:
                        break
                if rest:
                    result.append({"type": "guard", "condition": "previous branch did not exit", "steps": rest})
                break
        return result


def parse_source(file: str, language: str, source: bytes) -> SourceUnit:
    return Adapter(language, file).parse(source)
