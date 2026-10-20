"""Serveur web local (http://127.0.0.1:8765) : API + interface."""

from __future__ import annotations

import os
import shutil
import sys
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, config, llm, notes, pipeline, revision, transcribe, updater

WEB = Path(__file__).parent / "web"
app = FastAPI(title="Cours IA")


@app.middleware("http")
async def no_cache_ui(request, call_next):
    # l'interface est servie en local : toujours la dernière version après une mise à jour
    response = await call_next(request)
    if not request.url.path.startswith(("/media/", "/api/")):
        response.headers["Cache-Control"] = "no-cache"
    return response


_codex_cache: dict = {"t": 0.0, "v": None}


def _codex_status() -> dict:
    # `codex login status` lance un processus : on garde le résultat quelques secondes s'il est bon
    if _codex_cache["v"] and _codex_cache["v"]["ok"] and time.time() - _codex_cache["t"] < 60:
        return _codex_cache["v"]
    _codex_cache.update(t=time.time(), v=llm.codex_status())
    return _codex_cache["v"]


@app.get("/api/status")
def status():
    cfg = config.load()
    engines = transcribe.available_engines()
    return {
        "version": __version__,
        "desktop": bool(os.environ.get("COURS_IA_DESKTOP")),
        "update": updater.check_quietly(),
        "codex": _codex_status(),
        "engines": engines,
        "engine_auto": next((e for e in engines if e not in ("elevenlabs", "mistral")), None),
        "apple_silicon": transcribe.IS_APPLE_SILICON,
        "hyperframes": pipeline.hyperframes_available(),
        "config": config.public(cfg),
        "data_dir": str(config.DATA_DIR),
    }


@app.post("/api/config")
def set_config(values: dict):
    # ne pas écraser une clé API avec sa version masquée
    clean = {k: v for k, v in values.items() if not (isinstance(v, str) and v.startswith("••••"))}
    return config.public(config.save(clean))


@app.get("/api/lessons")
def lessons():
    return pipeline.list_lessons()


@app.post("/api/lessons")
async def new_lesson(title: str = Form(""), hint: str = Form(""), url: str = Form(""),
                     file: UploadFile | None = File(None)):
    if not url and not file:
        raise HTTPException(400, "Donne une vidéo ou un lien")
    lid = pipeline.create_lesson(title.strip(), hint.strip(), url=url.strip() or None,
                                 upload_name=file.filename if file else None)
    if file:
        ext = Path(file.filename or "video.mp4").suffix.lower() or ".mp4"
        dest = pipeline.lesson_dir(lid) / f"video{ext}"
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out, length=8 * 1024 * 1024)
        pipeline.update_meta(lid, media=dest.name)
    pipeline.enqueue(lid)
    return {"id": lid}


@app.get("/api/lessons/{lid}")
def lesson(lid: str):
    d = _dir(lid)
    rj = pipeline.read_json
    return {
        "meta": rj(d / "meta.json", {}),
        "transcript": rj(d / "transcript.json"),
        "notes": rj(d / "notes.json"),
        "deep": rj(d / "deep.json"),
        "animations": rj(d / "animations.json"),
        "renders": rj(d / "renders.json", {}),
        "user": rj(d / "user.json", {}),
    }


class Patch(BaseModel):
    title: str


@app.patch("/api/lessons/{lid}")
def rename(lid: str, body: Patch):
    _dir(lid)
    return pipeline.update_meta(lid, title=body.title.strip()[:200], title_auto=False)


class Reveal(BaseModel):
    path: str = ""


@app.post("/api/lessons/{lid}/reveal")
def reveal(lid: str, body: Reveal | None = None):
    """Montre le dossier du cours (ou un fichier) dans le Finder / l'Explorateur."""
    d = _dir(lid).resolve()
    target = (d / body.path).resolve() if body and body.path else d
    if target != d and d not in target.parents:
        raise HTTPException(400)
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(target)] if target.is_file() else ["open", str(target)])
    elif sys.platform == "win32":
        subprocess.Popen(["explorer", f"/select,{target}"] if target.is_file() else ["explorer", str(target)])
    return {"ok": True}


# ---------------------------------------------------------------- révision espacée

@app.get("/api/review")
def review():
    return revision.due_cards()


class Grade(BaseModel):
    lid: str
    idx: int
    ok: bool


@app.post("/api/review/grade")
def grade(body: Grade):
    _dir(body.lid)
    return revision.grade(body.lid, body.idx, body.ok)


# ---------------------------------------------------------------- compte ChatGPT & mises à jour

@app.post("/api/codex/login")
def codex_login():
    try:
        llm.codex_login()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Impossible de lancer la connexion : {e}")
    _codex_cache.update(v=None)
    return {"ok": True}


