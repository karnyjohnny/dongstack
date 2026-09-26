#!/usr/bin/env python3
"""tools/freeze_hashes.py — generuje requirements.lock.txt z hashami kół (decyzja D8).

Mechanika: `pip download` dla docelowych platform Windows (win_amd64 + win32) i Pythona 3.13
(Track A), tylko koła binarne (--only-binary=:all:), następnie SHA256 każdego pobranego pliku
i scalenie hashy per pakiet. Wynik: requirements.lock.txt do `pip install --require-hashes`
w release.yml.

Użycie:  python tools/freeze_hashes.py
Wymaga: pip w środowisku uruchamiającym (dowolny OS — pobiera koła Windows cross-platformowo).
Baseline składni: Python 3.8.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
from typing import Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
REQ_IN = os.path.join(ROOT, "requirements.txt")
LOCK_OUT = os.path.join(ROOT, "requirements.lock.txt")

PLATFORMS = ["win_amd64", "win32"]
PY_VERSION = "3.13"
ABIS = ["cp313", "abi3", "none"]

_WHEEL_NAME = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+?)-(?P<ver>[^-]+)-")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pip_download(dest: str, platform: str) -> None:
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "-r",
        REQ_IN,
        "-d",
        dest,
        "--only-binary=:all:",
        "--python-version",
        PY_VERSION,
        "--implementation",
        "cp",
        "--disable-pip-version-check",
        "--no-input",
        "--platform",
        platform,
    ]
    for a in ABIS:
        cmd += ["--abi", a]
    print("pip download [%s]: %s" % (platform, " ".join(cmd)))
    subprocess.check_call(cmd)


def main() -> int:
    hashes: Dict[str, List[str]] = {}
    versions: Dict[str, str] = {}
    for platform in PLATFORMS:
        with tempfile.TemporaryDirectory(prefix="dongstack-lock-%s-" % platform) as tmp:
            _pip_download(tmp, platform)
            for fname in sorted(os.listdir(tmp)):
                m = _WHEEL_NAME.match(fname)
                if not m:
                    print("pomijam (nie wheel):", fname)
                    continue
                name = _norm(m.group("name"))
                ver = m.group("ver")
                if name in versions and versions[name] != ver:
                    print("BŁĄD: rozjazd wersji %s: %s vs %s" % (name, versions[name], ver))
                    return 1
                versions[name] = ver
                dig = _sha256(os.path.join(tmp, fname))
                if dig not in hashes.setdefault(name, []):
                    hashes[name].append(dig)

    if not hashes:
        print("BŁĄD: nic nie pobrano")
        return 1

    lines = [
        "# DongStack — requirements.lock.txt",
        "# WYGENEROWANE przez tools/freeze_hashes.py — NIE edytować ręcznie.",
        "# Track A: Python 3.13 (win_amd64 + win32). Instalacja: pip install --require-hashes -r requirements.lock.txt",
        "# (decyzja D8: hashowanie wyłącznie dla runtime w release.yml; dev bez hashowania)",
        "",
    ]
    for name in sorted(hashes):
        ver = versions[name]
        hlist = " ".join("--hash=sha256:%s" % h for h in sorted(set(hashes[name])))
        lines.append("%s==%s %s" % (name, ver, hlist))
    with open(LOCK_OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("zapisano %s (%d pakietów)" % (LOCK_OUT, len(hashes)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
