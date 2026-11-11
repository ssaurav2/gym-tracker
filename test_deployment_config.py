"""Offline guards for routing and accidental private-file bundling, not a Vercel emulator."""
import fnmatch
import json
from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parent


class DeploymentConfigTest(unittest.TestCase):
    def test_backend_excludes_private_data_without_excluding_runtime(self):
        config = json.loads((ROOT / 'vercel.json').read_text())
        metadata = tomllib.loads((ROOT / 'pyproject.toml').read_text())
        self.assertEqual(metadata['tool']['vercel']['entrypoint'], 'api:app')
        patterns = config['functions']['api.py']['excludeFiles'].strip('{}').split(',')
        # fnmatch checks these concrete examples only, not Vercel's full glob syntax.
        def excluded(path):
            return any(fnmatch.fnmatchcase(path, pattern) or
                       (pattern.startswith('**/') and fnmatch.fnmatchcase(path, pattern[3:]))
                       for pattern in patterns)
        for path in ('gym_tracker.db', 'backups/snapshot/gym_tracker.db', 'private/progress-photos/photo.jpg', '.env', '.env.local', 'nested/.env.production', 'nested/backup.sqlite3-wal', 'import_sqlite.py', 'progress_photos.py', 'frontend/src/main.jsx'):
            self.assertTrue(excluded(path), path)
        for path in ('api.py', 'authentication.py', 'database.py', 'settings.py', 'pyproject.toml'):
            self.assertFalse(excluded(path), path)
        for path in ('.vercelignore', 'frontend/.vercelignore'):
            rules = (ROOT / path).read_text()
            for required in ('**/*.db', '**/.env', '**/.env.*', 'backups/', 'private/'):
                self.assertIn(required, rules)

    def test_api_routes_and_subpaths_precede_html_fallback(self):
        config = json.loads((ROOT / 'frontend/vercel.json').read_text())
        rules = config['rewrites']
        api_rules = rules[:-1]
        self.assertEqual({r['source'] for r in api_rules}, {'/exercises', '/exercises/:path*', '/sets', '/sets/:path*'})
        origins = set()
        for rule in api_rules:
            origin, path = rule['destination'].split('://', 1)[1].split('/', 1)
            self.assertTrue(rule['destination'].startswith('https://'))
            self.assertEqual('/' + path, rule['source'])
            self.assertNotIn('?', rule['destination'])  # Don't override incoming filters.
            origins.add(origin)
        self.assertEqual(len(origins), 1)
        self.assertEqual(rules[-1]['destination'], '/index.html')
        self.assertIn('?!assets/', rules[-1]['source'])

    def test_both_layers_disable_api_response_caching(self):
        frontend = json.loads((ROOT / 'frontend/vercel.json').read_text())
        backend = json.loads((ROOT / 'vercel.json').read_text())
        self.assertEqual({r['source'] for r in frontend['headers']}, {r['source'] for r in frontend['rewrites'][:-1]})
        self.assertEqual(backend['headers'][0]['source'], '/(.*)')
        for rule in frontend['headers'] + backend['headers']:
            headers = {h['key'].lower(): h['value'] for h in rule['headers']}
            for key in ('cache-control', 'cdn-cache-control', 'vercel-cdn-cache-control'):
                self.assertEqual(headers[key], 'no-store')


if __name__ == '__main__':
    unittest.main()
