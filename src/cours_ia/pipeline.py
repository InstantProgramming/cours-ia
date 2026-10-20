"""Orchestration : une file de travail, des étapes reprenables, un dossier par cours."""

from __future__ import annotations

import json
import platform
import queue
import re
import shutil
import subprocess
import threading
import time
import traceback
import unicodedata
import uuid
from pathlib import Path

from . import config, ingest, notes, revision, transcribe

STEPS = ["source", "audio", "transcript", "notes", "deep", "animations"]
STEP_LABELS = {
    "source": "Récupération de la vidéo",
    "audio": "Extraction de l'audio",
    "transcript": "Transcription",
    "notes": "Fiche de cours",
    "deep": "Approfondissements & vérifications",
    "animations": "Animations explicatives",
}

_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
_lock = threading.Lock()


# ---------------------------------------------------------------- stockage

def lesson_dir(lid: str) -> Path:
    if not re.fullmatch(r"[a-z0-9-]+", lid):
        raise ValueError("identifiant invalide")
    return config.LESSONS_DIR / lid


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def update_meta(lid: str, **fields) -> dict:
    with _lock:
        path = lesson_dir(lid) / "meta.json"
        meta = read_json(path, {})
        meta.update(fields)
        write_json(path, meta)
        return meta


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "cours"


def create_lesson(title: str, hint: str = "", url: str | None = None, upload_name: str | None = None) -> str:
    lid = f"{time.strftime('%Y%m%d')}-{slugify(title or upload_name or 'cours')}-{uuid.uuid4().hex[:4]}"
    d = lesson_dir(lid)
    d.mkdir(parents=True)
    write_json(d / "meta.json", {
        "id": lid, "title": title or (Path(upload_name).stem if upload_name else "Cours"),
        "title_auto": not title, "course_hint": hint, "url": url, "created": time.time(), "status": "en attente",
        "steps": {s: "todo" for s in STEPS}, "log": [], "progress": 0,
    })
    return lid


def list_lessons() -> list[dict]:
    if not config.LESSONS_DIR.exists():
        return []
    out = []
    for d in config.LESSONS_DIR.iterdir():
        meta = read_json(d / "meta.json")
        if meta:
            n = read_json(d / "notes.json", {}) or {}
            subject = n.get("subject") or ""
            out.append({k: meta.get(k) for k in ("id", "title", "created", "status", "duration", "steps", "progress")}
                       | {"subject": subject, "one_line": n.get("one_line"),
                          # « Droit des obligations — Droit des contrats » → regroupé sous « Droit des obligations »
                          "subject_group": subject.split(" — ")[0].split(" - ")[0].strip() or None}
                       | revision.stats(n, read_json(d / "user.json", {})))
    return sorted(out, key=lambda m: m.get("created") or 0, reverse=True)


def delete_lesson(lid: str) -> None:
    """Pas de suppression définitive : le dossier part dans la corbeille de l'appli."""
    trash = config.DATA_DIR / "corbeille"
    trash.mkdir(parents=True, exist_ok=True)
    shutil.move(str(lesson_dir(lid)), str(trash / lid))


# ---------------------------------------------------------------- notifications

