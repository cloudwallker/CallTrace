"""Black-box safety regressions: source text is analyzed, never executed."""
import textwrap

import pytest

from calltrace.core.analyzer import analyze
from calltrace.core.resolution import select_entry
from calltrace.core.sequence import build_sequence


def inspect_project(tmp_path, files, entry="main"):
    for name, source in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")
    project = analyze(tmp_path)
    assert not project.diagnostics, project.diagnostics
    symbol = select_entry(project, entry)
    calls = sorted((c for c in project.calls.values() if c.caller == symbol.symbol_id), key=lambda c: c.order)
    return project, symbol, calls


def named_call(calls, target):
    found = [call for call in calls if call.target == target]
    assert len(found) == 1, [(c.target, c.resolution) for c in calls]
    return found[0]


@pytest.mark.parametrize("file,source,entry,target", [
    ("a.py", "def leaf(): pass\ndef main(leaf):\n    leaf()", "main", "leaf"),
    ("a.js", "function leaf(){} function main(leaf){leaf();}", "main", "leaf"),
    ("a.ts", "function leaf(){} function main(leaf: ()=>void){leaf();}", "main", "leaf"),
    ("A.java", "class B { static void leaf(){} } class A { static void main(B B){B.leaf();} }", "A.main", "B.leaf"),
    ("a.go", "package demo\nfunc leaf(){}\nfunc main(leaf func()){leaf()}", "main", "leaf"),
    ("a.go", "package demo\nfunc leaf(){}\nfunc main(other, leaf func()){leaf()}", "main", "leaf"),
    ("a.py", "def leaf(): pass\ndef main(*leaf):\n    leaf()", "main", "leaf"),
    ("a.js", "function leaf(){} function main({leaf}){leaf();}", "main", "leaf"),
])
def test_parameters_never_resolve_to_shadowed_declarations(tmp_path, file, source, entry, target):
    _, _, calls = inspect_project(tmp_path, {file: source}, entry)
    call = named_call(calls, target)
    assert call.resolution != "exact"
    assert call.callee is None


@pytest.mark.parametrize("file,source,entry,target", [
    ("a.py", "def leaf(): pass\ndef main(other):\n    leaf = other\n    leaf()", "main", "leaf"),
    ("a.js", "function leaf(){} function main(other){leaf = other; leaf();}", "main", "leaf"),
    ("a.ts", "function leaf(){} function main(other: ()=>void){leaf = other; leaf();}", "main", "leaf"),
    ("A.java", "class B {void leaf(){}} class A {static void main(B other){B b=new B(); b=other; b.leaf();}}", "A.main", "b.leaf"),
    ("a.go", "package demo\nfunc leaf(){}\nfunc main(other func()){leaf:=func(){}; leaf=other; leaf()}", "main", "leaf"),
])
def test_reassignment_invalidates_exact_binding(tmp_path, file, source, entry, target):
    _, _, calls = inspect_project(tmp_path, {file: source}, entry)
    assert named_call(calls, target).resolution != "exact"


@pytest.mark.parametrize("extension", ["js", "ts"])
def test_conditional_assignment_does_not_prove_receiver(tmp_path, extension):
    source = "class A {leaf(){}} function main(flag){if(flag){var a=new A();} a.leaf();}"
    _, _, calls = inspect_project(tmp_path, {"a." + extension: source})
    assert named_call(calls, "a.leaf").resolution != "exact"


def test_python_conditional_assignment_does_not_prove_receiver(tmp_path):
    _, _, calls = inspect_project(tmp_path, {"a.py": "class A:\n    def leaf(self): pass\ndef main(flag):\n    if flag:\n        a = A()\n    a.leaf()"})
    assert named_call(calls, "a.leaf").resolution != "exact"


@pytest.mark.parametrize("files,entry,target", [
    ({"a.py": "from external import leaf\ndef main(): leaf()", "b.py": "def leaf(): pass"}, "main", "leaf"),
    ({"a.js": "import {leaf} from 'external'; function main(){leaf();}", "b.js": "export function leaf(){}"}, "main", "leaf"),
    ({"a.ts": "import {leaf} from 'external'; function main(){leaf();}", "b.ts": "export function leaf(){}"}, "main", "leaf"),
    ({"A.java": "import outside.B; class A {static void main(){B.leaf();}}", "B.java": "class B {static void leaf(){}}"}, "A.main", "B.leaf"),
    ({"a.go": 'package demo\nimport "outside/helper"\nfunc main(){helper.Leaf()}', "helper/b.go": "package helper\nfunc Leaf(){}"}, "main", "helper.Leaf"),
])
def test_external_import_never_uses_project_name_coincidence(tmp_path, files, entry, target):
    _, _, calls = inspect_project(tmp_path, files, entry)
    assert named_call(calls, target).resolution != "exact"


