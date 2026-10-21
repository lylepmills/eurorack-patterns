#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Fetch optional measured traces; verify archive and member hashes before use.

No board, serial port or measurement application is opened by this tool.
Use --check for an offline integrity check, or --from-dir for local archives.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'tests/measured/manifest.json'


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def relative_path(value):
    path = PurePosixPath(value)
    if (path.is_absolute() or '..' in path.parts or '\\' in value
            or ':' in value or str(path) != value
            or path.parts[:2] != ('tests', 'measured')):
        raise ValueError('unsafe evidence path')
    return path


def matches(path, record):
    return (path.is_file() and not path.is_symlink()
            and path.stat().st_size == record['size']
            and digest(path) == record['sha256'])


def destination(root, name):
    path = root / relative_path(name)
    # Reject symlinked parents, including dangling symlinks.
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError('symlink in evidence destination')
    return path


def install_archive(archive, record, root):
    if not matches(archive, record):
        raise ValueError('archive size or SHA-256 mismatch: ' + record['name'])
    with tempfile.TemporaryDirectory(prefix='evidence-') as staging:
        staging = Path(staging)
        staged = []
        with tarfile.open(archive, 'r:') as source:
            members = source.getmembers()
            names = [m.name for m in members]
            if len(names) != len(set(names)):
                raise ValueError('duplicate archive member')
            for info in members:
                relative_path(info.name)
                if not info.isfile():
                    raise ValueError('non-file archive member')
            for item in record['files']:
                target = destination(root, item['path'])
                info = source.getmember(item['path'])
                if info.size != item['size']:
                    raise ValueError('member size mismatch')
                staged_path = staging / str(len(staged))
                with source.extractfile(info) as data, staged_path.open('wb') as out:
                    shutil.copyfileobj(data, out)
                if not matches(staged_path, item):
                    raise ValueError('member SHA-256 mismatch')
                staged.append((staged_path, target))
        # Nothing is installed until every selected member has passed.
        for path, target in staged:
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as out:
                temp = Path(out.name)
                try:
                    with path.open('rb') as data:
                        shutil.copyfileobj(data, out)
                except BaseException:
                    temp.unlink(missing_ok=True)
                    raise
            try:
                temp.replace(target)
            finally:
                temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='verify installed files; no download')
    parser.add_argument('--list', action='store_true', help='list archive sizes; no download')
    parser.add_argument('--campaign', action='append', help='exact campaign directory name; repeatable')
    parser.add_argument('--from-dir', type=Path, help='read release archives from this directory')
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    if manifest['schema_version'] != 1:
        parser.error('unsupported manifest version')
    archives = manifest['archives']
    if args.campaign:
        known = {a['campaign'] for a in archives}
        unknown = set(args.campaign) - known
        if unknown:
            parser.error('unknown campaign: ' + ', '.join(sorted(unknown)))
        archives = [a for a in archives if a['campaign'] in args.campaign]
    if args.list:
        for record in archives:
            print(f"{record['campaign']}: {record['size'] / 1048576:.1f} MiB")
        print(f"Total: {sum(a['size'] for a in archives) / 1048576:.1f} MiB")
        return
    for record in archives:
        missing = [f for f in record['files'] if not matches(destination(ROOT, f['path']), f)]
        if not missing:
            continue
        if args.check:
            raise SystemExit('Missing or changed evidence: ' + missing[0]['path']
                             + '\nRun python3 tools/fetch_evidence.py to restore it.')
        if args.from_dir:
            install_archive(args.from_dir / record['name'], record, ROOT)
        else:
            print('Fetching ' + record['name'], flush=True)
            with tempfile.TemporaryDirectory(prefix='evidence-download-') as temp:
                archive = Path(temp) / record['name']
                request = urllib.request.Request(manifest['download_base'] + '/' + record['name'],
                                                 headers={'User-Agent': 'eurorack-patterns-evidence'})
                with urllib.request.urlopen(request, timeout=60) as response, archive.open('wb') as out:
                    remaining = record['size']
                    while remaining:
                        chunk = response.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError('truncated evidence download')
                        out.write(chunk)
                        remaining -= len(chunk)
                    if response.read(1):
                        raise ValueError('evidence download exceeds manifest size')
                install_archive(archive, record, ROOT)
    print('PASS: all selected evidence files match the pinned manifest')


if __name__ == '__main__':
    main()