@app.get("/api/update")
def update_check(force: int = 0):
    try:
        return updater.check(force=bool(force))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, str(e))


@app.post("/api/update/install")
def update_install():
    try:
        return {"version": updater.install()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, str(e))


@app.delete("/api/lessons/{lid}")
def delete(lid: str):
    _dir(lid)
    pipeline.delete_lesson(lid)
    return {"ok": True}


class Rerun(BaseModel):
    from_step: str = "notes"


@app.post("/api/lessons/{lid}/rerun")
def rerun(lid: str, body: Rerun):
    _dir(lid)
    if body.from_step not in pipeline.STEPS:
        raise HTTPException(400, "étape inconnue")
    pipeline.enqueue(lid, body.from_step)
    return {"ok": True}


class FixDiagram(BaseModel):
    code: str
    error: str
    where: str  # "section:<id>" | "concept_map"


@app.post("/api/lessons/{lid}/fix-diagram")
def fix_diagram(lid: str, body: FixDiagram):
    d = _dir(lid)
    code = notes.fix_diagram(body.code, body.error, config.load())
    n = pipeline.read_json(d / "notes.json")
    if body.where == "concept_map":
        n["concept_map"]["code"] = code
    else:
        for s in n["sections"]:
            if f"section:{s['id']}" == body.where:
                s["diagram"]["code"] = code
    pipeline.write_json(d / "notes.json", n)
    return {"code": code}


class Ask(BaseModel):
    question: str
    history: list[dict] = []


ASK_SCHEMA = notes.obj(answer_md=notes.STR, timestamps=notes.arr(notes.NUM))


@app.post("/api/lessons/{lid}/ask")
def ask(lid: str, body: Ask):
    """Tuteur : répond aux questions de l'étudiante en s'appuyant sur le cours (et le web si besoin)."""
    d = _dir(lid)
    tr = pipeline.read_json(d / "transcript.json") or {"segments": []}
    n = pipeline.read_json(d / "notes.json") or {}
    hist = "\n".join(f"{m['role']}: {m['content']}" for m in body.history[-6:])
    prompt = (
        f"Tu es un tuteur bienveillant et rigoureux. L'étudiante révise le cours « {n.get('title', '')} » "
        f"({n.get('subject', '')}). Réponds en français, clairement, avec un exemple si utile. Appuie-toi d'abord "
        "sur le cours ; si tu complètes avec tes connaissances ou le web, dis-le et cite la source. "
        "timestamps = moments de la vidéo (en secondes) où le prof en parle.\n\n"
        f"RÉSUMÉ\n{n.get('summary_md', '')}\n\nTRANSCRIPTION\n{notes.transcript_text(tr['segments'])}\n\n"
        f"ÉCHANGE PRÉCÉDENT\n{hist}\n\nQUESTION\n{body.question}"
    )
    return llm.ask_json(prompt, ASK_SCHEMA, config.load(), web=True, effort="medium", timeout=600)


@app.post("/api/lessons/{lid}/user")
def save_user(lid: str, data: dict):
    """Données de révision : cartes maîtrisées, scores de quiz, notes perso."""
    d = _dir(lid)
    cur = pipeline.read_json(d / "user.json", {}) or {}
    cur.update(data)
    pipeline.write_json(d / "user.json", cur)
    return cur


@app.post("/api/lessons/{lid}/animations/{idx}/render")
def render(lid: str, idx: int):
    _dir(lid)
    if not pipeline.hyperframes_available():
        raise HTTPException(400, "Node.js et FFmpeg sont requis pour exporter en vidéo (relance l'installateur)")
    pipeline.render_animation(lid, idx)
    return {"ok": True}


@app.get("/api/lessons/{lid}/export.md", response_class=PlainTextResponse)
def export_md(lid: str):
    _dir(lid)
    md = pipeline.export_markdown(lid)
    return PlainTextResponse(md, headers={"Content-Disposition": f'attachment; filename="{lid}.md"'})


@app.get("/media/{lid}/{path:path}")
def media(lid: str, path: str):
    d = _dir(lid).resolve()
    f = (d / path).resolve()
    if d not in f.parents or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)


def _dir(lid: str) -> Path:
    try:
        d = pipeline.lesson_dir(lid)
    except ValueError:
        raise HTTPException(400, "identifiant invalide")
    if not d.exists():
        raise HTTPException(404, "cours introuvable")
    return d


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")


def main() -> None:
    """Mode serveur seul (développement, ou COURS_IA_NO_WINDOW=1) : ouvre le navigateur."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    config.LESSONS_DIR.mkdir(parents=True, exist_ok=True)
    pipeline.start_worker()
    port = int(os.environ.get("COURS_IA_PORT", "8765"))
    if not os.environ.get("COURS_IA_NO_BROWSER"):
        threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
