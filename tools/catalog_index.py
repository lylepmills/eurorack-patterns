#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Regenerate the catalog's entry index from its headings; --check verifies it.

The index sits between the catalog-index markers in docs/catalog.md. Each row
comes from a "### <ID> <title>" heading, grouped under the "## " section that
precedes it, so adding, renaming or renumbering an entry needs only a rerun.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'docs/catalog.md'
BEGIN = '<!-- catalog-index:begin -->'
END = '<!-- catalog-index:end -->'
SECTION = re.compile(r'^## (.+?)\s*$')
ENTRY = re.compile(r'^### ([A-Z]\d{2}) (.+?)\s*$')


def anchor(heading):
    """GitHub's heading slug: lowercase, drop punctuation, spaces to hyphens."""
    return re.sub(r'[^a-z0-9 -]', '', heading.lower()).replace(' ', '-')


def render(lines):
    rows, section, current, seen = [], None, None, set()
    for line in lines:
        match = SECTION.match(line)
        if match:
            section = match.group(1)
            continue
        match = ENTRY.match(line)
        if not match:
            continue
        ident, title = match.groups()
        if ident in seen:
            sys.exit('docs/catalog.md: duplicate entry ' + ident)
        seen.add(ident)
        if section != current:
            current = section
            rows.append('| **' + section + '** | |')
        rows.append('| ' + ident + ' | [' + title + '](#' + anchor(ident + ' ' + title) + ') |')
    return [BEGIN, 'All ' + str(len(seen)) + ' entries, in catalog order:', '',
            '| ID | Pattern |', '| --- | --- |', *rows, '', END], len(seen)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='fail if the index is stale; write nothing')
    args = parser.parse_args()
    lines = CATALOG.read_text(encoding='utf-8').split('\n')
    if BEGIN not in lines or END not in lines or lines.index(END) < lines.index(BEGIN):
        sys.exit('docs/catalog.md: catalog-index markers missing or out of order')
    begin, end = lines.index(BEGIN), lines.index(END)
    index, count = render(lines)
    updated = lines[:begin] + index + lines[end + 1:]
    if updated == lines:
        print('PASS: catalog index is current (' + str(count) + ' entries)')
        return
    if args.check:
        sys.exit('docs/catalog.md: catalog index is stale; run python3 tools/catalog_index.py')
    CATALOG.write_text('\n'.join(updated), encoding='utf-8')
    print('Updated catalog index (' + str(count) + ' entries)')


if __name__ == '__main__':
    main()
