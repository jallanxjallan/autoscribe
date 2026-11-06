"""Use the existing Extensions Dropbox handler; never transfer client assets."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys

class PreprocessInfrastructureError(RuntimeError):
    pass


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise PreprocessInfrastructureError('Shared Dropbox resource cannot be loaded')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def stage_assets(references: list[str], work: Path | None) -> list[dict]:
    if not references:
        return []
    if work is None or not work.is_absolute() or not work.is_dir():
        raise PreprocessInfrastructureError('Dropbox assets require the verified SSH job directory')
    root = Path(os.environ.get('EXTENSIONS_ROOT') or os.environ.get('AUTOSCRIBE_EXTENSIONS_ROOT')
                or '/opt/autoscribe/extensions/current').resolve()
    rclone = Path(os.environ.get('AUTOSCRIBE_RCLONE', '/home/jeremy/.local/bin/rclone'))
    if 'AUTOSCRIBE_RCLONE' not in os.environ and not rclone.is_file():
        rclone = Path('/usr/bin/rclone')
    if not rclone.is_absolute() or not rclone.is_file() or not os.access(rclone, os.X_OK):
        raise PreprocessInfrastructureError('Dropbox rclone dependency unavailable')
    try:
        catalog = _module('autoscribe_shared_resources', root / 'runtime/resources.py')
        resource = catalog.ResourceCatalog.extensions(root).resolve('assets', 'dropbox-bitmap')
        handler = _module('autoscribe_shared_dropbox_assets', Path(resource)).DropboxAssetHandler(
            os.environ.get('DROPBOX_ASSET_ROOT', 'dropbox:'), rclone=str(rclone))
        # Same established publication adapter mapping; preserve original links
        # separately. This is storage resolution, not manuscript rewriting.
        prefix = '/home/jeremy/Dropbox/'
        remote = ['dropbox:' + ref[len(prefix):] if ref.startswith(prefix) else ref for ref in references]
        return [dict(item.to_dict(), requested_ref=original)
                for original, item in zip(references, handler.stage(remote, work), strict=True)]
    except Exception as exc:
        if isinstance(exc, PreprocessInfrastructureError):
            raise
        raise PreprocessInfrastructureError('Shared Dropbox asset retrieval/dependency failed') from exc
