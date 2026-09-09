import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reconciliation import Library, atomic_write


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'Series'
        self.root.mkdir()
        with Library(self.root, initialize=True):
            pass

    def test_content_updates_noop_and_stable_path(self):
        with Library(self.root) as lib:
            path = lib.assign('s', 'Show') + '/episode.strm'
            self.assertEqual(lib.write('e', path, 'old\n', 's'), 'created')
            before = (self.root / path).stat().st_mtime_ns
            self.assertEqual(lib.write('e', path, 'old\n', 's'), 'unchanged')
            self.assertEqual((self.root / path).stat().st_mtime_ns, before)
            self.assertEqual(lib.assign('s', 'Renamed'), 'Show')
            self.assertEqual(lib.write('e', 'elsewhere.strm', 'new\n', 's'), 'updated')
            self.assertEqual((self.root / path).read_text(), 'new\n')
            self.assertFalse((self.root / 'elsewhere.strm').exists())

    def test_unmanaged_and_modified_files_preserved(self):
        (self.root / 'user.strm').write_text('user')
        with Library(self.root) as lib:
            self.assertEqual(lib.write('u', 'user.strm', 'new', 's'), 'unmanaged')
            lib.write('e', 'owned.strm', 'initial', 's')
            (self.root / 'owned.strm').write_text('edited')
            self.assertEqual(lib.write('e', 'owned.strm', 'new', 's'), 'conflict')
            self.assertEqual(lib.retire({'s'}), {'retired': 0, 'conflict': 1})
        self.assertEqual((self.root / 'user.strm').read_text(), 'user')

    def test_retire_preserves_unmanaged_and_other_scope(self):
        with Library(self.root) as lib:
            lib.write('a', 'A/Season 01/a.strm', 'a', 'a')
            lib.write('b', 'B/b.strm', 'b', 'b')
            (self.root / 'A/user.nfo').write_text('user')
            self.assertEqual(lib.retire({'a'})['retired'], 1)
            self.assertFalse((self.root / 'A/Season 01').exists())
            self.assertTrue((self.root / 'A/user.nfo').exists())
            self.assertTrue((self.root / 'B/b.strm').exists())
            self.assertEqual((lib.state_dir / 'recovery/A/Season 01/a.strm').read_text(), 'a')

    def test_preview_does_not_write(self):
        before = {p: p.stat().st_mtime_ns for p in Path(self.temp.name).rglob('*')}
        with Library(self.root, preview=True) as lib:
            lib.assign('s', 'Show')
            self.assertEqual(lib.write('e', 'Show/e.strm', 'url', 's'), 'created')
        after = {p: p.stat().st_mtime_ns for p in Path(self.temp.name).rglob('*')}
        self.assertEqual(before, after)

    def test_missing_marker_fails_without_creating_media(self):
        (self.root / '.streamsieve-root').unlink()
        with self.assertRaises(ValueError):
            Library(self.root)

    def test_lock_rejects_second_writer(self):
        with Library(self.root):
            with self.assertRaises(ValueError):
                Library(self.root)

    def test_symlink_and_traversal_rejected(self):
        with Library(self.root) as lib:
            with self.assertRaises(ValueError):
                lib.write('x', '../outside', 'bad', 's')
            (self.root / 'linked').symlink_to(self.temp.name)
            with self.assertRaises(ValueError):
                lib.write('x', 'linked/outside', 'bad', 's')

    def test_recover_crash_after_file_before_index(self):
        with Library(self.root) as lib:
            lib.write('e', 'episode.strm', 'old', 's')
            real_save = lib._save
            def fail_index(name, value):
                if name == 'index.json':
                    raise OSError('simulated disk failure')
                real_save(name, value)
            with patch.object(lib, '_save', side_effect=fail_index):
                with self.assertRaises(OSError):
                    lib.write('e', 'episode.strm', 'new', 's')
        with Library(self.root) as recovered:
            self.assertEqual(recovered.write('e', 'episode.strm', 'new', 's'), 'unchanged')

    def test_failed_atomic_replace_preserves_old_file(self):
        target = self.root / 'test'
        target.write_bytes(b'old')
        with patch('reconciliation.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                atomic_write(target, b'new')
        self.assertEqual(target.read_bytes(), b'old')
        self.assertEqual(list(self.root.glob('.streamsieve-*')), [self.root / '.streamsieve-root'])

    def test_case_collision_gets_distinct_name(self):
        with Library(self.root) as lib:
            self.assertNotEqual(lib.assign('a', 'Show').casefold(), lib.assign('b', 'show').casefold())

    def test_corrupt_index_fails_closed(self):
        index = self.root.with_name('Series.streamsieve-state') / 'index.json'
        index.write_text('{')
        with self.assertRaises(json.JSONDecodeError):
            Library(self.root)

    def test_restore_retired_files_and_preserve_conflicts(self):
        with Library(self.root) as lib:
            lib.write('a', 'A/a.strm', 'a', 'a')
            lib.retire({'a'})
            self.assertEqual(lib.restore({'a'})['restored'], 1)
            self.assertEqual((self.root / 'A/a.strm').read_text(), 'a')
            lib.retire({'a'})
            (self.root / 'A').mkdir(exist_ok=True)
            (self.root / 'A/a.strm').write_text('user')
            self.assertEqual(lib.restore({'a'})['conflict'], 1)
            self.assertEqual((self.root / 'A/a.strm').read_text(), 'user')

    def test_output_readable_by_media_server(self):
        with Library(self.root) as lib:
            lib.write('a', 'a.strm', 'url', 'a')
        self.assertEqual((self.root / 'a.strm').stat().st_mode & 0o777, 0o644)

    def test_preview_retirement_leaves_owned_files(self):
        with Library(self.root) as lib:
            lib.write('a', 'a.strm', 'url', 'a')
        with Library(self.root, preview=True) as lib:
            self.assertEqual(lib.retire({'a'})['retired'], 1)
        self.assertTrue((self.root / 'a.strm').exists())
