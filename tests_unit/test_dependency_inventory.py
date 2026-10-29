import base64
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.dependency_inventory import build_inventory, generate, npm_components, python_components

ROOT = Path(__file__).resolve().parents[1]


class InventoryTests(unittest.TestCase):
    def test_python_ranges_are_not_installed_versions(self):
        components = python_components(ROOT)
        fastapi = next(c for c in components if c["name"] == "fastapi")
        self.assertNotIn("version", fastapi)
        self.assertIn(
            {"name": "judgeai:declared-requirement", "value": "fastapi>=0.110.0"},
            fastapi["properties"],
        )
        self.assertEqual(fastapi["licenses"][0]["expression"], "MIT")

    def test_scoped_and_nested_npm_identities_and_real_sri_hashes(self):
        digest = bytes(range(64))
        lock = {
            "packages": {
                "": {},
                "node_modules/@scope/pkg": {
                    "version": "1.2.3",
                    "integrity": "sha512-" + base64.b64encode(digest).decode(),
                    "resolved": "https://registry.npmjs.org/@scope/pkg/-/pkg-1.2.3.tgz",
                    "license": "MIT",
                },
                "node_modules/outer/node_modules/@scope/pkg": {
                    "version": "1.2.3",
                    "integrity": "sha512-" + base64.b64encode(digest).decode(),
                    "resolved": "https://registry.npmjs.org/@scope/pkg/-/pkg-1.2.3.tgz",
                },
            }
        }
        components, _ = npm_components(lock)
        self.assertEqual(len({c["bom-ref"] for c in components}), 2)
        self.assertEqual(components[0]["hashes"], [{"alg": "SHA-512", "content": digest.hex()}])
        self.assertEqual(components[0]["purl"], "pkg:npm/%40scope/pkg@1.2.3")
        self.assertNotIn("licenses", components[1])

    def test_secret_or_direct_dependency_urls_are_rejected_without_echo(self):
        from tools.dependency_inventory import safe_url, split_requirement

        for url in (
            "https://user:secret@example.com/a",
            "https://registry.npmjs.org/a?token=secret",
        ):
            with self.assertRaises(ValueError) as error:
                safe_url(url)
            self.assertNotIn("secret", str(error.exception))
        with self.assertRaises(ValueError) as error:
            split_requirement("thing @ https://user:secret@example.com/pkg.whl")
        self.assertNotIn("secret", str(error.exception))

    def test_invalid_sri_and_missing_exact_versions_fail(self):
        entry = {"version": "1.0.0", "integrity": "sha512-not-base64"}
        for value in (entry, {"integrity": "sha512-" + base64.b64encode(bytes(64)).decode()}):
            with self.assertRaises(ValueError):
                npm_components({"packages": {"": {}, "node_modules/pkg": value}})

    def test_real_repository_is_complete_deterministic_and_does_not_read_env(self):
        first, report = build_inventory(ROOT)
        second, _ = build_inventory(ROOT)
        self.assertEqual(first, second)
        npm = [c for c in first["components"] if c["bom-ref"].startswith("npm:")]
        lock = json.loads((ROOT / "verdikt-web/package-lock.json").read_text())
        self.assertEqual(len(npm), len(lock["packages"]) - 1)
        self.assertIn("unresolved", json.dumps(first))
        self.assertIn(f"**{len(lock['packages']) - 1}**", report)
        self.assertEqual(len({c["bom-ref"] for c in first["components"]}), len(first["components"]))

    def test_generate_and_check_detect_drift_without_rewriting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                "pyproject.toml",
                "packages/legal_core/pyproject.toml",
                "verdikt-web/package.json",
                "verdikt-web/package-lock.json",
                "docs/compliance/license-evidence.json",
                "docs/compliance/resources.json",
                "docs/legal-sources.json",
                "src/config.py",
                "Dockerfile",
                "Dockerfile.preview",
                "docker-compose.yml",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / relative).read_bytes())
            self.assertTrue(generate(root))
            self.assertTrue(generate(root, check=True))
            output = root / "docs/compliance/sbom.cdx.json"
            output.write_text("stale artifact\n")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertFalse(generate(root, check=True))
            self.assertEqual(output.read_text(), "stale artifact\n")

    def test_manifest_drift_and_missing_license_evidence_are_not_silent(self):
        from tools.dependency_inventory import validate_lock_manifest

        lock = {"lockfileVersion": 3, "packages": {"": {"dependencies": {"react": "^19"}}}}
        with self.assertRaisesRegex(ValueError, "declarations differ"):
            validate_lock_manifest({"dependencies": {"react": "^20"}}, lock)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "packages/legal_core").mkdir(parents=True)
            (root / "docs/compliance").mkdir(parents=True)
            (root / "pyproject.toml").write_text('[project]\ndependencies=["new-library>=1"]\n')
            (root / "packages/legal_core/pyproject.toml").write_text("[project]\ndependencies=[]\n")
            (root / "docs/compliance/license-evidence.json").write_text('{"python": []}')
            with self.assertRaisesRegex(ValueError, "license evidence"):
                python_components(root)

    def test_reads_only_public_allowlisted_inputs(self):
        from tools.dependency_inventory import INPUTS

        original = Path.open
        seen = set()

        def guarded(path, *args, **kwargs):
            relative = path.relative_to(ROOT).as_posix()
            self.assertIn(relative, INPUTS)
            seen.add(relative)
            return original(path, *args, **kwargs)

        with patch.object(Path, "open", guarded):
            build_inventory(ROOT)
        self.assertEqual(seen, set(INPUTS))

    def test_cli_check_returns_nonzero_on_missing_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/dependency_inventory.py"),
                    "--check",
                    "--root",
                    directory,
                ],
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Inventory validation failed", result.stderr)

    def test_nested_dependency_edges_choose_the_nearest_locked_package(self):
        from tools.dependency_inventory import npm_resolve

        packages = {
            "node_modules/dep": {"version": "1.0.0"},
            "node_modules/outer/node_modules/dep": {"version": "2.0.0"},
        }
        self.assertEqual(
            npm_resolve(packages, "node_modules/outer", "dep"),
            "npm:node_modules/outer/node_modules/dep@2.0.0",
        )
        self.assertEqual(
            npm_resolve(packages, "node_modules/unrelated", "dep"), "npm:node_modules/dep@1.0.0"
        )
        self.assertIsNone(npm_resolve(packages, "", "absent"))

    def test_signed_query_and_fragment_urls_cannot_enter_public_inventory(self):
        from tools.dependency_inventory import safe_url

        urls = [
            "https://registry.npmjs.org/a?X-Amz-Signature=private-marker",
            "https://example.com/archive#access_token=private-marker",
            "https://example.com/archive?custom_session=private-marker",
            "https://pravo.gov.ru/act?nd=123&X-Amz-Credential=private-marker",
        ]
        for url in urls:
            with self.subTest(url=url):
                with self.assertRaises(ValueError) as error:
                    safe_url(url)
                self.assertNotIn("private-marker", str(error.exception))
        self.assertEqual(
            safe_url("http://pravo.gov.ru/proxy/ips/?savertf=&nd=123&page=all"),
            "http://pravo.gov.ru/proxy/ips/?savertf=&nd=123&page=all",
        )

    def test_npm_ranges_tags_and_wrong_types_are_not_exact_versions(self):
        encoded = base64.b64encode(bytes(64)).decode()
        for version in ("^1.2.3", "~1.2.3", "latest", "*", 123, "1.2", "1.2.3-01"):
            with self.subTest(version=version):
                with self.assertRaises(ValueError):
                    npm_components(
                        {
                            "packages": {
                                "": {},
                                "node_modules/a": {
                                    "version": version,
                                    "integrity": "sha512-" + encoded,
                                    "resolved": "https://registry.npmjs.org/a/-/a.tgz",
                                },
                            }
                        }
                    )
        components, _ = npm_components(
            {
                "packages": {
                    "": {},
                    "node_modules/a": {
                        "version": "1.2.3-beta.1+build.01",
                        "integrity": "sha512-" + encoded,
                        "resolved": "https://registry.npmjs.org/a/-/a.tgz",
                    },
                }
            }
        )
        self.assertEqual(components[0]["version"], "1.2.3-beta.1+build.01")
