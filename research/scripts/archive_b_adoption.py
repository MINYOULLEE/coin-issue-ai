"""Create a verified, content-addressed LOCAL research backup; never upload or trade.

Includes all research datasets/results/scripts, adopted standards and current B source.
Existing dirty research is included as a workspace snapshot, not a claim of reviewed code.
No credentials, environment files, git internals or Supabase temp directories are included.
"""
import hashlib,json,zipfile
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'research/results/b_sparse_stage20/ADOPTION_MANIFEST.json'

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    files=set()
    for folder in ('research/data','research/scripts','research/results'):
        for path in (ROOT/folder).rglob('*'):
            if path.is_file() and path.suffix in ('.csv','.json','.py','.mjs','.cjs','.md','.txt') and path!=OUT:
                files.add(path)
    files.update((ROOT/'strategy').rglob('*.json'))
    files.update((ROOT/'strategy').glob('*.md'))
    files.add(ROOT/'AGENTS.md')
    files.add(ROOT/'docs/index.html')
    files.add(ROOT/'docs/plan-controls.js')
    files.update((ROOT/'supabase/repairs').glob('plan_b_stage26*.sql'))
    files.add(ROOT/'supabase/repairs/test_plan_b_stage26_rollback.sql')
    files.add(ROOT/'supabase/functions/coin-collector/answer_trees.ts')
    for folder in ('supabase/functions/_shared','supabase/functions/plan-b-executor','supabase/functions/plan-b-strategy','supabase/functions/plan-b-account-read'):
        for path in (ROOT/folder).rglob('*'):
            if path.is_file() and path.suffix in ('.json','.ts','.mjs'):
                files.add(path)
    records=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=digest(p)) for p in sorted(files)]
    content_id=hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest()
    archive=ROOT/'research/archives'/f'b_stage26_20260831_{content_id[:16]}.zip'
    archive.parent.mkdir(parents=True,exist_ok=True)
    if not archive.exists():
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for item in records:
                z.write(ROOT/item['path'],item['path'])
            z.writestr('ARCHIVE_CONTENTS.json',json.dumps(records,indent=2))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for item in records:
            assert hashlib.sha256(z.read(item['path'])).hexdigest()==item['sha256'],item['path']
    manifest=dict(created_at=datetime.now(timezone.utc).isoformat(),adopted_version='b_core_sparse_stage26_v1',
        archive_path=archive.relative_to(ROOT).as_posix(),archive_bytes=archive.stat().st_size,archive_sha256=digest(archive),
        source_set_sha256=content_id,files=records,verified=True,
        storage='Local workspace ZIP; raw datasets and ZIP are git-ignored, not a cloud backup',
        status='Stage26 core runtime deployed; consult B_STAGE26_ROLLOUT_20260831.md for contract alignment and Telegram approval blockers; owner switches unchanged',
        scope='All available research data/results/scripts plus strategy and B code snapshot; unrelated historical workspace edits are preserved as-is')
    OUT.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if k!='files'},ensure_ascii=False))
    print('VERIFIED_FILES',len(records))

if __name__=='__main__':main()
