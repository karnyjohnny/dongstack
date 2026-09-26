"""Testy pinów supply-chain i spójności infrastruktury freeze/CI (M6, §9)."""

from __future__ import annotations

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def test_python_win7_manifest_schema():
    m = json.loads(_read("packaging/python-win7.json"))
    assert m["repo"] == "Alex313031/Python-Win7"
    assert re.fullmatch(r"[0-9a-f]{40}", m["commit"])
    for arch in ("amd64", "win32"):
        f = m["files"][arch]
        assert re.fullmatch(r"[0-9a-f]{64}", f["sha256"]), arch
        assert f["size"] > 10_000_000
        assert f["name"].endswith(".exe")
    # amd64 = artefakt główny (D1), win32 = zasięg
    assert "amd64" in m["files"]["amd64"]["name"]


def test_lock_covers_every_runtime_requirement():
    req = _read("requirements.txt")
    lock = _read("requirements.lock.txt")
    pinned = re.findall(r"^([A-Za-z0-9_.-]+)==([0-9][0-9A-Za-z.\-+]*)", req, flags=re.M)
    pinned = [(n.lower().replace("_", "-"), v) for n, v in pinned]
    lock_lines = [ln for ln in lock.splitlines() if ln and not ln.startswith("#")]
    lock_names = {}
    for ln in lock_lines:
        name_ver, hashes = ln.split(" ", 1)
        name, ver = name_ver.split("==")
        lock_names[name.lower()] = (ver, re.findall(r"--hash=sha256:([0-9a-f]{64})", hashes))
    pinned_versions: dict = {}
    for name, ver in pinned:
        pinned_versions.setdefault(name, set()).add(ver)
    for name, versions in pinned_versions.items():
        if name not in lock_names:
            continue  # np. PyQt5-sip<3.10 — poza Track A (lock budowany dla py3.13)
        lver, hashes = lock_names[name]
        assert lver in versions, "%s: lock %s spoza pinów %s" % (name, lver, versions)
        assert hashes, name
    # pakiety binarne mają hash-e OBU architektur Windows (D1: matrix amd64+win32)
    for name in ("pyqt5", "pyqt5-qt5", "pyqt5-sip"):
        _, hashes = lock_names[name]
        assert len(hashes) >= 2, "%s: oczekiwano hash-y win_amd64+win32" % name


def test_version_info_in_sync_with_package():
    import app

    vi = _read("packaging/version_info.txt")
    major, minor, patch = (int(x) for x in app.__version__.split(".")[:3])
    assert "filevers=(%d, %d, %d, 0)" % (major, minor, patch) in vi
    assert "'%d.%d.%d.0'" % (major, minor, patch) in vi  # FileVersion/ProductVersion


def test_spec_references_existing_paths():
    spec = _read("packaging/dongstack.spec")
    assert 'ENTRY = os.path.join(ROOT, "app", "main.py")' in spec
    assert os.path.isfile(os.path.join(ROOT, "app", "main.py"))
    assert os.path.isfile(os.path.join(ROOT, "app", "resources", "icons", "app.ico"))
    assert os.path.isfile(os.path.join(ROOT, "packaging", "version_info.txt"))
    for sub in ("styles", "icons"):
        assert os.path.isdir(os.path.join(ROOT, "app", "resources", sub))
    # rygory §8.2 zakodowane w specu
    assert "upx=False" in spec and "console=False" in spec
    assert "PyQt5.QtSvg" in spec and "PyQt5.QtNetwork" in spec  # excludes


def test_workflows_reference_pinned_assets():
    rel = _read(".github/workflows/release.yml")
    assert "packaging/python-win7.json" in rel
    assert "packaging\\dongstack.spec" in rel or "packaging/dongstack.spec" in rel
    assert "--require-hashes" in rel and "requirements.lock.txt" in rel
    assert "DHT_ONEFILE" in rel
    ci = _read(".github/workflows/ci.yml")
    assert "QT_QPA_PLATFORM" in ci and "ruff" in ci


def test_gitignore_protects_secrets_and_artifacts():
    gi = _read(".gitignore")
    assert ".env" in gi.splitlines()
    for pat in ("dist/", "dist-onefile/", "*.sqlite", "__pycache__/"):
        assert pat in gi
