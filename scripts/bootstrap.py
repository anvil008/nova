#!/usr/bin/env python3
"""Build and install Workcell with native plugin managers. No dependency downloads."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

from package import ROOT, HARNESSES, build, write_json


def run(command, capture=False):
    print('+ ' + shlex.join(map(str, command)), flush=True)
    result = subprocess.run(list(map(str, command)), check=True, text=True,
                            stdout=subprocess.PIPE if capture else None, timeout=120)
    return json.loads(result.stdout) if capture else None


def fingerprint():
    digest = hashlib.sha256()
    for folder in ('skills', 'instructions', 'agents', 'hooks', 'tools', 'packaging'):
        for path in sorted((ROOT / folder).rglob('*')):
            if path.is_file() and not any(x in path.parts for x in ('__pycache__', '.DS_Store')) and path.suffix != '.pyc':
                digest.update(str(path.relative_to(ROOT)).encode())
                digest.update(path.read_bytes())
    digest.update((ROOT / 'scripts/package.py').read_bytes())
    return digest.hexdigest()[:16]


def marketplace(harness, expected, replace):
    data = run([harness, 'plugin', 'marketplace', 'list', '--json'], capture=True)
    entries = data['marketplaces'] if harness == 'codex' else data
    matches = [e for e in entries if e['name'] == 'workcell']
    if not matches:
        return 'add'
    current = matches[0].get('root' if harness == 'codex' else 'path', '')
    if current and Path(current).resolve() == expected.resolve():
        return 'keep'
    if not replace:
        raise ValueError(f'{harness}: marketplace workcell already uses {current or "another source"}. '
                         'Use --replace-marketplace to switch this named marketplace explicitly.')
    return 'replace'


def owned_updates(sources, target_root, receipt):
    updates = []
    for source in sorted(sources):
        target = target_root / source.name
        new = source.read_bytes()
        if target.is_symlink():
            raise ValueError(f'Refusing installed-file symlink: {target}')
        if target.exists():
            old = target.read_bytes()
            if old != new and hashlib.sha256(old).hexdigest() != receipt.get(str(target)):
                raise ValueError(f'Existing file differs and is not an unchanged bootstrap copy: {target}')
        updates.append((target, new))
    return updates


def helper_updates(source_dir, receipt):
    target_root = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'agents'
    return owned_updates(source_dir.glob('*.toml'), target_root, receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--harness', action='append', choices=HARNESSES + ('all',),
                        help='Repeat to select harnesses; default: all available CLIs')
    parser.add_argument('--dry-run', action='store_true', help='Print actions without writes or native commands')
    parser.add_argument('--prefix', type=Path,
                        default=Path.home() / '.local/share/workcell', help='Stable package storage')
    parser.add_argument('--bin-dir', type=Path, default=Path.home() / '.local/bin', help='Install workcell-flow here')
    parser.add_argument('--with-codex-helpers', action='store_true', help='Install optional native TOML helpers')
    parser.add_argument('--replace-marketplace', action='store_true', help='Switch an existing workcell marketplace source')
    options = parser.parse_args()
    selected = options.harness or [h for h in HARNESSES if shutil.which(h)]
    if 'all' in selected:
        selected = list(HARNESSES)
    selected = list(dict.fromkeys(selected))
    if not selected:
        parser.error('No supported harness CLI found. Install Codex, Claude Code, or Agy first.')
    missing = [h for h in selected if not shutil.which(h)]
    if missing:
        parser.error('Missing harness CLI: ' + ', '.join(missing))
    if options.with_codex_helpers and 'codex' not in selected:
        parser.error('--with-codex-helpers requires selecting codex')
    prefix = options.prefix.expanduser().absolute()
    bundle = prefix / 'plugins'
    receipt_path = prefix / 'bootstrap.json'
    try:
        if prefix.is_symlink():
            raise ValueError(f'Refusing symlink prefix: {prefix}')
        if options.dry_run:
            print(f'Build self-contained bundles in {bundle}')
            print(f'Install workcell-flow in {options.bin_dir.expanduser().absolute()} with ownership checks')
            for harness in selected:
                print(f'{harness}: inspect marketplace; register if absent; install/update workcell')
            if options.with_codex_helpers:
                print('Copy Codex helpers only if absent, identical, or unchanged since this bootstrap installed them')
            print('Project instructions and formatter/linter activation remain repo-setup tasks.')
            return
        # Preflight every registry before build or installation writes.
        actions = {h: marketplace(h, bundle / h, options.replace_marketplace)
                   for h in selected if h != 'agy'}
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
        tool_copies = owned_updates([ROOT / 'tools/workcell-flow'], options.bin_dir.expanduser().absolute(), receipt.get('tools', {}))
        helpers = []
        # Preflight helper files using the canonical sources before publishing the bundle.
        if options.with_codex_helpers:
            helpers = helper_updates(ROOT / 'agents/codex', receipt.get('helpers', {}))
        version = (ROOT / 'VERSION').read_text().strip().split('+')[0]
        version += ('.' if '-' in version else '-') + 'local.' + fingerprint()
        build(bundle, version=version)
        for harness in selected:
            if harness == 'agy':
                run(['agy', 'plugin', 'install', bundle / 'agy/plugins/workcell'])
            else:
                if actions[harness] == 'replace':
                    run([harness, 'plugin', 'marketplace', 'remove', 'workcell'])
                if actions[harness] in ('add', 'replace'):
                    run([harness, 'plugin', 'marketplace', 'add', bundle / harness])
                if harness == 'codex':
                    run(['codex', 'plugin', 'add', 'workcell@workcell'])
                else:
                    installed = run(['claude', 'plugin', 'list', '--json'], capture=True)
                    exists = any(x['id'] == 'workcell@workcell' and x.get('scope') == 'user' for x in installed)
                    if actions[harness] == 'keep':
                        run(['claude', 'plugin', 'marketplace', 'update', 'workcell'])
                    run(['claude', 'plugin', 'update' if exists else 'install', 'workcell@workcell'])
        owned = receipt.get('helpers', {})
        for target, data in helpers:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            owned[str(target)] = hashlib.sha256(data).hexdigest()
        owned_tools = receipt.get('tools', {})
        for target, data in tool_copies:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(0o755)
            owned_tools[str(target)] = hashlib.sha256(data).hexdigest()
        write_json(receipt_path, {'version': version, 'harnesses': selected, 'helpers': owned, 'tools': owned_tools})
        print(f'Installed workcell-flow in {options.bin_dir.expanduser().absolute()}; add this directory to PATH if needed.')
        print('Workcell installed. Start new harness sessions to load the updated plugins.')
        print('Project instructions and formatter/linter activation remain repo-setup tasks.')
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f'Bootstrap stopped: {error}\nCompleted native installations are retained; fix the error and rerun.\n')


if __name__ == '__main__':
    main()
