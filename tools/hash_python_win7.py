#!/usr/bin/env python3
"""tools/hash_python_win7.py — regeneruje packaging/python-win7.json.

Pobiera installery Python-Win7 (Alex313031) z przypiętego commita i oblicza
SHA256 + rozmiar (supply-chain pin dla release.yml). Uruchamiane RĘCZNIE przez
maintainera przy zmianie wersji Pythona; wynik commitowany do repo.

Użycie:  python tools/hash_python_win7.py [--version 3.13.5] [--commit <sha>]
Wymaga tylko stdlib (urllib). Baseline składni: Python 3.8.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.request

REPO = "Alex313031/Python-Win7"
FILES = {
    "amd64": "python-{ver}-amd64-full.exe",
    "win32": "python-{ver}-full.exe",
}
HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "..", "build", "python-win7.json")
UA = {"User-Agent": "dongstack-tools/1.0"}


def latest_commit_for(path: str) -> str:
    url = "https://api.github.com/repos/%s/commits?path=%s&per_page=1" % (REPO, path)
    req = urllib.request.Request(url, headers=dict(UA, **{"Accept": "application/vnd.github+json"}))
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return data[0]["sha"]


def download_sha256(url: str) -> "tuple":
    h = hashlib.sha256()
    size = 0
    with tempfile.TemporaryFile() as tmp:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=180) as r:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                tmp.write(chunk)
                h.update(chunk)
                size += len(chunk)
    return h.hexdigest(), size


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="3.13.5")
    ap.add_argument(
        "--commit", default=None, help="domyślnie: ostatni commit dotykający katalogu wersji"
    )
    args = ap.parse_args()

    ver_dir = args.version
    commit = args.commit or latest_commit_for(ver_dir)
    print("repo=%s commit=%s version=%s" % (REPO, commit, args.version))

    files = {}
    for arch, pattern in FILES.items():
        name = pattern.format(ver=args.version)
        url = "https://raw.githubusercontent.com/%s/%s/%s/%s" % (REPO, commit, ver_dir, name)
        print("pobieram %s ..." % name)
        sha, size = download_sha256(url)
        files[arch] = {"name": name, "size": size, "sha256": sha}
        print("  size=%d sha256=%s" % (size, sha))

    manifest = {
        "_comment": (
            "Pin zaufania dla CI: build Python-Win7 (Alex313031). Checksumy obliczone "
            "praktycznie przez tools/hash_python_win7.py. CI odmawia buildu przy niezgodności SHA256."
        ),
        "repo": REPO,
        "commit": commit,
        "version": args.version,
        "files": files,
        "verified_on": __import__("datetime").date.today().isoformat(),
        "regenerate": "python tools/hash_python_win7.py",
    }
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("zapisano %s" % os.path.abspath(MANIFEST))
    return 0


if __name__ == "__main__":
    sys.exit(main())
