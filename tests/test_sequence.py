from hashlib import sha256
from pathlib import Path

import pytest

from calltrace.core.models import Call, Project, SourceUnit, Symbol
from calltrace.core.render import render_mermaid as _render_mermaid


def render_mermaid(sequence):
    """Keep the actual renderer output for independent Mermaid parser checks."""
    rendered = _render_mermaid(sequence)
    directory = Path(__file__).resolve().parents[1] / 'artifacts' / 'mermaid'
    directory.mkdir(parents=True, exist_ok=True)
    digest = sha256(rendered.encode('utf-8')).hexdigest()
    (directory / f'sequence-{digest}.mmd').write_text(rendered, encoding='utf-8')
    return rendered


def sample():
    a = Symbol('a', 'a', 'pkg.a', 'function', 'python', 'x.py', 1)
    b = Symbol('b', 'b', 'pkg.b', 'function', 'python', 'x.py', 10)
    calls = [
        Call('ab1', 'a', 'b()', 'b', 'x.py', 2, 0, 2, 3, 0, callee='b', resolution='exact'),
        Call('ab2', 'a', 'b()', 'b', 'x.py', 3, 0, 3, 3, 1, callee='b', resolution='exact'),
        Call('ba', 'b', 'a()', 'a', 'x.py', 11, 0, 11, 3, 0, callee='a', resolution='exact'),
        Call('unknown', 'b', 'external()', 'external', 'x.py', 12, 0, 12, 10, 1),
    ]
    a.body = [{'type': 'call', 'call_id': 'ab1'}, {'type': 'call', 'call_id': 'ab2'}]
    b.body = [{'type': 'call', 'call_id': 'ba'}, {'type': 'call', 'call_id': 'unknown'}]
    return Project([SourceUnit('x.py', 'python', 'pkg', [a, b], calls)]), a


def test_depth_zero_and_one_do_not_leak_transitive_calls():
    from calltrace.core.sequence import build_sequence
    project, entry = sample()
    graph, sequence, unresolved = build_sequence(project, entry, 0)
    assert [s['symbol_id'] for s in graph['symbols']] == ['a']
    assert graph['edges'] == sequence['steps'] == unresolved['calls'] == []
    graph, sequence, unresolved = build_sequence(project, entry, 1)
    assert [c['call_id'] for c in graph['edges']] == ['ab1', 'ab2']
    assert [s['call_id'] for s in sequence['steps']] == ['ab1', 'ab2']
    assert all(s['truncated'] and not s['steps'] for s in sequence['steps'])
    assert unresolved['calls'] == []


def test_path_recursion_retains_repeated_calls_and_unique_graph_edges():
    from calltrace.core.sequence import build_sequence
    project, entry = sample()
    graph, sequence, unresolved = build_sequence(project, entry, 5)
    assert len(graph['edges']) == 4
    assert [s['steps'][0]['recursive'] for s in sequence['steps']] == [True, True]
    assert [s['steps'][1]['to'] for s in sequence['steps']] == ['unresolved', 'unresolved']
    assert [p['id'] for p in sequence['participants']] == ['a', 'b', 'unresolved']
    assert [c['call_id'] for c in unresolved['calls']] == ['unknown']
    assert all(doc['schema_version'] == '0.1' for doc in (graph, sequence, unresolved))


def test_heuristic_is_visible_but_never_expanded():
    from calltrace.core.sequence import build_sequence
    project, entry = sample()
    project.units[0].calls[0].resolution = 'heuristic'
    _, sequence, _ = build_sequence(project, entry, 4)
    assert sequence['steps'][0]['resolution'] == 'heuristic'
    assert sequence['steps'][0]['steps'] == []


def test_control_flow_rendering_escapes_labels_and_preserves_context():
    from calltrace.core.sequence import build_sequence
    project, entry = sample()
    entry.qualified_name = 'a;\nparticipant Evil as <img>'
    project.units[0].calls[0].context = {'await': True, 'async': True}
    entry.body = [{'type': 'alt', 'condition': 'x < 2', 'steps': [
        {'type': 'loop', 'condition': 'items', 'steps': [{'type': 'call', 'call_id': 'ab1'}]}
    ], 'else_steps': [{'type': 'exit', 'label': 'return early'}]},
        {'type': 'guard', 'condition': 'continuing', 'steps': [{'type': 'note', 'label': 'done'}]}]
    _, sequence, _ = build_sequence(project, entry, 1)
    text = render_mermaid(sequence)
    assert text.startswith('sequenceDiagram\n')
    assert '\nparticipant Evil' not in text
    assert '<img>' not in text
    assert 'p0->>p1:' in text
    assert 'await' in text and 'async' in text
    assert 'alt ' in text and 'loop items' in text and 'opt continuing' in text
    assert 'else' in text and 'return early' in text
    assert 'depth' in text.lower()
    assert '-->>' not in text


def test_negative_depth_is_rejected():
    from calltrace.core.sequence import build_sequence
    project, entry = sample()
    with pytest.raises(ValueError, match='depth'):
        build_sequence(project, entry, -1)