def test_python_custom_decorator_may_replace_function(tmp_path):
    _, _, calls = inspect_project(tmp_path, {"a.py": "def replace(fn):\n    return lambda: None\n@replace\ndef leaf(): pass\ndef main(): leaf()"})
    assert named_call(calls, "leaf").resolution != "exact"


@pytest.mark.parametrize("extension", ["js", "ts"])
def test_explicit_export_list_resolves_local_function(tmp_path, extension):
    files = {"a." + extension: "import {run} from './b'; function main(){run();}",
             "b." + extension: "function leaf(){} export {leaf as run};"}
    project, _, calls = inspect_project(tmp_path, files)
    call = named_call(calls, "run")
    assert call.resolution == "exact"
    assert project.symbols[call.callee].name == "leaf"


@pytest.mark.parametrize("extension", ["js", "ts"])
def test_explicit_reexport_resolves_original_function(tmp_path, extension):
    files = {"a." + extension: "import {run} from './b'; function main(){run();}",
             "b." + extension: "export {leaf as run} from './c';",
             "c." + extension: "export function leaf(){}"}
    project, _, calls = inspect_project(tmp_path, files)
    call = named_call(calls, "run")
    assert call.resolution == "exact"
    assert project.symbols[call.callee].file == "c." + extension


def test_go_local_module_import(tmp_path):
    project, _, calls = inspect_project(tmp_path, {
        "go.mod": "module example.test/app\ngo 1.22\n",
        "main.go": 'package main\nimport h "example.test/app/helper"\nfunc main(){h.Leaf()}',
        "helper/leaf.go": "package helper\nfunc Leaf(){}",
    })
    call = named_call(calls, "h.Leaf")
    assert call.resolution == "exact"
    assert project.symbols[call.callee].file == "helper/leaf.go"


def test_java_overload_stays_ambiguous(tmp_path):
    _, _, calls = inspect_project(tmp_path, {"A.java": "class A {static void leaf(int x){} static void leaf(String x){} static void main(){leaf(1);}}"}, "A.main")
    call = named_call(calls, "leaf")
    assert call.resolution != "exact"
    assert len(call.candidates) == 2


@pytest.mark.parametrize("file,source,entry,target", [
    ("A.java", "class B {void leaf(){}} class A {static void main(){B b=new B(); b.leaf();}}", "A.main", "b.leaf"),
    ("a.go", "package demo\ntype B struct{}\nfunc(b B) Leaf(){}\nfunc main(){b:=B{}; b.Leaf()}", "main", "b.Leaf"),
    ("a.go", "package demo\ntype B struct{}\nfunc(b B) Leaf(){}\nfunc(b B) main(){b.Leaf()}", "B.main", "b.Leaf"),
])
def test_concrete_instance_method_is_exact(tmp_path, file, source, entry, target):
    _, _, calls = inspect_project(tmp_path, {file: source}, entry)
    assert named_call(calls, target).resolution == "exact"


@pytest.mark.parametrize("file,source,entry", [
    ("a.py", "class A:\n    def method(self, n): pass\ndef f(): return A()\ndef g(): return 1\ndef main(): f().method(g())", "main"),
    ("a.js", "function f(){return {method(n){}};} function g(){return 1;} function main(){f().method(g());}", "main"),
    ("a.ts", "function f(){return {method(n: number){}};} function g(){return 1;} function main(){f().method(g());}", "main"),
    ("A.java", "class A {static A f(){return new A();} static int g(){return 1;} void method(int n){} static void main(){f().method(g());}}", "A.main"),
    ("a.go", "package demo\ntype A struct{}\nfunc f() A{return A{}}\nfunc g() int{return 1}\nfunc(a A) method(n int){}\nfunc main(){f().method(g())}", "main"),
])
def test_receiver_and_argument_calls_precede_outer_call(tmp_path, file, source, entry):
    project, symbol, calls = inspect_project(tmp_path, {file: source}, entry)
    assert [c.target for c in calls] == ["f", "g", "f().method"]
    assert calls[-1].resolution != "exact"
    _, sequence, _ = build_sequence(project, symbol, 1)
    assert [step["call_id"] for step in sequence["steps"]] == [c.call_id for c in calls]


