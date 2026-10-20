"""Récupération de la vidéo (fichier local ou lien) et extraction de l'audio."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg


def ffmpeg_bin() -> str:
    """ffmpeg système si présent, sinon le binaire embarqué par imageio-ffmpeg."""
    return shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()


def download_url(url: str, dest_dir: Path, log=print) -> tuple[Path, str]:
    """Télécharge une vidéo (YouTube & co) avec yt-dlp. Renvoie (fichier, titre)."""
    import yt_dlp

    dest_dir.mkdir(parents=True, exist_ok=True)

    def hook(d):
        if d.get("status") == "downloading" and d.get("total_bytes"):
            pct = 100 * d.get("downloaded_bytes", 0) / d["total_bytes"]
            log(f"Téléchargement… {pct:.0f} %", progress=pct / 100)

    opts = {
        # vidéo légère (≤720p) pour la relecture + audio ; repli sur le meilleur format unique
        "format": "bv*[height<=720]+ba/b[height<=720]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(dest_dir / "video.%(ext)s"),
        "ffmpeg_location": ffmpeg_bin(),
        "progress_hooks": [hook],
        "quiet": True,
        "noprogress": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
    if not path.exists():  # après fusion, l'extension peut changer
        candidates = sorted(dest_dir.glob("video.*"))
        path = candidates[0]
    meta = {
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "description": (info.get("description") or "")[:3000],
        "chapters": info.get("chapters"),
        "duration": info.get("duration"),
        "url": url,
    }
    (dest_dir / "source.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, info.get("title") or "Cours"


def extract_audio(video: Path, wav: Path) -> Path:
    """Audio mono 16 kHz WAV : le format attendu par tous les modèles ASR."""
    cmd = [ffmpeg_bin(), "-y", "-loglevel", "error", "-i", str(video),
           "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)]
    subprocess.run(cmd, check=True)
    return wav


def media_duration(path: Path) -> float:
    """Durée en secondes (lue dans la sortie de ffmpeg, pas besoin de ffprobe)."""
    proc = subprocess.run([ffmpeg_bin(), "-i", str(path)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    for line in proc.stderr.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            h, m, s = line.split(",")[0].split()[1].split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0


def make_browser_friendly(video: Path, out: Path) -> Path:
    """Les navigateurs lisent mal MKV/AVI : on remuxe/transcode en MP4 si besoin."""
    if video.suffix.lower() in {".mp4", ".m4v", ".webm", ".mov", ".mp3", ".m4a", ".wav", ".ogg"}:
        return video
    subprocess.run([ffmpeg_bin(), "-y", "-loglevel", "error", "-i", str(video),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                    "-vf", "scale=-2:'min(720,ih)'", "-c:a", "aac", "-b:a", "128k", str(out)], check=True)
    return out
