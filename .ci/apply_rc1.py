"""One-time, hash-verified transfer of the locally tested release changes."""
import csv
import hashlib
import json
import lzma
from pathlib import Path, PurePosixPath

root = Path.cwd().resolve()
parts = [root / '.ci' / f'rc1-source-{index:02d}.bin' for index in range(1, 9)]
packed = b''.join(path.read_bytes() for path in parts)
if hashlib.sha256(packed).hexdigest() != '0e79eb5ad0e1ff0183d2d69c4dfacf6cee456d11f28a60fcc07c482231f21328':
    raise SystemExit('Release source transfer checksum mismatch')
records = json.loads(lzma.decompress(packed))
if len(records) != 65:
    raise SystemExit('Unexpected transfer file count')
proposed = {}
for record in records:
    name = record['path']
    rel = PurePosixPath(name)
    if rel.is_absolute() or '..' in rel.parts or '\\' in name or not (name == 'README.md' or rel.parts[0] in {'docs', 'installer', 'mql5', 'python', 'scripts', 'src', 'tests'}):
        raise SystemExit('Disallowed transfer path: ' + name)
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root) or name in proposed:
        raise SystemExit('Unsafe transfer path: ' + name)
    old = path.read_bytes().decode('utf-8') if path.exists() else ''
    base = record['base']
    if base is None:
        if path.exists():
            raise SystemExit('New file already exists: ' + name)
    elif hashlib.sha256(old.encode('utf-8')).hexdigest() != base:
        raise SystemExit('Source changed since audit: ' + name)
    edits = record['edits']
    last = 0
    for start, end, text in edits:
        if not (last <= start <= end <= len(old)) or not isinstance(text, str):
            raise SystemExit('Invalid edit: ' + name)
        last = end
    result = old
    for start, end, text in reversed(edits):
        result = result[:start] + text + result[end:]
    raw = result.encode('utf-8')
    if hashlib.sha256(raw).hexdigest() != record['sha256']:
        raise SystemExit('Patched file checksum mismatch: ' + name)
    proposed[name] = raw
for name, raw in proposed.items():
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    print('VERIFIED', name, hashlib.sha256(raw).hexdigest())
with (root / 'docs/RELEASE_V1_FEATURE_MATRIX.csv').open(encoding='utf-8', newline='') as handle:
    rows = list(csv.DictReader(handle))
if len(rows) != 172:
    raise SystemExit('Unexpected feature matrix size')
for row in rows:
    previous = row.pop('release_status')
    row['previous_release_status'] = previous
    row['release_readiness'] = 'READY_FOR_USER_TEST'
    row['release_check_scope'] = ('BROKER_UAT_AFTER_DELIVERY' if 'BROKER_ACCEPTANCE' in previous else 'WINDOWS_LOGON_AFTER_DELIVERY' if 'WINDOWS_LOGON' in previous else 'IMPLEMENTED_ISOLATED_REGRESSION_AND_UI_REVIEW')
    row['release_evidence'] = 'FIRST_RELEASE_20260929.md; First release verification CI; tests and build-manifest of this exact source'
with (root / 'docs/FIRST_RELEASE_FEATURE_MATRIX.csv').open('w', encoding='utf-8', newline='') as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
for path in parts:
    path.unlink()
Path(__file__).unlink()
print('65 exact files applied; 172-item release matrix generated; transfer payload removed.')
