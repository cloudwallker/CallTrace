"""Render the sequence IR without consulting the source project."""

import re


def _escape(value):
    # Mermaid numeric entities prevent source text becoming diagram syntax.
    escapes = {'#': '#35;', '&': '#38;', ';': '#59;', '<': '#60;', '>': '#62;',
               '"': '#34;', "'": '#39;', ':': '#58;', '\\': '#92;', '`': '#96;',
               '{': '#123;', '}': '#125;', '|': '#124;', '%': '#37;'}
    text = ''.join(' ' if c.isspace() else escapes.get(c, c) for c in str(value))
    # A bare "end" can be interpreted as a block terminator in label positions.
    return re.sub(r'\bend\b', '#101;nd', text)


def render_mermaid(sequence: dict) -> str:
    participants = sequence['participants']
    ids = {p['id']: f'p{i}' for i, p in enumerate(participants)}
    lines = ['sequenceDiagram']
    for p in participants:
        lines.append(f"    participant {ids[p['id']]} as {_escape(p['label'])}")
    default = ids.get(sequence.get('entry'), next(iter(ids.values()), 'p0'))

    def walk(steps, indent=1):
        pad = '    ' * indent
        for node in steps:
            kind = node['type']
            if kind == 'call':
                context = node.get('context', {})
                markers = [key for key in ('await', 'async', 'go', 'defer', 'deferred') if context.get(key)]
                if node.get('resolution') != 'exact':
                    markers.append(node.get('resolution', 'unresolved'))
                label = node.get('expression') or node.get('method', '')
                if markers:
                    label = f"[{', '.join(markers)}] {label}"
                target = ids[node['to']]
                lines.append(f"{pad}{ids[node['from']]}->>{target}: {_escape(label)}")
                if node.get('recursive'):
                    lines.append(f'{pad}Note over {target}: recursive call / 递归停止展开')
                elif node.get('truncated'):
                    lines.append(f'{pad}Note over {target}: depth limit / 深度边界')
                walk(node.get('steps', []), indent)
            elif kind in ('alt', 'loop', 'guard'):
                keyword = 'opt' if kind == 'guard' else kind
                lines.append(f"{pad}{keyword} {_escape(node.get('condition', ''))}")
                walk(node.get('steps', []), indent + 1)
                if kind == 'alt' and node.get('else_steps'):
                    lines.append(f'{pad}else otherwise')
                    walk(node['else_steps'], indent + 1)
                lines.append(f'{pad}end')
            elif kind in ('exit', 'note'):
                target = ids.get(node.get('participant'), default)
                lines.append(f"{pad}Note over {target}: {_escape(node.get('label', kind))}")

    walk(sequence['steps'])
    return '\n'.join(lines) + '\n'
