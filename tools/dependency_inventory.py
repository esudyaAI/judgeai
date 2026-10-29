"""Offline source inventory, not a resolved runtime SBOM or a license approval.

Reads a fixed allowlist of public project manifests; never inspects the environment.
"""

import argparse
import ast
import base64
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlsplit

INPUTS = (
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
)


def public_query_allowed(host: str, key: str, value: str) -> bool:
    if host == "pravo.gov.ru":
        return (
            (key == "savertf" and value == "")
            or (key == "nd" and re.fullmatch(r"[0-9]+", value) is not None)
            or (key == "page" and (value == "all" or value.isascii() and value.isdecimal()))
        )
    if host in {"vsrf.ru", "www.vsrf.ru"}:
        return (key == "__download" and value == "1") or (
            key == "__filename"
            and re.fullmatch(r"[^\x00-\x1f/\\?#&]{1,240}\.pdf", value) is not None
        )
    return False


def safe_url(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or any(ord(character) < 32 for character in url)
        or any(
            not public_query_allowed(parsed.hostname, key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        )
    ):
        raise ValueError("Source URL contains credentials or an unsupported format")
    return url


def prop(name: str, value: str) -> dict:
    return {"name": "judgeai:" + name, "value": value}


def split_requirement(requirement: str) -> tuple[str, str]:
    if "@" in requirement or "://" in requirement:
        raise ValueError("Direct dependency URLs require a separate provenance review")
    match = re.fullmatch(
        r"([A-Za-z0-9][A-Za-z0-9_.-]*)(\[[A-Za-z0-9_,.-]+\])?([^\n]*)", requirement
    )
    if not match:
        raise ValueError("Unsupported dependency requirement")
    return re.sub(r"[-_.]+", "-", match[1]).lower(), requirement


def read_json(root: Path, path: str):
    return json.loads((root / path).read_text(encoding="utf-8"))


def python_components(root: Path) -> list[dict]:
    evidence = {
        item["name"]: item
        for item in read_json(root, "docs/compliance/license-evidence.json")["python"]
    }
    declarations: dict[str, set[tuple[str, str]]] = {}
    for path in ("pyproject.toml", "packages/legal_core/pyproject.toml"):
        manifest = tomllib.loads((root / path).read_text(encoding="utf-8"))
        project = manifest["project"]
        groups = {
            "runtime": project.get("dependencies", []),
            "build": manifest.get("build-system", {}).get("requires", []),
        }
        groups.update(
            {
                "extra:" + key: value
                for key, value in project.get("optional-dependencies", {}).items()
            }
        )
        for group, requirements in groups.items():
            for requirement in requirements:
                name, original = split_requirement(requirement)
                declarations.setdefault(name, set()).add((path + ":" + group, original))
    components = []
    for name, entries in sorted(declarations.items()):
        if name not in evidence:
            raise ValueError("Missing reviewed license evidence for dependency: " + name)
        record = evidence[name]
        properties = [
            prop("resolution", "unresolved"),
            prop("license-evidence-scope", record["applies_to"]),
            prop("license-evidence-git-blob", record["evidence_git_blob"]),
        ]
        for source, requirement in sorted(entries):
            properties.extend(
                [prop("declaration", source), prop("declared-requirement", requirement)]
            )
        components.append(
            {
                "type": "library",
                "bom-ref": "pypi:" + name,
                "name": name,
                "purl": "pkg:pypi/" + name,
                "licenses": [{"expression": record["license_expression"]}],
                "externalReferences": [
                    {"type": "license", "url": safe_url(record["evidence_blob_url"])}
                ],
                "properties": properties,
            }
        )
    return components


def validate_lock_manifest(manifest: dict, lock: dict) -> None:
    if lock.get("lockfileVersion") != 3:
        raise ValueError("Expected npm package-lock version 3")
    locked_root = lock.get("packages", {}).get("")
    if not isinstance(locked_root, dict):
        raise ValueError("Missing npm root package")
    for group in ("dependencies", "devDependencies", "optionalDependencies"):
        if manifest.get(group, {}) != locked_root.get(group, {}):
            raise ValueError("npm manifest and lockfile declarations differ: " + group)


def exact_npm_version(version) -> str:
    if not isinstance(version, str) or not re.fullmatch(
        r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
        r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
        r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?",
        version,
    ):
        raise ValueError("npm package requires an exact supported semantic version")
    prerelease = version.split("+", 1)[0].partition("-")[2]
    if any(
        part.isdecimal() and len(part) > 1 and part.startswith("0")
        for part in prerelease.split(".")
    ):
        raise ValueError("npm prerelease version is not canonical")
    return version


def npm_ref(path: str, entry: dict) -> str:
    return "npm:" + path + "@" + exact_npm_version(entry.get("version"))


def npm_resolve(packages: dict, parent: str, name: str) -> str | None:
    current = parent
    while True:
        candidate = (current + "/" if current else "") + "node_modules/" + name
        if candidate in packages:
            return npm_ref(candidate, packages[candidate])
        if not current:
            return None
        current = current.rsplit("/node_modules/", 1)[0] if "/node_modules/" in current else ""


def npm_components(lock: dict) -> tuple[list[dict], list[dict]]:
    packages = lock["packages"]
    components, dependencies = [], []
    for path, entry in sorted(packages.items()):
        if not path:
            continue
        if "node_modules/" not in path or entry.get("link") or not entry.get("version"):
            raise ValueError("npm package lacks a supported exact identity")
        name = entry.get("name") or path.rsplit("node_modules/", 1)[-1]
        component = {
            "type": "library",
            "bom-ref": npm_ref(path, entry),
            "name": name,
            "version": entry["version"],
            "purl": "pkg:npm/" + quote(name, safe="/") + "@" + quote(entry["version"], safe=""),
            "properties": [
                prop("resolution", "npm-lock"),
                prop("lock-path", path),
                prop("development", str(entry.get("dev", False)).lower()),
                prop("license-evidence-scope", "npm-lock-metadata-not-release-approval"),
            ],
        }
        hashes = []
        for integrity in entry.get("integrity", "").split():
            algorithm, separator, encoded = integrity.partition("-")
            if not separator or algorithm not in {"sha256", "sha384", "sha512"}:
                raise ValueError("Unsupported npm integrity format")
            try:
                digest = base64.b64decode(encoded, validate=True)
            except ValueError:
                raise ValueError("Invalid npm integrity encoding") from None
            if len(digest) != int(algorithm[3:]) // 8:
                raise ValueError("Invalid npm integrity length")
            hashes.append({"alg": "SHA-" + algorithm[3:], "content": digest.hex()})
        if not hashes:
            raise ValueError("Missing npm integrity")
        component["hashes"] = hashes
        if entry.get("license"):
            component["licenses"] = [{"expression": entry["license"]}]
        else:
            component["properties"].append(prop("license-status", "unknown"))
        if not entry.get("resolved"):
            raise ValueError("Missing npm distribution provenance")
        if entry.get("resolved"):
            component["externalReferences"] = [
                {"type": "distribution", "url": safe_url(entry["resolved"])}
            ]
        components.append(component)
        edges = set()
        for group in ("dependencies", "optionalDependencies", "peerDependencies"):
            for dependency in entry.get(group, {}):
                target = npm_resolve(packages, path, dependency)
                optional = group == "optionalDependencies" or entry.get(
                    "peerDependenciesMeta", {}
                ).get(dependency, {}).get("optional", False)
                if target:
                    edges.add(target)
                elif not optional:
                    raise ValueError("Missing locked npm dependency: " + dependency)
        dependencies.append({"ref": component["bom-ref"], "dependsOn": sorted(edges)})
    return components, dependencies


def configured_model(root: Path) -> str:
    tree = ast.parse((root / "src/config.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "EMBEDDING_MODEL"
        ):
            return ast.literal_eval(node.value)
    raise ValueError("Configured embedding model could not be inventoried statically")


def build_inventory(root: Path) -> tuple[dict, str]:
    manifest = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    core = tomllib.loads((root / "packages/legal_core/pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    npm_manifest = read_json(root, "verdikt-web/package.json")
    lock = read_json(root, "verdikt-web/package-lock.json")
    validate_lock_manifest(npm_manifest, lock)
    components = python_components(root)
    python_count = len(components)
    npm, dependencies = npm_components(lock)
    components.extend(npm)
    components.append(
        {
            "type": "library",
            "bom-ref": "project:legal_core",
            "name": core["name"],
            "version": core["version"],
            "properties": [prop("origin", "local-project-source")],
        }
    )
    resources = read_json(root, "docs/compliance/resources.json")
    model_name = configured_model(root)
    model = next((item for item in resources["models"] if item["name"] == model_name), None)
    if model is None:
        raise ValueError("Configured model lacks reviewed provenance")
    components.append(
        {
            "type": "machine-learning-model",
            "bom-ref": "model:" + model_name,
            "name": model_name,
            "licenses": [{"expression": model["declared_license"]}],
            "externalReferences": [{"type": "website", "url": safe_url(model["source_url"])}],
            "properties": [prop("revision", "unresolved"), prop("usage", model["usage"])],
        }
    )
    legal_sources = read_json(root, "docs/legal-sources.json")
    for source in legal_sources:
        if not re.fullmatch(r"[a-f0-9]{64}", source["sha256"]):
            raise ValueError("Invalid legal source digest")
        components.append(
            {
                "type": "data",
                "bom-ref": "legal-source:" + source["key"],
                "name": source["title"],
                "hashes": [{"alg": "SHA-256", "content": source["sha256"]}],
                "externalReferences": [
                    {"type": "distribution", "url": safe_url(source["source_url"])}
                ],
                "properties": [
                    prop("verification", source["verification_status"]),
                    prop("rights-review", "pending"),
                ],
            }
        )
    for item in resources.get("preview_runtime", []):
        components.append(
            {
                "type": "application" if item["name"] == "LibreOffice Writer" else "data",
                "bom-ref": "preview-runtime:" + item["name"],
                "name": item["name"],
                "licenses": [{"license": {"name": item["license_notice"]}}],
                "externalReferences": [{"type": "website", "url": safe_url(item["source_url"])}],
                "properties": [
                    prop("evidence", item["evidence"]),
                    prop("review", item["review_status"]),
                ],
            }
        )
    images = re.findall(r"^FROM\s+(\S+)", (root / "Dockerfile").read_text(), re.MULTILINE)
    images += re.findall(r"^FROM\s+(\S+)", (root / "Dockerfile.preview").read_text(), re.MULTILINE)
    images += re.findall(
        r"^\s+image:\s*(\S+)", (root / "docker-compose.yml").read_text(), re.MULTILINE
    )
    for image in sorted(set(images)):
        components.append(
            {
                "type": "container",
                "bom-ref": "image:" + image,
                "name": image,
                "properties": [
                    prop("digest", "unresolved"),
                    prop("inventory", "declared-image-only"),
                ],
            }
        )
    components.sort(key=lambda item: item["bom-ref"])
    root_dependencies = [c["bom-ref"] for c in components if not c["bom-ref"].startswith("npm:")]
    for group in ("dependencies", "devDependencies", "optionalDependencies"):
        for name in npm_manifest.get(group, {}):
            resolved = npm_resolve(lock["packages"], "", name)
            if resolved is None:
                raise ValueError("Missing direct npm package: " + name)
            root_dependencies.append(resolved)
    dependencies.append({"ref": "project:judgeai", "dependsOn": sorted(set(root_dependencies))})
    services = [
        {
            "bom-ref": "provider:" + str(i),
            "name": item["name"],
            "externalReferences": [{"type": "website", "url": safe_url(item["source_url"])}],
            "properties": [prop("usage", item["usage"]), prop("review", item["review_status"])],
        }
        for i, item in enumerate(resources["providers"])
    ]
    bom = {
        "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": "project:judgeai",
                "name": manifest["project"]["name"],
                "version": manifest["project"]["version"],
            },
            "properties": [
                prop("inventory-scope", "source-declarations-and-npm-lock-not-runtime"),
                prop("python-resolution", "unresolved"),
                prop("project-license", resources["project_license"]),
                *[
                    prop(
                        "input-sha256:" + path,
                        hashlib.sha256((root / path).read_bytes()).hexdigest(),
                    )
                    for path in INPUTS
                ],
            ],
        },
        "components": components,
        "services": services,
        "dependencies": sorted(dependencies, key=lambda item: item["ref"]),
    }
    license_counts: dict[str, int] = {}
    for component in npm:
        license_name = component.get("licenses", [{}])[0].get("expression", "unknown")
        license_counts[license_name] = license_counts.get(license_name, 0) + 1
    development_count = sum(prop("development", "true") in c["properties"] for c in npm)
    lines = [
        "# Generated dependency inventory",
        "",
        "Source inventory only; not a resolved runtime SBOM or legal approval.",
        "",
        f"- Python declared packages (runtime/dev/build, deduplicated): **{python_count}**; "
        "exact installed versions: **0 verified**.",
        f"- npm lock entries: **{len(npm)}**; development entries: **{development_count}**.",
        f"- Official legal archives: **{len(legal_sources)}**; "
        f"image declarations: **{len(set(images))}**; "
        f"model: **{model_name}**, revision unresolved.",
        "",
        "## npm license metadata",
        "",
        "| Declaration | Entries |",
        "|---|---:|",
    ]
    lines += [f"| {name} | {count} |" for name, count in sorted(license_counts.items())]
    lines += [
        "",
        "## Python declarations",
        "",
        "| Package | Constraints (not installed versions) | Upstream license |",
        "|---|---|---|",
    ]
    for component in components:
        if component["bom-ref"].startswith("pypi:"):
            constraints = sorted(
                {
                    p["value"]
                    for p in component["properties"]
                    if p["name"] == "judgeai:declared-requirement"
                }
            )
            lines.append(
                f"| {component['name']} | {', '.join(constraints)} | "
                f"{component['licenses'][0]['expression']} |"
            )
    lines += ["", "## Document preview runtime", ""]
    lines += [
        "- " + item["name"] + ": " + item["license_notice"] + ". " + item["evidence"]
        for item in resources.get("preview_runtime", [])
    ]
    lines += ["", "## Open decisions and release blockers", ""] + [
        "- " + gap for gap in resources["gaps"]
    ]
    lines += [
        "",
        "Regenerate: `python3 tools/dependency_inventory.py`; "
        "verify: `python3 tools/dependency_inventory.py --check`.",
        "",
    ]
    return bom, "\n".join(lines)


def generate(root: Path, *, check: bool = False) -> bool:
    bom, report = build_inventory(root)
    outputs = {
        "docs/compliance/sbom.cdx.json": json.dumps(bom, ensure_ascii=False, indent=2) + "\n",
        "docs/compliance/INVENTORY.md": report,
    }
    valid = True
    for relative, content in outputs.items():
        path = root / relative
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                print("Inventory drift: " + relative, file=sys.stderr)
                valid = False
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    return valid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        ok = generate(args.root, check=args.check)
    except (ValueError, KeyError, OSError) as exc:
        print(f"Inventory validation failed: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(2) from None
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
