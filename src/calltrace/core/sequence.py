"""Build bounded, evidence-backed call graph and sequence documents."""

from copy import deepcopy
from dataclasses import asdict

from .models import Project, Symbol, public_symbol


def build_sequence(project: Project, entry: Symbol, depth: int) -> tuple[dict, dict, dict]:
    if depth < 0:
        raise ValueError('depth must be non-negative')
    symbols, calls = project.symbols, project.calls
    visited_symbols = {entry.symbol_id: entry}
    visited_calls = {}
    participants = {}

    def participant(symbol_id):
        if symbol_id not in participants:
            label = symbols[symbol_id].qualified_name if symbol_id in symbols else 'unresolved / 未解析'
            participants[symbol_id] = {'id': symbol_id, 'label': label}

    participant(entry.symbol_id)

    def walk(body, owner, remaining, path):
        result = []
        for item in body:
            kind = item['type']
            if kind == 'call':
                call = calls[item['call_id']]
                visited_calls[call.call_id] = call
                callee = symbols.get(call.callee)
                target = callee.symbol_id if callee else 'unresolved'
                participant(target)
                if callee:
                    visited_symbols[target] = callee
                expandable = call.resolution == 'exact' and callee is not None
                recursive = bool(expandable and target in path)
                truncated = bool(expandable and remaining <= 1 and callee.body and not recursive)
                node = {
                    'type': 'call', 'call_id': call.call_id,
                    'from': owner, 'to': target,
                    'method': callee.name if callee else call.target,
                    'expression': call.expression, 'resolution': call.resolution,
                    'context': deepcopy(call.context), 'recursive': recursive,
                    'truncated': truncated, 'steps': [],
                }
                if expandable and not recursive and remaining > 1:
                    node['steps'] = walk(callee.body, target, remaining - 1, path | {target})
                result.append(node)
            elif kind in ('alt', 'loop', 'guard'):
                node = {'type': kind, 'condition': item.get('condition', ''),
                        'steps': walk(item.get('steps', []), owner, remaining, path)}
                if kind == 'alt':
                    node['else_steps'] = walk(item.get('else_steps', []), owner, remaining, path)
                result.append(node)
            elif kind in ('exit', 'note'):
                result.append({'type': kind, 'label': item.get('label', ''), 'participant': owner})
        return result

    steps = walk(entry.body, entry.symbol_id, depth, {entry.symbol_id}) if depth else []
    edges = [asdict(call) for call in sorted(visited_calls.values(),
             key=lambda c: (c.file, c.line, c.column, c.order, c.call_id))]
    common = {'schema_version': '0.1', 'entry': entry.symbol_id, 'depth': depth}
    graph = {**common, 'symbols': [public_symbol(visited_symbols[k]) for k in sorted(visited_symbols)],
             'edges': edges, 'diagnostics': deepcopy(project.diagnostics)}
    sequence = {**common, 'participants': list(participants.values()), 'steps': steps}
    unresolved = {**common, 'calls': [deepcopy(call) for call in edges if call['resolution'] == 'unresolved']}
    return graph, sequence, unresolved
