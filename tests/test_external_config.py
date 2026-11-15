import tempfile
import unittest
from pathlib import Path
from unittest import mock

from actions_trigger import external_config


class IsYamlTestCase(unittest.TestCase):
    def test_yaml_suffixes(self):
        self.assertTrue(external_config.is_yaml('unit.yaml'))
        self.assertTrue(external_config.is_yaml('UNIT.YML'))
        self.assertFalse(external_config.is_yaml('unit.json'))
        self.assertFalse(external_config.is_yaml('yaml'))


class FromReleaseTestCase(unittest.TestCase):
    def test_keeps_yaml_assets(self):
        release = {
            'assets': [
                {'name': 'one.yaml', 'browser_download_url': 'u1'},
                {'name': 'notes.txt', 'browser_download_url': 'u2'},
                {'name': 'two.yml', 'browser_download_url': 'u3'},
            ]
        }
        with mock.patch.object(external_config, 'get_release_by_tag', return_value=release) as m:
            files = external_config.from_release('o/r', 'store-config')
        m.assert_called_once_with('o/r', 'store-config')
        self.assertEqual([(f.name, f.url) for f in files], [('one.yaml', 'u1'), ('two.yml', 'u3')])

    def test_missing_release(self):
        with mock.patch.object(external_config, 'get_release_by_tag', return_value=None):
            self.assertEqual(external_config.from_release('o/r', 'store-config'), [])


class FromBranchTestCase(unittest.TestCase):
    def test_keeps_downloadable_yaml_files(self):
        entries = [
            {'name': 'one.yaml', 'path': 'config/one.yaml', 'type': 'file', 'download_url': 'u1'},
            {'name': 'two.yml', 'path': 'config/two.yml', 'type': 'file', 'download_url': 'u2'},
            {'name': 'notes.txt', 'path': 'config/notes.txt', 'type': 'file', 'download_url': 'u3'},
            {'name': 'no-url.yaml', 'path': 'config/no-url.yaml', 'type': 'file', 'download_url': None},
            {'name': 'nested', 'path': 'config/nested', 'type': 'dir', 'download_url': None},
        ]
        with mock.patch.object(external_config, 'list_contents', return_value=entries) as m:
            files = external_config.from_branch('o/r', 'config', 'config')
        m.assert_called_once_with('o/r', 'config', ref='config')
        self.assertEqual([(f.name, f.url) for f in files], [('one.yaml', 'u1'), ('two.yml', 'u2')])

    def test_missing_branch(self):
        with mock.patch.object(external_config, 'list_contents', return_value=None):
            self.assertEqual(external_config.from_branch('o/r', 'config'), [])


class SyncConfigsTestCase(unittest.TestCase):
    def test_writes_new_files_and_keeps_existing_ones(self):
        entries = [
            {'name': 'new.yaml', 'path': 'new.yaml', 'type': 'file', 'download_url': 'u1'},
            {'name': 'old.yaml', 'path': 'old.yaml', 'type': 'file', 'download_url': 'u2'},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp)
            (target_dir / 'old.yaml').write_text('local', encoding='utf-8')

            def fake_download(url, target):
                target.write_text(f'downloaded {url}', encoding='utf-8')

            with mock.patch.object(external_config.settings, 'config_dir', return_value=target_dir), \
                    mock.patch.object(external_config, 'list_contents', return_value=entries), \
                    mock.patch.object(external_config, 'download', side_effect=fake_download) as m:
                written = external_config.sync_configs('o/r', 'branch', branch='config')

            self.assertEqual([p.name for p in written], ['new.yaml'])
            m.assert_called_once()
            self.assertEqual((target_dir / 'new.yaml').read_text(encoding='utf-8'), 'downloaded u1')
            self.assertEqual((target_dir / 'old.yaml').read_text(encoding='utf-8'), 'local')

    def test_allow_override_rewrites_existing_file(self):
        entries = [{'name': 'old.yaml', 'path': 'old.yaml', 'type': 'file', 'download_url': 'u2'}]
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp)
            (target_dir / 'old.yaml').write_text('local', encoding='utf-8')

            def fake_download(url, target):
                target.write_text('remote', encoding='utf-8')

            with mock.patch.object(external_config.settings, 'config_dir', return_value=target_dir), \
                    mock.patch.object(external_config, 'list_contents', return_value=entries), \
                    mock.patch.object(external_config, 'download', side_effect=fake_download):
                written = external_config.sync_configs('o/r', 'branch', branch='config', allow_override=True)

            self.assertEqual([p.name for p in written], ['old.yaml'])
            self.assertEqual((target_dir / 'old.yaml').read_text(encoding='utf-8'), 'remote')

    def test_rejects_unsafe_names(self):
        entries = [{'name': '../evil.yaml', 'path': '../evil.yaml', 'type': 'file', 'download_url': 'u1'}]
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(external_config.settings, 'config_dir', return_value=Path(tmp)), \
                    mock.patch.object(external_config, 'list_contents', return_value=entries), \
                    mock.patch.object(external_config, 'download') as download:
                written = external_config.sync_configs('o/r', 'branch', branch='config')
            self.assertEqual(written, [])
            download.assert_not_called()

    def test_unknown_source(self):
        with self.assertRaises(ValueError):
            external_config.sync_configs('o/r', 'git')

    def test_cli_defaults_come_from_settings(self):
        # settings defaults are used when the flags are omitted
        parser = external_config.build_parser()
        args = parser.parse_args(['o/r'])
        self.assertEqual(args.source, external_config.settings.config_source())
        self.assertEqual(args.tag, external_config.settings.config_tag())
        self.assertEqual(args.branch, external_config.settings.config_branch())
        self.assertEqual(args.path, external_config.settings.config_path())


if __name__ == '__main__':
    unittest.main()
