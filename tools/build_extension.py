"""Package the browser extension.

    python tools/build_extension.py            # writes dist/extension/*.zip

Makes two zips from extension/:
  hyperget-extension-<version>-store.zip  for the Chrome Web Store and Edge Add-ons
                                          (in-page video download off on YouTube)
  hyperget-extension-<version>-full.zip   the complete extension, shipped inside
                                          the HyperGet download for "Load unpacked"
"""
from __future__ import annotations

import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "extension")
OUT = os.path.join(ROOT, "dist", "extension")
SKIP_DIRS = {"store", "__pycache__"}
SKIP_FILES = {".DS_Store", "Thumbs.db"}
MAX_ICON = {"16": 16, "32": 32, "48": 48, "128": 128}


def check(manifest: dict) -> None:
    problems = []
    if manifest.get("manifest_version") != 3:
        problems.append("manifest_version must be 3")
    if not re.fullmatch(r"\d+(\.\d+){0,3}", manifest.get("version", "")):
        problems.append("version must be 1-4 dot-separated numbers")
    if len(manifest.get("name", "")) > 75:
        problems.append("name is longer than 75 characters")
    if len(manifest.get("description", "")) > 132:
        problems.append("description is longer than 132 characters (store limit)")
    for size, path in manifest.get("icons", {}).items():
        if not os.path.isfile(os.path.join(SRC, path)):
            problems.append(f"missing icon {path}")
    for cs in manifest.get("content_scripts", []):
        for js in cs.get("js", []):
            if not os.path.isfile(os.path.join(SRC, js)):
                problems.append(f"missing content script {js}")
    sw = manifest.get("background", {}).get("service_worker")
    if sw and not os.path.isfile(os.path.join(SRC, sw)):
        problems.append(f"missing service worker {sw}")
    if problems:
        sys.exit("manifest problems:\n  " + "\n  ".join(problems))


def files():
    for dirpath, dirnames, filenames in os.walk(SRC):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name in SKIP_FILES:
                continue
            full = os.path.join(dirpath, name)
            yield full, os.path.relpath(full, SRC).replace(os.sep, "/")


def build(store: bool, version: str) -> str:
    os.makedirs(OUT, exist_ok=True)
    flavour = "store" if store else "full"
    path = os.path.join(OUT, f"hyperget-extension-{version}-{flavour}.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for full, rel in files():
            if rel == "config.js":
                text = open(full, encoding="utf-8").read()
                text, n = re.subn(r"(HYPERGET_BUILD\s*=\s*\{\s*store:\s*)(true|false)",
                                 lambda m: m.group(1) + ("true" if store else "false"), text, count=1)
                if n != 1:
                    sys.exit("config.js: HYPERGET_BUILD.store not found")
                text = re.sub(r'version:\s*"[^"]*"', f'version: "{version}"', text, count=1)
                z.writestr(rel, text)
            else:
                z.write(full, rel)
    return path


def main() -> None:
    manifest = json.load(open(os.path.join(SRC, "manifest.json"), encoding="utf-8"))
    check(manifest)
    version = manifest["version"]
    for store in (True, False):
        p = build(store, version)
        print(f"{os.path.relpath(p, ROOT)}  ({os.path.getsize(p) // 1024} KB)")


if __name__ == "__main__":
    main()
