"""Bounded, task-isolated local cache of generated picture tracks."""
import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'output' / 'picture-track-cache'
MAX_BYTES = 2 * 1024**3
MAX_AGE = 15 * 86400


def cache_path(task_id, signature):
    digest = hashlib.sha256(json.dumps({'task': task_id, 'signature': signature}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return ROOT / (digest + '.mp4')


def restore(path, destination):
    try:
        if time.time() - path.stat().st_mtime > MAX_AGE:
            return False
        shutil.copyfile(path, destination)
        return True
    except OSError:
        return False


def save(path, source):
    """Cache failures never fail a production render; only this cache is pruned."""
    temporary = None
    try:
        ROOT.mkdir(parents=True, exist_ok=True)
        temporary = ROOT / (uuid.uuid4().hex + '.tmp')
        shutil.copyfile(source, temporary)
        os.replace(temporary, path)
        files = sorted(ROOT.glob('*.mp4'), key=lambda file: file.stat().st_mtime, reverse=True)
        used = 0
        for file in files:
            if not file.resolve().is_relative_to(ROOT.resolve()):
                continue
            size = file.stat().st_size
            if time.time() - file.stat().st_mtime > MAX_AGE or used + size > MAX_BYTES:
                file.unlink(missing_ok=True)
            else:
                used += size
    except OSError:
        pass
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