def notify(title: str, body: str = "") -> None:
    """Notification système (macOS) ; silencieux ailleurs."""
    if platform.system() != "Darwin":
        return
    q = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')  # noqa: E731
    subprocess.Popen(["osascript", "-e", f'display notification "{q(body)}" with title "{q(title)}" sound name "Glass"'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------- file de travail

def enqueue(lid: str, from_step: str = "source") -> None:
    meta = read_json(lesson_dir(lid) / "meta.json", {})
    steps = meta.get("steps", {})
    start = STEPS.index(from_step)
    for s in STEPS[start:]:
        steps[s] = "todo"
    update_meta(lid, steps=steps, status="en attente", error=None)
    _queue.put((lid, from_step))


def start_worker() -> None:
    threading.Thread(target=_worker, daemon=True, name="coursia-worker").start()
    # reprendre ce qui a été interrompu (appli fermée en cours de traitement)
    for m in list_lessons():
        if m["status"] not in ("terminé", "erreur"):
            first = next((s for s in STEPS if (m.get("steps") or {}).get(s) != "done"), None)
            if first:
                _queue.put((m["id"], first))


def _worker() -> None:
    while True:
        lid, from_step = _queue.get()
        try:
            run(lid, from_step)
        except Exception as e:  # noqa: BLE001
            update_meta(lid, status="erreur", error=str(e))
            notify("⚠️ Problème pendant l'analyse", read_json(lesson_dir(lid) / "meta.json", {}).get("title", ""))
            traceback.print_exc()
            _log(lid, f"❌ {e}")
        finally:
            _queue.task_done()


def _log(lid: str, msg: str, progress: float | None = None) -> None:
    with _lock:
        path = lesson_dir(lid) / "meta.json"
        meta = read_json(path, {})
        logs = meta.get("log", [])
        # les messages de progression répétés remplacent la ligne précédente
        if logs and msg.split("…")[0] == logs[-1]["msg"].split("…")[0] and "…" in msg:
            logs[-1] = {"t": time.time(), "msg": msg}
        else:
            logs.append({"t": time.time(), "msg": msg})
        meta["log"] = logs[-200:]
        if progress is not None:
            meta["step_progress"] = progress
        write_json(path, meta)
    try:
        print(f"[{lid}] {msg}", flush=True)
    except (UnicodeEncodeError, OSError):
        pass


# ---------------------------------------------------------------- étapes

def run(lid: str, from_step: str = "source") -> None:
    d = lesson_dir(lid)
    cfg = config.load()

    def log(msg, progress=None):
        _log(lid, msg, progress)

    for step in STEPS[STEPS.index(from_step):]:
        meta = read_json(d / "meta.json", {})
        if step == "animations" and not cfg.get("explainer_videos", True):
            _set_step(lid, step, "skipped")
            continue
        _set_step(lid, step, "running")
        update_meta(lid, status=STEP_LABELS[step], step_progress=None)
        t0 = time.time()
        log(f"▶ {STEP_LABELS[step]}")
        try:
            STEP_FUNCS[step](d, meta, cfg, log)
        except Exception:
            _set_step(lid, step, "error")
            raise
        _set_step(lid, step, "done")
        log(f"✔ {STEP_LABELS[step]} ({time.time() - t0:.0f} s)")
        if step == "notes":
            notify("📝 Ta fiche est prête", read_json(d / "meta.json", {}).get("title", ""))
    update_meta(lid, status="terminé", progress=1, step_progress=None)
    notify("✅ Cours prêt", f"{read_json(d / 'meta.json', {}).get('title', '')} : explications et animations terminées")


def _set_step(lid: str, step: str, state: str) -> None:
    meta = read_json(lesson_dir(lid) / "meta.json", {})
    steps = meta.get("steps", {})
    steps[step] = state
    done = sum(1 for s in STEPS if steps.get(s) in ("done", "skipped"))
    update_meta(lid, steps=steps, progress=done / len(STEPS))


def step_source(d: Path, meta: dict, cfg: dict, log) -> None:
    if meta.get("url") and not meta.get("media"):
        path, title = ingest.download_url(meta["url"], d, log=lambda m, progress=None: log(m, progress))
        fields = {"media": path.name, "source": read_json(d / "source.json", {})}
        if meta.get("title_auto"):
            fields["title"] = title
        meta.update(fields)
        update_meta(meta["id"], **fields)
    media = d / meta["media"]
    playable = ingest.make_browser_friendly(media, d / "video_web.mp4")
    update_meta(meta["id"], playable=playable.name, duration=ingest.media_duration(media))


def step_audio(d: Path, meta: dict, cfg: dict, log) -> None:
    ingest.extract_audio(d / meta["media"], d / "audio.wav")


def step_transcript(d: Path, meta: dict, cfg: dict, log) -> None:
    # Le titre et les précisions orientent le vocabulaire (Whisper : initial_prompt)
    glossary = ". ".join(x for x in [meta.get("title"), meta.get("course_hint")] if x)
    result = transcribe.transcribe(d / "audio.wav", cfg, glossary=glossary, log=log)
    write_json(d / "transcript.json", result)
    words = sum(len(s["text"].split()) for s in result["segments"])
    log(f"{len(result['segments'])} segments, {words} mots transcrits")


def step_notes(d: Path, meta: dict, cfg: dict, log) -> None:
    tr = read_json(d / "transcript.json")
    result = notes.build_notes(tr["segments"], meta, cfg, log)
    write_json(d / "notes.json", result)
    if result.get("title") and meta.get("title_auto"):
        update_meta(meta["id"], title=result["title"])


def step_deep(d: Path, meta: dict, cfg: dict, log) -> None:
    n = read_json(d / "notes.json")
    write_json(d / "deep.json", notes.deepen(n, cfg, log))


def step_animations(d: Path, meta: dict, cfg: dict, log) -> None:
    n = read_json(d / "notes.json")
    deep = read_json(d / "deep.json", {}) or {}
    result = notes.animations(n, deep, cfg, log)
    for i, a in enumerate(result.get("animations", [])):
        adir = d / f"anim_{i}"
        adir.mkdir(exist_ok=True)
        (adir / "index.html").write_text(a["html"], encoding="utf-8")
        a["file"] = f"anim_{i}/index.html"
        a.pop("html")
    write_json(d / "animations.json", result)


STEP_FUNCS = {"source": step_source, "audio": step_audio, "transcript": step_transcript,
              "notes": step_notes, "deep": step_deep, "animations": step_animations}


# ---------------------------------------------------------------- export vidéo HyperFrames

def hyperframes_available() -> bool:
    # HyperFrames encode avec le FFmpeg/FFprobe du système (pas celui embarqué par imageio-ffmpeg)
    return all(shutil.which(b) for b in ("npx", "ffmpeg", "ffprobe"))


def render_animation(lid: str, idx: int) -> None:
    """Rend une animation en MP4 avec HyperFrames (Node 22 + Chrome, téléchargés au besoin)."""
    d = lesson_dir(lid)
    adir = d / f"anim_{idx}"

    def go():
        renders = read_json(d / "renders.json", {}) or {}
        renders[str(idx)] = {"status": "running"}
        write_json(d / "renders.json", renders)
        npx = shutil.which("npx")
        try:
            proc = subprocess.run([npx, "--yes", "hyperframes@latest", "render", "--output", "video.mp4",
                                   "--quality", "standard"], cwd=adir, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=1800)
            ok = proc.returncode == 0 and (adir / "video.mp4").exists()
            renders[str(idx)] = {"status": "done" if ok else "error",
                                 "file": f"anim_{idx}/video.mp4" if ok else None,
                                 "detail": "" if ok else (proc.stdout + proc.stderr)[-2000:]}
        except Exception as e:  # noqa: BLE001
            renders[str(idx)] = {"status": "error", "detail": str(e)}
        write_json(d / "renders.json", renders)

    threading.Thread(target=go, daemon=True).start()


# ---------------------------------------------------------------- export Markdown

def export_markdown(lid: str) -> str:
    d = lesson_dir(lid)
    meta = read_json(d / "meta.json", {})
    n = read_json(d / "notes.json", {}) or {}
    deep = read_json(d / "deep.json", {}) or {}
    out = [f"# {n.get('title') or meta.get('title')}", "", f"*{n.get('one_line', '')}*", "",
           "## Résumé", n.get("summary_md", ""), "", f"**Problématique** : {n.get('problematique', '')}", ""]
    for s in n.get("sections", []):
        out += [f"## {s['title']}  ({notes.fmt_ts(s['start'])})", s["notes_md"], ""]
        if s.get("diagram", {}).get("kind") == "mermaid":
            out += ["```mermaid", s["diagram"]["code"], "```", ""]
    if n.get("definitions"):
        out += ["## Lexique"] + [f"- **{x['term']}** : {x['definition']}" for x in n["definitions"]] + [""]
    for e in deep.get("explanations", []):
        out += [f"## Pour bien comprendre : {e['concept']}", e["simple_md"], "",
                f"*Analogie* : {e['analogy']}", "", f"*Exemple* : {e['example']}", "", e["expert_md"], ""]
        out += [f"- [{s['title']}]({s['url']})" for s in e.get("sources", [])] + [""]
    if n.get("exam_questions"):
        out += ["## Sujets d'examen probables"]
        for q in n["exam_questions"]:
            out += [f"### {q['question']}", q["answer_outline_md"], ""]
    return "\n".join(out)
