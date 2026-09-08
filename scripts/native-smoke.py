#!/usr/bin/env python3
"""Linux-only offline native plugin install trial with isolated home configuration mounts."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New evidence directory')
    parser.add_argument('--bootstrap', action='store_true', help='Exercise bootstrap twice instead of direct native commands')
    options = parser.parse_args()
    output = options.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    if not shutil.which('bwrap'):
        parser.exit(1, 'bubblewrap is required; no unisolated fallback is used\n')
    results = []
    with tempfile.TemporaryDirectory(prefix='nova-native-') as name:
        trial = Path(name)
        args = ['bwrap', '--ro-bind', '/', '/', '--proc', '/proc', '--dev', '/dev',
                '--unshare-pid', '--unshare-net', '--die-with-parent',
                '--bind', str(trial), str(trial)]
        for folder in ('.codex', '.agents', '.claude', '.gemini'):
            target = trial / folder
            target.mkdir()
            args += ['--bind', str(target), str(Path.home() / folder)]
        config = trial / 'claude.json'; config.write_text('{}')
        args += ['--bind', str(config), str(Path.home() / '.claude.json'), '--chdir', str(trial)]
        commands = [
            ['codex', 'plugin', 'marketplace', 'add', str(ROOT / 'dist/plugins/codex'), '--json'],
            ['codex', 'plugin', 'add', 'nova@nova', '--json'],
            ['codex', 'plugin', 'list', '--json'],
            ['claude', 'plugin', 'marketplace', 'add', str(ROOT / 'dist/plugins/claude')],
            ['claude', 'plugin', 'install', 'nova@nova'],
            ['claude', 'plugin', 'details', 'nova@nova'],
            ['agy', 'plugin', 'install', str(ROOT / 'dist/plugins/agy/plugins/nova')],
            ['agy', 'plugin', 'list'],
        ]
        if options.bootstrap:
            command = [str(ROOT / 'scripts/bootstrap.sh'), '--harness', 'all',
                       '--with-codex-helpers', '--prefix', str(trial / 'prefix'), '--bin-dir', str(trial / 'bin')]
            commands = [command, command, [str(trial / 'bin/nova-flow'), '--dir', str(trial / 'run'), 'init', 'Installed tool smoke test'], [str(trial / 'bin/nova-flow'), '--dir', str(trial / 'run'), 'check']]
        for command in commands:
            try:
                result = subprocess.run(args + command, capture_output=True, text=True, timeout=45)
                record = {'command': command, 'exit': result.returncode,
                          'stdout': result.stdout, 'stderr': result.stderr}
            except (OSError, subprocess.TimeoutExpired) as error:
                record = {'command': command, 'exit': None, 'error': str(error)}
            results.append(record)
            print(' '.join(command[:3]), record['exit'], flush=True)
        # Native installation must retain assets and shared instruction links.
        for harness, pattern in [('codex', '.codex/plugins/cache/**/skills/refactor/SKILL.md'),
                                  ('claude', '.claude/plugins/cache/**/skills/refactor/SKILL.md'),
                                  ('agy', '.gemini/**/plugins/nova/skills/refactor/SKILL.md')]:
            skills = list(trial.glob(pattern))
            valid = bool(skills) and all((p.parent / 'assets/report.html').is_file()
                                        and (p.parent / '../../instructions/development.md').is_file()
                                        for p in skills)
            results.append({'component': harness + ' installed assets', 'exit': 0 if valid else 1})
    (output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    if any(r['exit'] != 0 for r in results):
        parser.exit(1, f'Native trial has failures; see {output}\n')
    print(output)


if __name__ == '__main__':
    main()