@pytest.mark.parametrize("file,source", [
    ("a.py", "def first(): pass\ndef second(): pass\ndef main(): first() and second()"),
    ("a.js", "function first(){} function second(){} function main(){first() && second();}"),
    ("a.ts", "function first(){} function second(){} function main(){first() && second();}"),
])
def test_short_circuit_rhs_is_guarded(tmp_path, file, source):
    project, symbol, _ = inspect_project(tmp_path, {file: source})
    _, sequence, _ = build_sequence(project, symbol, 1)
    assert [s["type"] for s in sequence["steps"]] == ["call", "guard"]
    assert sequence["steps"][1]["steps"][0]["method"] == "second"


def test_loop_calls_remain_in_loop_and_following_call_is_guarded_by_return(tmp_path):
    source = "def check(): pass\ndef body(): pass\ndef tail(): pass\ndef main(flag):\n    while check():\n        body()\n    if flag:\n        return\n    tail()"
    project, symbol, _ = inspect_project(tmp_path, {"a.py": source})
    _, sequence, _ = build_sequence(project, symbol, 1)
    loop, branch, guarded = sequence["steps"]
    assert loop["type"] == "loop"
    assert [s["method"] for s in loop["steps"]] == ["check", "body"]
    assert branch["type"] == "alt"
    assert guarded["type"] == "guard"
    assert guarded["steps"][0]["method"] == "tail"


def test_unconditional_return_omits_unreachable_call(tmp_path):
    project, symbol, calls = inspect_project(tmp_path, {"a.py": "def leaf(): pass\ndef main():\n    return\n    leaf()"})
    assert calls == []
    graph, _, _ = build_sequence(project, symbol, 1)
    assert graph["edges"] == []


def test_constructor_assignment_shadows_bare_function_name(tmp_path):
    _, _, calls = inspect_project(tmp_path, {"a.py": "def leaf(): pass\nclass Callable:\n    def __call__(self): pass\ndef main():\n    leaf = Callable()\n    leaf()"})
    assert named_call(calls, "leaf").resolution != "exact"


def test_enclosing_parameter_shadows_module_function_for_closure(tmp_path):
    _, _, calls = inspect_project(tmp_path, {"a.py": "def leaf(): pass\ndef outer(leaf):\n    def main():\n        leaf()\n    return main"}, "outer.main")
    assert named_call(calls, "leaf").resolution != "exact"


def test_javascript_module_variable_replaces_function_declaration(tmp_path):
    _, _, calls = inspect_project(tmp_path, {"a.js": "function leaf(){} var leaf = external; function main(){leaf();}"})
    assert named_call(calls, "leaf").resolution != "exact"


def test_object_literal_method_is_not_module_function(tmp_path):
    _, _, calls = inspect_project(tmp_path, {"a.js": "const obj = {leaf(){}}; function main(){leaf();}"})
    assert named_call(calls, "leaf").resolution != "exact"


def test_go_import_does_not_expose_private_package_function(tmp_path):
    _, _, calls = inspect_project(tmp_path, {
        "go.mod": "module example.test/app\ngo 1.22\n",
        "main.go": 'package main\nimport "example.test/app/helper"\nfunc main(){helper.leaf()}',
        "helper/leaf.go": "package helper\nfunc leaf(){}",
    })
    assert named_call(calls, "helper.leaf").resolution != "exact"


def test_exception_handler_is_not_an_unconditional_next_call(tmp_path):
    project, symbol, _ = inspect_project(tmp_path, {"a.py": "def work(): pass\ndef recover(): pass\ndef main():\n    try:\n        work()\n    except Exception:\n        recover()"})
    _, sequence, _ = build_sequence(project, symbol, 1)
    # Unsupported constructs may be diagnosed or kept as conditional groups,
    # but must not claim the handler always runs after the successful call.
    direct = [s["method"] for s in sequence["steps"] if s["type"] == "call"]
    assert "recover" not in direct


def test_switch_cases_are_not_unconditional_sequential_calls(tmp_path):
    project, symbol, _ = inspect_project(tmp_path, {"a.js": "function first(){} function second(){} function main(x){switch(x){case 1: first(); break; default: second();}}"})
    _, sequence, _ = build_sequence(project, symbol, 1)
    direct = [s["method"] for s in sequence["steps"] if s["type"] == "call"]
    assert "first" not in direct and "second" not in direct


def test_return_inside_loop_guards_following_call(tmp_path):
    project, symbol, _ = inspect_project(tmp_path, {"a.py": "def tail(): pass\ndef main(flag):\n    while flag:\n        return\n    tail()"})
    _, sequence, _ = build_sequence(project, symbol, 1)
    direct = [s["method"] for s in sequence["steps"] if s["type"] == "call"]
    assert "tail" not in direct
