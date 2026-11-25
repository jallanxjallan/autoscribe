#!/usr/bin/env python3
"""Prepare immutable local release inputs. Never install, merge or activate."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import runpy

NATIVE = ('srv-output', 'srv-writeback', 'srv-control-ingest', 'srv-plan-select')
RETIRED = ('srv-export', 'srv-input')


def launcher(installed, selection, revisions):
    """The selected CLI verifies its own immutable payload before importing it."""
    return ('#!/opt/autoscribe/.venv/bin/python -I\n'
            'import hashlib, json, os, sys\nfrom pathlib import Path\n'
            'def require(value, message):\n    if not value: raise RuntimeError(message)\n'
            f'root = Path({str(installed)!r})\n'
            'manifest = json.loads((root / "manifest.json").read_text())\n'
            f'require(manifest["revisions"] == {revisions!r}, "release revision mismatch")\n'
            'prefix = root.name + "/"\n'
            'for name, digest in manifest["files"].items():\n'
            '    if name.startswith(prefix):\n'
            '        path = root / name[len(prefix):]\n'
            '        require(path.resolve().is_relative_to(root), "release path escape")\n'
            '        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, str(path))\n'
            'for path, digest in manifest["resource_files"].items():\n'
            '    require(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, path)\n'
            f'os.environ.update({selection!r})\n'
            f'os.execv(sys.executable, [sys.executable, "-I", "-B", {str(installed / "app/bin/asc")!r}, *sys.argv[1:]])\n')


def run(command, **kwargs):
    return subprocess.run([str(x) for x in command], check=True, **kwargs)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive_tree(source, destination):
    with tarfile.open(destination, 'x') as archive:
        for path in sorted(source.rglob('*')):
            relative = path.relative_to(source)
            info = archive.gettarinfo(str(path), str(relative))
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            info.mtime = 0
            with path.open('rb') if path.is_file() else io.BytesIO() as data:
                archive.addfile(info, data if path.is_file() else None)


def relocate_registry(engine, installed):
    path = engine / 'extensions/registry.json'
    registry = json.loads(path.read_text())
    if not isinstance(registry, dict):
        raise ValueError('script registry must be an object')
    relocated = {}
    for name, target in registry.items():
        if not isinstance(name, str) or not name or any(c.isspace() for c in name):
            raise ValueError('invalid script registry name')
        relative = Path(target).relative_to('/opt/autoscribe/extensions')
        if '..' in relative.parts:
            raise ValueError('script registry path escapes extensions')
        relocated[name] = str(installed / 'extensions' / relative)
    path.write_text(json.dumps(relocated, indent=2)+'\n')
    return relocated


def validate_catalogue_scripts(control, registry, installed, engine):
    """Every canonical script step must resolve to a packaged executable."""
    with sqlite3.connect(control.as_uri()+'?mode=ro&immutable=1', uri=True) as db:
        steps = db.execute("SELECT id,script FROM steps WHERE engine_kind='script' ORDER BY id").fetchall()
    dependencies = []
    for identity, name in steps:
        target = registry.get(name)
        if not isinstance(target, str):
            raise ValueError(f'Control step {identity}: unregistered script {name!r}')
        relative = Path(target).relative_to(installed)
        candidate = engine / relative
        if not candidate.resolve().is_relative_to(engine.resolve()):
            raise ValueError(f'Control step {identity}: script escapes packaged engine')
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise ValueError(f'Control step {identity}: packaged script missing or not executable: {name}')
        dependencies.append({'step_id': identity, 'script': name,
                             'packaged_path': str(relative), 'sha256': sha(candidate)})
    return dependencies


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--git-adapter', type=Path, required=True)
    parser.add_argument('--common', type=Path, required=True)
    parser.add_argument('--client', type=Path, required=True)
    parser.add_argument('--client-release', type=Path, required=True)
    parser.add_argument('--services', type=Path, required=True)
    parser.add_argument('--extensions', type=Path, required=True)
    parser.add_argument('--templates', type=Path, required=True)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--runtime-inventory', type=Path, required=True)
    args = parser.parse_args()
    output = args.destination
    if not output.is_absolute() or output.exists() or not output.parent.is_dir():
        parser.error('destination must be new, absolute and in an existing parent')
    if not args.git_adapter.is_absolute() or not args.git_adapter.is_file():
        parser.error('absolute git.py adapter required')
    sources = dict(autoscribe=Path(__file__).resolve().parent, common=args.common, client=args.client,
                   services=args.services, extensions=args.extensions,
                   templates=args.templates, control=args.control)
    def git(source, *parts):
        return run(['/usr/bin/python3', args.git_adapter, '-C', source, *parts],
                   capture_output=True, text=True).stdout.strip()
    revisions = {}
    for name, source in sources.items():
        if not source.is_absolute() or git(source, 'status', '--porcelain'):
            parser.error(f'{name}: source must be absolute, clean and committed')
        revisions[name] = git(source, 'rev-parse', 'HEAD')
    client_metadata=json.loads((args.client_release/'dispatch-provenance.json').read_text())
    if client_metadata['source_commit']!=revisions['client']:
        parser.error('client binary/source revision mismatch')
    for name,digest in client_metadata['files'].items():
        path=args.client_release/name
        if not path.resolve().is_relative_to(args.client_release.resolve()) or sha(path)!=digest:
            parser.error('client release checksum mismatch: '+name)
    release_id = 'qualified-' + revisions['autoscribe'][:12] + '-' + hashlib.sha256(
        json.dumps(revisions, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:20]
    installed = Path('/opt/autoscribe/services/releases') / release_id
    output.mkdir()
    with tempfile.TemporaryDirectory(prefix='autoscribe-release-') as temporary:
        temporary = Path(temporary)
        extracted = {}
        for name, source in sources.items():
            archive = output / (name + '-source.tar')
            git(source, 'archive', '--format=tar', '--output='+str(archive), revisions[name])
            tree = temporary / name
            tree.mkdir()
            with tarfile.open(archive) as files:
                files.extractall(tree, filter='data')
            extracted[name] = tree
        if sha(output/'client-source.tar')!=client_metadata['files']['client-source.tar']:
            raise ValueError('Client source archive differs from release source')
        shutil.copytree(args.client_release,output/('client-'+revisions['client'][:12]))
        engine = output / release_id
        engine.mkdir()
        shutil.copytree(extracted['autoscribe'] / 'app', engine / 'app')
        shutil.copytree(extracted['common'] / 'python/biznet_common', engine / 'app/biznet_common')
        (engine / 'extensions').mkdir()
        shutil.copy2(extracted['extensions'] / 'registry.json', engine / 'extensions/registry.json')
        shutil.copytree(extracted['extensions'] / 'scripts', engine / 'extensions/scripts')
        registry = relocate_registry(engine, installed)
        (engine / 'bin').mkdir()
        cargo = Path(shutil.which('cargo') or '/home/jeremy/.cargo/bin/cargo')
        target = Path('/tmp/autoscribe-qualified-services-target')
        run([cargo, 'build', '--release', '--offline', '--locked', '--manifest-path',
             extracted['services'] / 'Cargo.toml', '--target-dir', target,
             *[part for name in NATIVE for part in ('--bin', name)]],
            env=dict(os.environ, RUSTFLAGS='--remap-path-prefix='+str(extracted['services'])+'=/src/autoscribe-services'))
        for name in NATIVE:
            shutil.copy2(target / 'release' / name, engine / 'bin' / name)
        selection = {
            'AUTOSCRIBE_CONTROL_DB': '/var/lib/autoscribe/control.sqlite',
            'AUTOSCRIBE_LEDGER_DB': '/home/jeremy/Data/ledger.sql',
            'AUTOSCRIBE_RUNTIME_RETENTION_SECONDS': str(runpy.run_path(str(extracted['autoscribe'] / 'app/asc/settings.py'))['retention_seconds']()),
            'AUTOSCRIBE_REDIS_HOST': '127.0.0.1', 'AUTOSCRIBE_REDIS_PORT': '6379',
            'AUTOSCRIBE_EXTENSION_REGISTRY': str(installed / 'extensions/registry.json'),
            'TEMPLATES_ROOT': '/opt/autoscribe/templates/releases/'+revisions['templates'],
            'EXTENSIONS_ROOT': '/opt/autoscribe/extensions/releases/'+revisions['extensions'],
            'AUTOSCRIBE_PANDOC': '/home/jeremy/.local/bin/pandoc',
            'AUTOSCRIBE_RCLONE': '/home/jeremy/.local/bin/rclone',
        }
        selection['AUTOSCRIBE_RELEASE_ROOT'] = str(installed)
        wrapper = launcher(installed, selection, revisions)
        (engine / 'bin/asc').write_text(wrapper)
        (engine / 'bin/asc').chmod(0o755)
        # Client is an independently installed capability. Pin and archive its
        # protocol source; do not rebuild or install unrelated client commands.
        config = output / ('control-'+revisions['control'][:12])
        config.mkdir()
        shutil.copy2(output / 'control-source.tar', config / 'control-source.tar')
        policy = temporary / 'control-policy.toml'
        control_repo = temporary / 'control.git'
        git(sources['control'], 'clone', '--bare', str(sources['control']), str(control_repo))
        policy.write_text('[paths]\nrepo_roots=['+json.dumps(str(temporary))+']\neffect_key_file='+json.dumps(str(temporary/'unused-effect.key'))+'\n')
        adapter = temporary / 'git.py'
        adapter.write_text('#!/usr/bin/python3\nimport os, sys\nos.execv("/usr/bin/python3", ["/usr/bin/python3", '+repr(str(args.git_adapter))+', *sys.argv[1:]])\n')
        adapter.chmod(0o755)
        run([engine / 'bin/srv-control-ingest', '--policy', policy,
             '--repo', control_repo, '--commit', revisions['control'],
             '--db', config / 'control.sqlite'], env=dict(os.environ, VAULT_GIT_ADAPTER=str(adapter)))
        script_dependencies = validate_catalogue_scripts(config / 'control.sqlite', registry, installed, engine)
        (config / 'manifest.json').write_text(json.dumps({'source_commit': revisions['control'],
            'plan_id': 'pln_K9X7H2M4R6Q8V3TN', 'control_sha256': sha(config / 'control.sqlite'),
            'activation': 'not installed; independently versioned configuration'}, indent=2)+'\n')
        for name in ('extensions', 'templates'):
            # Independent dependency archives; never retarget publication current links.
            shutil.copy2(output / (name+'-source.tar'), output / (name+'-'+revisions[name]+'.tar'))
        for path in engine.rglob('*'):
            if path.name in RETIRED:
                raise RuntimeError('obsolete executable in release')
        for name, source in sources.items():
            if git(source, 'rev-parse', 'HEAD') != revisions[name] or git(source, 'status', '--porcelain'):
                raise RuntimeError('source changed during build')
        archive_tree(engine, output / (release_id+'.tar'))
        (output / (release_id+'.tar.sha256')).write_text(sha(output / (release_id+'.tar'))+'  '+release_id+'.tar\n')
        manifest = {'schema': 'autoscribe.qualified-release.v1', 'release_id': release_id,
                    'revisions': revisions, 'installed_engine': str(installed),
                    'selected_environment': selection, 'native_binaries': list(NATIVE), 'script_dependencies': script_dependencies,
                    'runtime_dependencies': json.loads(args.runtime_inventory.read_text()),
                    'source_provenance': {name: {'commit': revisions[name],
                        'repository': git(source, 'remote', 'get-url', 'origin'),
                        'archive_sha256': sha(output / (name+'-source.tar'))}
                        for name, source in sources.items()},
                    'resource_files': {str(Path(selection['EXTENSIONS_ROOT' if name=='extensions' else 'TEMPLATES_ROOT']) / p.relative_to(extracted[name])): sha(p)
                        for name in ('extensions','templates') for p in sorted(extracted[name].rglob('*')) if p.is_file()},
                    'protocols': {'prepared': 'autoscribe.prepared.v2', 'response': 'autoscribe.client-response.v1', 'component': 'asc.component.v1', 'step_result': 'asc.step-result.v1', 'runtime': 'asc.call.v1'},
                    'model_catalogue': dict(runpy.run_path(str(extracted['common'] / 'python/biznet_common/llm.py'))['MODELS']),
                    'client_release': {'directory':'client-'+revisions['client'][:12], 'provenance_sha256':sha(args.client_release/'dispatch-provenance.json')},
                    'capability_bindings': {'autoscribe': str(installed),
                        'native_services': {'selection': '/opt/autoscribe/services/current', 'commit': revisions['services']},
                        'control': {'database': selection['AUTOSCRIBE_CONTROL_DB'], 'source_commit': revisions['control'], 'schema_version': 3},
                        'extensions': selection['EXTENSIONS_ROOT'], 'templates': selection['TEMPLATES_ROOT']},
                    'cargo': run([cargo, '--version'], capture_output=True, text=True).stdout.strip(),
                    'rustc': run(['/home/jeremy/.cargo/bin/rustc', '--version'], capture_output=True, text=True).stdout.strip(),
                    'files': {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file()},
                    'status': 'prepared only; not approved, installed or operational'}
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
        (output / 'SHA256SUMS').write_text(''.join(sha(p)+'  '+str(p.relative_to(output))+'\n'
            for p in sorted(output.rglob('*')) if p.is_file() and p != output / 'SHA256SUMS'))
    print(json.dumps({'destination': str(output), 'manifest_sha256': sha(output / 'manifest.json')}))


def extend_runtime():
    """Package changed Extensions against an accepted runtime, reusing native/app bytes."""
    parser=argparse.ArgumentParser(description='Extend an accepted immutable runtime without rebuilding unchanged dependencies')
    parser.add_argument('--extend-runtime',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--extensions-archive',type=Path,required=True)
    parser.add_argument('--autoscribe-archive',type=Path)
    parser.add_argument('--extensions-commit',required=True)
    parser.add_argument('--autoscribe-commit',required=True)
    args=parser.parse_args()
    previous=args.extend_runtime.resolve(strict=True)
    prior=json.loads((previous/'manifest.json').read_text())
    prefix=previous.name+'/'
    for name,digest in prior['files'].items():
        if name.startswith(prefix) and sha(previous/name[len(prefix):])!=digest:
            raise ValueError('Accepted runtime payload changed: '+name)
    if args.autoscribe_commit != prior['revisions']['autoscribe']:
        raise ValueError('Extension-only release must retain the accepted application revision')
    output=args.destination
    if not output.is_absolute() or output.exists() or not output.parent.is_dir():
        raise ValueError('Use a new absolute destination in an existing parent')
    output.mkdir()
    revisions=dict(prior['revisions'],autoscribe=args.autoscribe_commit,extensions=args.extensions_commit)
    release_id='qualified-'+revisions['autoscribe'][:12]+'-'+hashlib.sha256(json.dumps(revisions,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:20]
    installed=previous.parent/release_id
    engine=output/release_id
    shutil.copytree(previous,engine)
    (engine/'manifest.json').unlink()
    with tempfile.TemporaryDirectory(prefix='extensions-package-') as temp:
        extensions=Path(temp)
        with tarfile.open(args.extensions_archive) as archive:archive.extractall(extensions,filter='data')
        shutil.rmtree(engine/'extensions')
        (engine/'extensions').mkdir()
        for name in ('scripts','registry.json','capabilities.json'):
            source=extensions/name
            if source.is_dir():shutil.copytree(source,engine/'extensions'/name)
            else:shutil.copy2(source,engine/'extensions'/name)
        registry=relocate_registry(engine,installed)
        selection=dict(prior['selected_environment'],AUTOSCRIBE_RELEASE_ROOT=str(installed),
            AUTOSCRIBE_EXTENSION_REGISTRY=str(installed/'extensions/registry.json'),
            EXTENSIONS_ROOT='/opt/autoscribe/extensions/releases/'+revisions['extensions'])
        (engine/'bin/asc').chmod(0o755)
        (engine/'bin/asc').write_text(launcher(installed,selection,revisions));(engine/'bin/asc').chmod(0o755)
        resources={p:h for p,h in prior['resource_files'].items() if not p.startswith(prior['selected_environment']['EXTENSIONS_ROOT']+'/')}
        resources.update({str(Path(selection['EXTENSIONS_ROOT'])/p.relative_to(extensions)):sha(p) for p in extensions.rglob('*') if p.is_file()})
        extension_archive=output/('extensions-'+revisions['extensions']+'.tar')
        shutil.copy2(args.extensions_archive,extension_archive)
    shutil.copy2(args.extensions_archive,output/'extensions-source.tar')
    if args.autoscribe_archive is not None:
        shutil.copy2(args.autoscribe_archive,output/'autoscribe-source.tar')
    archive_tree(engine,output/(release_id+'.tar'))
    manifest=dict(prior,schema='autoscribe.qualified-release.v1',release_id=release_id,revisions=revisions,
        installed_engine=str(installed),selected_environment=selection,resource_files=resources,
        reused_runtime=dict(path=str(previous),manifest_sha256=sha(previous/'manifest.json'),
                            unchanged=['app','native binaries','Common','clients','Control','Templates']),
        source_provenance={name:dict(prior['source_provenance'][name],commit=revisions[name],archive_sha256=sha(output/(name+'-source.tar'))) for name in (('autoscribe','extensions') if args.autoscribe_archive is not None else ('extensions',))},
        status='prepared; runtime extension only; existing accepted payload reused')
    manifest['capability_bindings']=dict(prior['capability_bindings'],autoscribe=str(installed),extensions=selection['EXTENSIONS_ROOT'])
    manifest['files']={str(p.relative_to(output)):sha(p) for p in output.rglob('*') if p.is_file()}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(release=release_id,manifest_sha256=sha(output/'manifest.json'))))


if __name__ == '__main__':
    import sys
    if '--extend-runtime' in sys.argv:extend_runtime()
    else:main()
