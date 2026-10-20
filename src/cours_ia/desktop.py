"""Appli de bureau : le serveur local tourne en arrière-plan, l'interface s'affiche dans une vraie fenêtre
(WebKit sur Mac, WebView2 sur Windows). Fermer la fenêtre quitte l'appli."""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from . import config, llm, pipeline
from .server import app

HOME = Path(os.environ.get("COURS_IA_HOME", Path.home() / ".cours-ia"))


def _free_port(preferred: int) -> int:
    # port fixe de préférence : le navigateur intégré garde les préférences (thème…) par origine
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("aucun port libre")


def start_server(port: int) -> uvicorn.Server:
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True, name="coursia-server").start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    return server


class Api:
    """Fonctions appelables depuis la page (window.pywebview.api.*)."""

    def __init__(self):
        self._window = None  # privé : pywebview n'expose pas les attributs « _ » à la page

    def save_file(self, name: str, content: str) -> str | None:
        import webview

        kind = getattr(getattr(webview, "FileDialog", None), "SAVE", None) or webview.SAVE_DIALOG
        res = self._window.create_file_dialog(kind, save_filename=name)
        if not res:
            return None
        path = res if isinstance(res, str) else res[0]
        Path(path).write_text(content, encoding="utf-8")
        return path

    def open_url(self, url: str) -> None:
        webbrowser.open(url)


def _mac_dock_icon() -> None:
    icon = os.environ.get("COURS_IA_ICON")
    if sys.platform != "darwin" or not icon:
        return
    try:
        from AppKit import NSApplication, NSImage

        NSApplication.sharedApplication().setApplicationIconImage_(NSImage.alloc().initWithContentsOfFile_(icon))
    except Exception:  # noqa: BLE001 — purement cosmétique
        pass


def run() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    config.LESSONS_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["COURS_IA_DESKTOP"] = "1"
    pipeline.start_worker()
    port = _free_port(int(os.environ.get("COURS_IA_PORT", "8765")))
    start_server(port)
    url = f"http://127.0.0.1:{port}/"
    # Codex absent : on l'installe en arrière-plan pendant que l'interface s'ouvre
    threading.Thread(target=lambda: _safe(llm.ensure_codex), daemon=True).start()

    try:
        import webview
    except ImportError:
        webbrowser.open(url)
        while True:
            time.sleep(3600)

    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    if "ALLOW_DOWNLOADS" in webview.settings:
        webview.settings["ALLOW_DOWNLOADS"] = True
    api = Api()
    api._window = webview.create_window("Cours IA", url, width=1380, height=900, min_size=(940, 620),
                                       js_api=api, text_select=True, background_color="#F7F4EE")
    HOME.mkdir(parents=True, exist_ok=True)
    webview.start(_mac_dock_icon, private_mode=False, storage_path=str(HOME / "webview"))
    os._exit(0)  # fenêtre fermée : on arrête aussi le serveur et les traitements


def _safe(fn):
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        print(f"Installation de Codex impossible : {e}", flush=True)
