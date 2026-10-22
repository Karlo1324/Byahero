import json
from pathlib import Path
from graphify.cache import check_semantic_cache

root = Path('/Users/karlofamoso/Documents/vscode files/ByaHero')
out = root / 'graphify-out'
spec = '/Users/karlofamoso/.claude/skills/graphify/references/extraction-spec.md'

detect = json.loads((out / '.graphify_detect.json').read_text(encoding='utf-8'))
all_files = [f for cat in ('document', 'paper', 'image') for f in detect['files'].get(cat, [])]

cn, ce, ch, uncached = check_semantic_cache(all_files, root=str(root), prompt_file=spec)

if cn or ce or ch:
    (out / '.graphify_cached.json').write_text(
        json.dumps({'nodes': cn, 'edges': ce, 'hyperedges': ch}, ensure_ascii=False), encoding='utf-8')
else:
    (out / '.graphify_cached.json').unlink(missing_ok=True)

(out / '.graphify_uncached.txt').write_text('\n'.join(uncached), encoding='utf-8')
for stale in out.glob('.graphify_chunk_*.json'):
    stale.unlink()

print(f'Cache: {len(all_files) - len(uncached)} hit, {len(uncached)} need extraction')
for u in uncached:
    print('  UNCACHED', u)
