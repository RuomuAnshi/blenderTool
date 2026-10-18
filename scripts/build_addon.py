"""Build a Blender extension ZIP with its manifest at archive root."""
from pathlib import Path
import ast
import hashlib
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'character_effects'
manifest = tomllib.loads((SOURCE / 'blender_manifest.toml').read_text())
version = manifest['version']
module = ast.parse((SOURCE / '__init__.py').read_text())
info = next(ast.literal_eval(n.value) for n in module.body
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'bl_info' for t in n.targets))
if '.'.join(map(str, info['version'])) != version:
    raise SystemExit('Manifest and bl_info versions differ')
for name in ('__init__.py', 'blender_manifest.toml', 'LICENSE', 'assets/bath.blend', 'assets/ATTRIBUTION.txt'):
    if not (SOURCE / name).is_file():
        raise SystemExit(f'Missing runtime file: {name}')
output = ROOT / 'dist'
output.mkdir(exist_ok=True)
archive = output / f'blenderTool-v{version}.zip'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
    for file in sorted(SOURCE.rglob('*')):
        rel = file.relative_to(SOURCE)
        if not file.is_file() or any(p.startswith('.') or p == '__pycache__' for p in rel.parts):
            continue
        if file.suffix not in {'.py', '.toml', '.txt', '.blend'} and file.name != 'LICENSE':
            continue
        entry = zipfile.ZipInfo(rel.as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
        entry.compress_type = zipfile.ZIP_DEFLATED
        entry.external_attr = 0o100644 << 16
        bundle.writestr(entry, file.read_bytes(), compresslevel=9)
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
checksum = output / 'SHA256SUMS.txt'
checksum.write_text(f'{digest}  {archive.name}\n')
print(f'{archive.name}: {archive.stat().st_size} bytes')
print(f'SHA256: {digest}')
