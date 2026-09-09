"""Build a deterministic plugin archive and update the repository manifest."""
import hashlib
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent
config = json.loads((root / 'plugin.json').read_text())
version = config['version']
output = root / 'dist' / f'StreamSieve-v{version}.zip'
output.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
    for name in ('plugin.py', 'plugin.json', 'reconciliation.py', 'sync.py', 'README.md', 'LICENSE'):
        info = zipfile.ZipInfo('streamsieve/' + name, (2026, 9, 9, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, (root / name).read_bytes())
manifest_path = root / 'manifest.json'
document = json.loads(manifest_path.read_text())
document['generated_at'] = '2026-09-09T00:00:00Z'
entry = document['manifest']['plugins'][0]
entry.update(latest_version=version, last_updated=document['generated_at'],
             latest_url=f'https://github.com/NicholasBoulanger/StreamSieve/releases/download/v{version}/{output.name}',
             latest_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
             latest_size=max(1, (output.stat().st_size + 1023) // 1024),
             description=config['description'])
manifest_path.write_text(json.dumps(document, indent=2) + '\n')
print(output)
print(entry['latest_sha256'])