def test_unresolved_and_recursion_render_without_fabricated_returns():
    from calltrace.core.sequence import build_sequence
    project, entry = sample()
    _, sequence, _ = build_sequence(project, entry, 5)
    text = render_mermaid(sequence)
    assert 'participant p2 as unresolved / 未解析' in text
    assert text.count('p1->>p2: [unresolved] external()') == 2
    assert text.count('recursive call') == 2
    assert '-->>' not in text


def test_documents_are_stable_and_do_not_mutate_project():
    from copy import deepcopy
    from calltrace.core.sequence import build_sequence
    project, entry = sample()
    original = deepcopy(project)
    first = build_sequence(project, entry, 3)
    project.units[0].calls.reverse()
    second = build_sequence(project, entry, 3)
    assert first == second
    project.units[0].calls.reverse()
    assert project == original
    first[1]['steps'][0]['context']['await'] = True
    assert project.calls['ab1'].context == {}


def test_graph_preserves_callsite_resolution_evidence():
    from calltrace.core.sequence import build_sequence
    project, entry = sample()
    call = project.calls['ab1']
    call.confidence = 1.0
    call.rule = 'same-module'
    call.reason = 'one lexical target'
    call.candidates = ['b']
    graph, sequence, _ = build_sequence(project, entry, 1)
    edge = graph['edges'][0]
    assert edge == {
        'call_id': 'ab1', 'caller': 'a', 'expression': 'b()', 'target': 'b',
        'file': 'x.py', 'line': 2, 'column': 0, 'end_line': 2, 'end_column': 3,
        'order': 0, 'context': {}, 'callee': 'b', 'resolution': 'exact',
        'confidence': 1.0, 'rule': 'same-module', 'reason': 'one lexical target',
        'candidates': ['b'],
    }
    assert sequence['steps'][0]['call_id'] == edge['call_id']
    assert all('body' not in symbol for symbol in graph['symbols'])


@pytest.mark.parametrize('depth, expected_edges', [(1, ['ab1']), (2, ['ab1', 'bc']), (3, ['ab1', 'bc', 'cd'])])
def test_depth_counts_calls_not_control_blocks(depth, expected_edges):
    from calltrace.core.sequence import build_sequence
    project, entry = sample()
    unit = project.units[0]
    b = project.symbols['b']
    c = Symbol('c', 'c', 'pkg.c', 'function', 'python', 'x.py', 20)
    d = Symbol('d', 'd', 'pkg.d', 'function', 'python', 'x.py', 30)
    unit.symbols.extend([c, d])
    unit.calls = [unit.calls[0],
                  Call('bc', 'b', 'c()', 'c', 'x.py', 11, 0, 11, 3, 0, callee='c', resolution='exact'),
                  Call('cd', 'c', 'd()', 'd', 'x.py', 21, 0, 21, 3, 0, callee='d', resolution='exact')]
    entry.body = [{'type': 'loop', 'condition': 'items', 'steps': [entry.body[0]]}]
    b.body = [{'type': 'call', 'call_id': 'bc'}]
    c.body = [{'type': 'call', 'call_id': 'cd'}]
    graph, sequence, _ = build_sequence(project, entry, depth)
    assert [edge['call_id'] for edge in graph['edges']] == expected_edges
    node = sequence['steps'][0]['steps'][0]
    for _ in range(depth - 1):
        assert not node['truncated']
        node = node['steps'][0]
    assert node['steps'] == []
    assert node['truncated'] is (depth < 3)


def test_mutual_recursion_is_a_path_boundary_not_global_visited_state():
    from calltrace.core.sequence import build_sequence
    project, entry = sample()
    _, sequence, _ = build_sequence(project, entry, 20)
    for node in sequence['steps']:
        assert node['to'] == 'b'
        backedge = node['steps'][0]
        assert (backedge['from'], backedge['to']) == ('b', 'a')
        assert backedge['recursive'] is True
        assert backedge['truncated'] is False
        assert backedge['steps'] == []


def test_deferred_context_is_visible_on_unresolved_call():
    from calltrace.core.sequence import build_sequence
    project, entry = sample()
    project.calls['unknown'].context = {'deferred': True}
    _, sequence, _ = build_sequence(project, entry, 2)
    assert '[deferred, unresolved] external()' in render_mermaid(sequence)


@pytest.mark.parametrize('label, escaped', [
    ('end', '#101;nd'), ('end work', '#101;nd work'),
    ('x %% hidden', 'x #37;#37; hidden'), ('x\ny\rz', 'x y z'),
    ('x:y', 'x#58;y'),
])
def test_all_source_labels_escape_mermaid_tokens(label, escaped):
    sequence = {'entry': 'a', 'participants': [{'id': 'a', 'label': label}],
                'steps': [{'type': 'loop', 'condition': label, 'steps': [
                    {'type': 'note', 'participant': 'a', 'label': label},
                    {'type': 'call', 'from': 'a', 'to': 'a', 'expression': label, 'resolution': 'exact'}]}]}
    rendered = render_mermaid(sequence)
    assert rendered.splitlines() == [
        'sequenceDiagram', f'    participant p0 as {escaped}',
        f'    loop {escaped}', f'        Note over p0: {escaped}',
        f'        p0->>p0: {escaped}', '    end',
    ]
