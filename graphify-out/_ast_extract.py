import json
from pathlib import Path
from graphify.extract import collect_files, extract

root = Path('/Users/karlofamoso/Documents/vscode files/ByaHero')
out = root / 'graphify-out'

detect = json.loads((out / '.graphify_detect.json').read_text(encoding='utf-8'))

code_files = []
for f in detect.get('files', {}).get('code', []):
    p = Path(f)
    code_files.extend(collect_files(p) if p.is_dir() else [p])

if code_files:
    result = extract(code_files, cache_root=root, root=root)
    (out / '.graphify_ast.json').write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'AST: {len(result["nodes"])} nodes, {len(result["edges"])} edges')
    for n in result['nodes'][:15]:
        print('  NODE', n['id'])
else:
    (out / '.graphify_ast.json').write_text(
        json.dumps({'nodes': [], 'edges': [], 'input_tokens': 0, 'output_tokens': 0}, ensure_ascii=False),
        encoding='utf-8')
    print('No code files - skipping AST extraction')
