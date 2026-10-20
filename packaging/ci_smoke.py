"""Test sur un vrai Mac (GitHub Actions) : transcription MLX, diarisation, téléchargement de Codex.

Usage : python packaging/ci_smoke.py audio.aiff
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from cours_ia import ingest, llm, transcribe

results = {}
wav = Path(tempfile.mkdtemp()) / "audio.wav"
ingest.extract_audio(Path(sys.argv[1]), wav)

for engine in ("parakeet", "mlx-whisper"):
    t0 = time.time()
    try:
        r = transcribe.transcribe(wav, {"asr_engine": engine, "language": "fr"}, log=lambda *a, **k: None)
        results[engine] = {"ok": True, "s": round(time.time() - t0, 1), "text": " ".join(s["text"] for s in r["segments"])}
    except Exception as e:  # noqa: BLE001
        results[engine] = {"ok": False, "error": repr(e)[:500]}

try:
    turns = transcribe.diarize(wav)
    results["diarisation"] = {"ok": True, "turns": len(turns)}
except Exception as e:  # noqa: BLE001
    results["diarisation"] = {"ok": False, "error": repr(e)[:500]}

try:
    llm.BUNDLED_CODEX = Path(tempfile.mkdtemp()) / "bin" / "codex"
    llm._codex_path = None
    llm._search_codex = lambda: str(llm.BUNDLED_CODEX) if llm.BUNDLED_CODEX.exists() else None
    exe = llm.ensure_codex(log=lambda *a: None)
    out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60)
    results["codex"] = {"ok": out.returncode == 0, "version": out.stdout.strip()}
except Exception as e:  # noqa: BLE001
    results["codex"] = {"ok": False, "error": repr(e)[:500]}

print(json.dumps(results, ensure_ascii=False, indent=2))
sys.exit(0 if results["parakeet"]["ok"] and results["codex"]["ok"] else 1)
