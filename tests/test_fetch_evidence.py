# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Integrity and safe-install checks for the optional evidence downloader."""
import hashlib
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import fetch_evidence as fetch


class EvidenceTests(unittest.TestCase):
    def archive(self, root, members):
        archive = root / 'sample.tar'
        records = []
        with tarfile.open(archive, 'w') as out:
            for name, value, kind in members:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.size = len(value) if kind == tarfile.REGTYPE else 0
                out.addfile(info, io.BytesIO(value))
                records.append(dict(path=name, size=len(value),
                                    sha256=hashlib.sha256(value).hexdigest()))
        return archive, dict(name=archive.name, size=archive.stat().st_size,
                             sha256=fetch.digest(archive), files=records)

    def test_valid_archive_is_installed_and_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive, record = self.archive(root, [('tests/measured/example/trace.txt.gz', b'abc', tarfile.REGTYPE)])
            fetch.install_archive(archive, record, root)
            self.assertTrue(fetch.matches(root / record['files'][0]['path'], record['files'][0]))
            fetch.install_archive(archive, record, root)  # Idempotent restoration.

    def test_wrong_archive_hash_cannot_install(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive, record = self.archive(root, [('tests/measured/a', b'abc', tarfile.REGTYPE)])
            record['sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'archive size or SHA'):
                fetch.install_archive(archive, record, root)
            self.assertFalse((root / 'tests').exists())

    def test_bad_later_member_does_not_partially_install(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive, record = self.archive(root, [('tests/measured/a', b'a', tarfile.REGTYPE),
                                                 ('tests/measured/b', b'b', tarfile.REGTYPE)])
            record['files'][1]['sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'member SHA'):
                fetch.install_archive(archive, record, root)
            self.assertFalse((root / 'tests').exists())

    def test_paths_links_and_duplicate_members_are_rejected(self):
        cases = [('../outside', tarfile.REGTYPE), ('/absolute', tarfile.REGTYPE),
                 ('tests/measured/../../outside', tarfile.REGTYPE),
                 ('tests/measured/link', tarfile.SYMTYPE)]
        for name, kind in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                archive, record = self.archive(root, [(name, b'', kind)])
                with self.assertRaises(ValueError):
                    fetch.install_archive(archive, record, root)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive, record = self.archive(root, [('tests/measured/a', b'a', tarfile.REGTYPE)] * 2)
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                fetch.install_archive(archive, record, root)

    def test_existing_symlink_cannot_redirect_install(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'outside').mkdir()
            try:
                (root / 'tests').symlink_to(root / 'outside', target_is_directory=True)
            except OSError:
                self.skipTest('Creating symlinks requires platform permission')
            archive, record = self.archive(root, [('tests/measured/a', b'a', tarfile.REGTYPE)])
            with self.assertRaisesRegex(ValueError, 'symlink'):
                fetch.install_archive(archive, record, root)
            self.assertFalse((root / 'outside/measured').exists())

    def test_previous_revision_can_select_a_subset_of_an_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive, record = self.archive(root, [('tests/measured/a', b'a', tarfile.REGTYPE),
                                                 ('tests/measured/b', b'b', tarfile.REGTYPE)])
            record['files'] = record['files'][:1]
            fetch.install_archive(archive, record, root)
            self.assertTrue((root / 'tests/measured/a').is_file())
            self.assertFalse((root / 'tests/measured/b').exists())


if __name__ == '__main__':
    unittest.main()
