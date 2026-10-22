import json
from pathlib import Path

out = Path('/Users/karlofamoso/Documents/vscode files/ByaHero/graphify-out')

ast = json.loads((out / '.graphify_ast.json').read_text(encoding='utf-8'))
sem = json.loads((out / '.graphify_semantic.json').read_text(encoding='utf-8'))

for n in sem['nodes']:
    n.setdefault('_origin', 'semantic')
for e in sem['edges']:
    e.setdefault('_origin', 'semantic')

seen = {n['id'] for n in ast['nodes']}
merged_nodes = list(ast['nodes'])
for n in sem['nodes']:
    if n['id'] not in seen:
        merged_nodes.append(n)
        seen.add(n['id'])

merged_edges = ast['edges'] + sem['edges']
merged = {
    'nodes': merged_nodes,
    'edges': merged_edges,
    'hyperedges': sem.get('hyperedges', []),
    'input_tokens': sem.get('input_tokens', 0),
    'output_tokens': sem.get('output_tokens', 0),
}
(out / '.graphify_extract.json').write_text(
    json.dumps(merged, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'Merged: {len(merged_nodes)} nodes, {len(merged_edges)} edges '
      f'({len(ast["nodes"])} AST + {len(sem["nodes"])} semantic)')
