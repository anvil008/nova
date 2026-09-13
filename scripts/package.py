#!/usr/bin/env python3
"""Build self-contained native bundles. Never install or modify harness settings."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HARNESSES = ('codex', 'claude', 'agy')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def copy_tree(source, destination):
    for path in source.rglob('*'):
        if path.is_symlink():
            raise ValueError(f'Package sources must not contain symlinks: {path}')
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store'))


def build(output, version=None):
    output = Path(output).absolute()
    # Only replace our own previous build, never an arbitrary destination.
    if output.is_symlink() or (output.exists() and not (output / '.nova-build').is_file()):
        raise ValueError(f'Refusing unowned output directory: {output}')
    if output == ROOT or ROOT.is_relative_to(output) or output.is_relative_to(ROOT / 'skills'):
        raise ValueError('Output overlaps source')
    output.parent.mkdir(parents=True, exist_ok=True)
    version = version or (ROOT / 'VERSION').read_text().strip()
    with tempfile.TemporaryDirectory(prefix='.nova-build-', dir=output.parent) as temp:
        staging = Path(temp) / 'bundle'
        staging.mkdir()
        (staging / '.nova-build').write_text(version + '\n')
        for harness in HARNESSES:
            marketplace = staging / harness
            plugin = marketplace / 'plugins/nova'
            copy_tree(ROOT / 'packaging' / harness, plugin)
            for name in ('skills', 'instructions', 'tools'):
                copy_tree(ROOT / name, plugin / name)
            copy_tree(ROOT / 'hooks', plugin / 'hooks')
            # Codex plugin agent discovery is not documented; carry explicit setup resources.
            agent_destination = 'setup/agents' if harness == 'codex' else 'agents'
            copy_tree(ROOT / 'agents' / harness, plugin / agent_destination)
            shutil.copy2(ROOT / 'instructions/install.md', plugin / 'INSTALL.md')
            manifest_path = plugin / {'codex': '.codex-plugin/plugin.json',
                                      'claude': '.claude-plugin/plugin.json',
                                      'agy': 'plugin.json'}[harness]
            manifest = json.loads(manifest_path.read_text())
            manifest['version'] = version
            write_json(manifest_path, manifest)
            if harness in ('codex', 'claude'):
                adapter = json.loads((plugin / 'hooks' / f'{harness}.example.json').read_text())
                adapter['hooks']['PostToolUse'][0]['hooks'][0]['command'] = (
                    f'python3 "${{CLAUDE_PLUGIN_ROOT}}/hooks/post-edit.py" --harness {harness}')
                # Automatic Nova Flow tracking is disabled for now.
                adapter['hooks']['PreToolUse'] = [{
                    'matcher': 'Read|read_file|Bash|exec_command|shell_command',
                    'hooks': [{'type': 'command', 'timeout': 5,
                               'command': f'python3 "${{CLAUDE_PLUGIN_ROOT}}/hooks/read-routing.py" --harness {harness}'}]}]
                for event in ('SubagentStop', 'Stop', 'SessionEnd'):
                    adapter['hooks'][event] = [{'hooks': [{'type': 'command', 'timeout': 5,
                        'command': 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/integration.py"'}]}]
                if harness == 'claude':
                    for event in ('WorktreeCreate', 'WorktreeRemove'):
                        adapter['hooks'][event] = [{'hooks': [{'type': 'command', 'timeout': 120,
                            'command': 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/workspace.py"'}]}]
                write_json(plugin / 'hooks/hooks.json', adapter)
            else:
                write_json(plugin / 'hooks.json', {'nova-read-routing': {
                    'enabled': True, 'description': 'Route bulk reads to the existing scout',
                    'PreToolUse': [{'matcher': 'view_file|run_command', 'hooks': [{
                        'type': 'command', 'timeout': 5,
                        'command': 'python3 -c "import os,sys; p = \\"hooks/read-routing.py\\" if os.path.exists(\\"hooks/read-routing.py\\") else os.path.expanduser(\\"~/.gemini/config/plugins/nova/hooks/read-routing.py\\"); os.execv(sys.executable, [sys.executable, p] + sys.argv[1:])" --harness agy'}]}]}})
                # Agy's Stop can continue once; PostToolUse records observed delegation.
                agy_hooks = json.loads((plugin / 'hooks.json').read_text())
                integration_command = ('python3 -c "import os,runpy; '
                    'p=os.path.expanduser(\\\"~/.gemini/config/plugins/nova/hooks/integration.py\\\"); '
                    'runpy.run_path(\\\"hooks/integration.py\\\" if os.path.isfile(\\\"hooks/integration.py\\\") '
                    'else p,run_name=\\\"__main__\\\")" --harness agy')
                agy_hooks['nova-integration'] = {
                    'enabled': True, 'description': 'One parent integration reminder after delegation',
                    'PostToolUse': [{'matcher': 'invoke_subagent', 'hooks': [{
                        'type': 'command', 'timeout': 5,
                        'command': integration_command + ' --event PostToolUse'}]}],
                    'Stop': [{'type': 'command', 'timeout': 5,
                              'command': integration_command + ' --event Stop'}]}
                write_json(plugin / 'hooks.json', agy_hooks)
                (plugin / 'rules').mkdir(exist_ok=True)
                shutil.copy2(ROOT / 'instructions/development.md', plugin / 'rules/nova.md')
            if harness == 'codex':
                index = {'name': 'nova', 'interface': {'displayName': 'Nova'},
                         'plugins': [{'name': 'nova',
                                      'source': {'source': 'local', 'path': './plugins/nova'},
                                      'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'},
                                      'category': 'Developer Tools'}]}
                write_json(marketplace / '.agents/plugins/marketplace.json', index)
            else:
                index = {'name': 'nova', 'owner': {'name': 'Foundry Zero'},
                         'plugins': [{'name': 'nova', 'source': './plugins/nova',
                                      'version': version, 'description': manifest['description']}]}
                write_json(marketplace / '.claude-plugin/marketplace.json', index)
        if output.exists():
            shutil.rmtree(output)
        shutil.move(str(staging), output)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/plugins')
    args = parser.parse_args()
    try:
        print(build(args.output))
    except (ValueError, OSError) as error:
        parser.exit(1, f'{error}\n')
