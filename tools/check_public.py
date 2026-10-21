#!/usr/bin/env python3
"""Check local documentation links and accidental private paths before publishing.

Optionally set EP_PRIVATE_TERMS to newline-separated private identifiers locally.
Never commit that list or put it in public workflow output. This check supplements
human review; it cannot determine whether otherwise generic content is public.
"""
import gzip
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
# A complete five-minute bench wire trace is larger than 16 MiB. Scan it in
# full; retain a bounded decompression limit and reject, never skip, excess.
MAX_COMPRESSED_TEXT = 64 * 1024 * 1024

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])

def main():
    patterns = [
        ('home directory', re.compile(r'(?<![a-z:])/(?:Users|home)/[A-Za-z0-9_.-]+/')),
        ('Windows home', re.compile(r'(?i)[A-Z]:[\\/]Users[\\/][^\s\\/]+[\\/]')),
    ]
    patterns.extend(('private identifier', re.compile(re.escape(term), re.I))
                    for term in os.environ.get('EP_PRIVATE_TERMS', '').splitlines() if term.strip())
    problems = []
    def scan(label, text):
        for kind, pattern in patterns:
            if pattern.search(text):
                problems.append(label + ': ' + kind + ' found (content omitted)')
    names = set(git('ls-files', '-z', '--cached', '--others', '--exclude-standard').decode().split('\0')) - {''}
    for name in sorted(names):
        path = ROOT / name
        if not path.is_file():
            continue
        scan(name, name)
        try:
            if path.name.endswith('.txt.gz'):
                with gzip.open(path, 'rt', encoding='utf-8') as stream:
                    text = stream.read(MAX_COMPRESSED_TEXT + 1)
                if len(text) > MAX_COMPRESSED_TEXT:
                    problems.append(name + ': compressed text exceeds review limit')
                    continue
            else:
                text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        scan(name, text)
        if path.suffix == '.md':
            for target in re.findall(r'!?\[[^\]]*\]\(([^\s)]+)\)', text):
                parsed = urlsplit(target)
                if parsed.scheme or target.startswith('#'):
                    continue
                if not (path.parent / unquote(parsed.path)).exists():
                    problems.append(name + ': missing relative link ' + target)
    # Review all reachable commit messages too; fetch full history in CI.
    scan('commit messages', git('log', '--all', '--format=%B').decode())
    if problems:
        raise SystemExit('\n'.join(problems))
    print('PASS: public-path and local-link checks; human content/provenance review still required')

if __name__ == '__main__':
    main()
