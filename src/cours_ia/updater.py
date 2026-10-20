"""Mises à jour via les releases GitHub du projet.

Le .app contient une copie du code ; au lancement, le lanceur (packaging/macos/launcher.sh) utilise la
version la plus récente entre celle du .app et celle installée dans ~/Library/Application Support/CoursIA.
Mettre à jour = télécharger l'archive source de la dernière release dans versions/<v>, l'indiquer dans
`current`, puis relancer l'appli (le lanceur installe les nouvelles dépendances si besoin).
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path

import httpx

from . import __version__

REPO = os.environ.get("COURS_IA_REPO", "InstantProgramming/cours-ia")
HOME = Path(os.environ.get("COURS_IA_HOME", Path.home() / ".cours-ia"))
_cache: dict = {"t": 0.0, "data": None}


def parse(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.lstrip("v").split(".") if x.isdigit())


def check(force: bool = False) -> dict:
    """Interroge GitHub (au plus une fois par heure)."""
    if not force and _cache["data"] and time.time() - _cache["t"] < 3600:
        return _cache["data"]
    r = httpx.get(f"https://api.github.com/repos/{REPO}/releases/latest", timeout=15,
                  headers={"Accept": "application/vnd.github+json"}, follow_redirects=True)
    r.raise_for_status()
    rel = r.json()
    latest = rel["tag_name"].lstrip("v")
    src = next((a["browser_download_url"] for a in rel.get("assets", []) if a["name"].endswith(".tar.gz")), None)
    data = {"current": __version__, "latest": latest, "available": parse(latest) > parse(__version__) and bool(src),
            "notes": (rel.get("body") or "").strip(), "source_url": src}
    _cache.update(t=time.time(), data=data)
    return data


def check_quietly() -> dict:
    try:
        return check()
    except Exception as e:  # noqa: BLE001 — hors ligne, GitHub indisponible… : pas bloquant
        data = {"current": __version__, "available": False, "error": str(e)}
        _cache.update(t=time.time() - 3000, data=data)  # on réessaiera dans ~10 min
        return data


def install(on_done=None) -> str:
    info = check(force=True)
    if not info["available"]:
        raise RuntimeError("Aucune mise à jour disponible")
    data = httpx.get(info["source_url"], follow_redirects=True, timeout=600).raise_for_status().content
    dest = HOME / "versions" / info["latest"]
    tmp = dest.with_name(dest.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(tmp, filter="data")
    # l'archive peut contenir un dossier racine unique
    inner = list(tmp.iterdir())
    root = inner[0] if len(inner) == 1 and inner[0].is_dir() and not (tmp / "pyproject.toml").exists() else tmp
    if not (root / "pyproject.toml").exists():
        raise RuntimeError("Archive de mise à jour invalide")
    if dest.exists():
        shutil.rmtree(dest)
    root.rename(dest)
    shutil.rmtree(tmp, ignore_errors=True)
    (HOME / "current").write_text(info["latest"], encoding="utf-8")
    threading.Timer(1.0, relaunch).start()
    return info["latest"]


def relaunch() -> None:
    """Relance l'appli (le lanceur prendra la nouvelle version), puis quitte celle-ci."""
    bundle = os.environ.get("COURS_IA_BUNDLE")
    if bundle and sys.platform == "darwin":
        subprocess.Popen(["/bin/sh", "-c", f'sleep 2; open -n "{bundle}"'], start_new_session=True)
    os._exit(0)
