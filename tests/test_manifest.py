import hashlib
import json
import os
import unittest
import zipfile
from plugin import Plugin


REPOSITORY_ROOT = os.path.dirname(os.path.dirname(__file__))


class RepositoryManifestTests(unittest.TestCase):
    def test_repository_manifest_matches_current_release(self):
        with open(
            os.path.join(REPOSITORY_ROOT, "manifest.json"),
            encoding="utf-8",
        ) as handle:
            document = json.load(handle)

        with open(os.path.join(REPOSITORY_ROOT, 'plugin.json')) as handle:
            config = json.load(handle)
        self.assertEqual(config['version'], Plugin.version)
        self.assertEqual(config['fields'], Plugin.fields)
        self.assertEqual(config['actions'], Plugin.actions)
        manifest = document["manifest"]
        self.assertEqual(manifest["registry_name"], "StreamSieve Plugins")
        self.assertEqual(len(manifest["plugins"]), 1)

        entry = manifest["plugins"][0]
        self.assertEqual(entry["slug"], "streamsieve")
        self.assertEqual(entry["name"], "StreamSieve")
        self.assertEqual(entry["latest_version"], "1.6.0")
        self.assertEqual(
            entry["latest_url"],
            "https://github.com/NicholasBoulanger/StreamSieve/releases/"
            "download/v1.6.0/StreamSieve-v1.6.0.zip",
        )

        release_zip = os.path.join(
            REPOSITORY_ROOT, "dist", "StreamSieve-v1.6.0.zip"
        )
        if os.path.exists(release_zip):
            with open(release_zip, "rb") as handle:
                checksum = hashlib.sha256(handle.read()).hexdigest()
            self.assertEqual(entry["latest_sha256"], checksum)
            with zipfile.ZipFile(release_zip) as archive:
                for name in ('plugin.py', 'plugin.json', 'reconciliation.py', 'sync.py', 'README.md', 'LICENSE'):
                    with open(os.path.join(REPOSITORY_ROOT, name), 'rb') as source:
                        self.assertEqual(archive.read('streamsieve/' + name), source.read())


if __name__ == "__main__":
    unittest.main()
