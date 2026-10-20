"""Transcription horodatée (+ diarisation optionnelle), moteur choisi selon la machine.

Benchmark (oct. 2026) — voir docs/benchmark.md :
  Mac Apple Silicon : Parakeet TDT 0.6B v3 (MLX)  → WER FR ≈ 5,4 %, très rapide
                      Whisper large-v3-turbo (MLX) → langue forcée + glossaire (plan B)
                      Nemotron-3-Diarization (MLX) → qui parle quand
  PC NVIDIA        : faster-whisper large-v3-turbo (CUDA)
  Cloud            : ElevenLabs Scribe v2 (meilleur FR), Mistral Voxtral (le moins cher)
"""

from __future__ import annotations

import platform
from pathlib import Path

import httpx

IS_APPLE_SILICON = platform.system() == "Darwin" and platform.machine() == "arm64"

DEFAULT_MODELS = {
    "parakeet": "mlx-community/parakeet-tdt-0.6b-v3",
    "mlx-whisper": "mlx-community/whisper-large-v3-turbo",
    "faster-whisper": "large-v3-turbo",
    "elevenlabs": "scribe_v2",
    "mistral": "voxtral-mini-latest",
}


def available_engines() -> list[str]:
    engines = []
    try:
        if IS_APPLE_SILICON:
            import parakeet_mlx  # noqa: F401
            engines.append("parakeet")
    except ImportError:
        pass
    try:
        if IS_APPLE_SILICON:
            import mlx_whisper  # noqa: F401
            engines.append("mlx-whisper")
    except ImportError:
        pass
    try:
        import faster_whisper  # noqa: F401
        engines.append("faster-whisper")
    except ImportError:
        pass
    return engines + ["elevenlabs", "mistral"]


def pick_engine(cfg: dict) -> str:
    engine = cfg.get("asr_engine", "auto")
    if engine != "auto":
        return engine
    local = [e for e in available_engines() if e not in ("elevenlabs", "mistral")]
    if local:
        return local[0]
    if cfg.get("elevenlabs_api_key"):
        return "elevenlabs"
    if cfg.get("mistral_api_key"):
        return "mistral"
    raise RuntimeError("Aucun moteur de transcription disponible : installe les dépendances locales "
                       "ou renseigne une clé ElevenLabs / Mistral dans les réglages.")


def transcribe(wav: Path, cfg: dict, *, glossary: str = "", log=print) -> dict:
    """Renvoie {"engine", "model", "language", "segments": [{start, end, text, speaker?}]}."""
    engine = pick_engine(cfg)
    model = cfg.get("asr_model") or DEFAULT_MODELS[engine]
    lang = cfg.get("language") or "fr"
    log(f"Transcription avec {engine} ({model})…")
    if engine == "parakeet":
        segs = _parakeet(wav, model, log)
    elif engine == "mlx-whisper":
        segs = _mlx_whisper(wav, model, lang, glossary)
    elif engine == "faster-whisper":
        segs = _faster_whisper(wav, model, lang, glossary, log)
    elif engine == "elevenlabs":
        segs = _elevenlabs(wav, model, lang, cfg, diarize=cfg.get("diarization", False))
    elif engine == "mistral":
        segs = _mistral(wav, model, lang, cfg, diarize=cfg.get("diarization", False))
    else:
        raise RuntimeError(f"Moteur inconnu : {engine}")

    if cfg.get("diarization") and engine not in ("elevenlabs", "mistral"):
        try:
            log("Identification des intervenants (diarisation)…")
            turns = diarize(wav)
            segs = assign_speakers(segs, turns)
        except Exception as e:  # noqa: BLE001 — la diarisation est un bonus, jamais bloquante
            log(f"⚠️ Diarisation indisponible : {e}")
    segs = [s for s in segs if s["text"].strip()]
    return {"engine": engine, "model": model, "language": lang, "segments": segs}


# ---------------------------------------------------------------- moteurs locaux

def _parakeet(wav: Path, model: str, log) -> list[dict]:
    from parakeet_mlx import from_pretrained

    m = from_pretrained(model)
    result = m.transcribe(str(wav), chunk_duration=120, overlap_duration=15)
    return [{"start": float(s.start), "end": float(s.end), "text": s.text.strip()} for s in result.sentences]


def _mlx_whisper(wav: Path, model: str, lang: str, glossary: str) -> list[dict]:
    import mlx_whisper

    r = mlx_whisper.transcribe(str(wav), path_or_hf_repo=model, language=lang,
                               initial_prompt=glossary or None, condition_on_previous_text=False)
    return [{"start": float(s["start"]), "end": float(s["end"]), "text": s["text"].strip()} for s in r["segments"]]


def _faster_whisper(wav: Path, model: str, lang: str, glossary: str, log) -> list[dict]:
    _add_nvidia_dll_dirs()
    from faster_whisper import WhisperModel

    try:
        m = WhisperModel(model, device="cuda", compute_type="int8_float16")
    except Exception as e:  # noqa: BLE001 — pas de GPU utilisable : CPU, plus lent
        log(f"GPU indisponible ({e}), transcription sur CPU (plus lent)…")
        m = WhisperModel(model, device="cpu", compute_type="int8")
    # on passe le signal décodé : évite le décodeur PyAV de faster-whisper (incompatible avec PyAV récent)
    segments, info = m.transcribe(read_wav(wav), language=lang, vad_filter=True, beam_size=5,
                                  initial_prompt=glossary or None, condition_on_previous_text=False)
    out = []
    for s in segments:
        out.append({"start": s.start, "end": s.end, "text": s.text.strip()})
        if info.duration:
            log(f"Transcription… {fmt(s.end)} / {fmt(info.duration)}", progress=min(s.end / info.duration, 1))
    return out


def read_wav(wav: Path):
    """WAV mono 16 kHz 16 bits (produit par ingest.extract_audio) → numpy float32."""
    import wave

    import numpy as np

    with wave.open(str(wav), "rb") as w:
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def _add_nvidia_dll_dirs() -> None:
    """Windows : rend visibles les DLL cuBLAS/cuDNN installées par pip (nvidia-*-cu12)."""
    if platform.system() != "Windows":
        return
    import os
    import site

    for base in site.getsitepackages():
        nv = Path(base) / "nvidia"
        for bin_dir in nv.glob("*/bin"):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


def diarize(wav: Path) -> list[tuple[float, float, str]]:
    if IS_APPLE_SILICON:
        from mlx_audio.vad import load

        d = load("mlx-community/Nemotron-3-Diarization", strict=True)
        return [(float(g.start), float(g.end), f"Intervenant {int(g.speaker) + 1}")
                for r in d.generate_stream(str(wav)) for g in r.segments]
    import os

    import torch
    from pyannote.audio import Pipeline

    p = Pipeline.from_pretrained("pyannote/speaker-diarization-community-1", token=os.environ.get("HF_TOKEN"))
    if torch.cuda.is_available():
        p.to(torch.device("cuda"))
    out = p(str(wav))
    return [(t.start, t.end, spk) for t, spk in out.exclusive_speaker_diarization]


def assign_speakers(segs: list[dict], turns: list[tuple[float, float, str]]) -> list[dict]:
    for s in segs:
        overlap: dict[str, float] = {}
        for a, b, spk in turns:
            o = min(s["end"], b) - max(s["start"], a)
            if o > 0:
                overlap[spk] = overlap.get(spk, 0) + o
        if overlap:
            s["speaker"] = max(overlap, key=overlap.get)
    return segs


# ---------------------------------------------------------------- moteurs cloud

def _words_to_segments(words: list[dict], max_gap: float = 1.2, max_len: float = 20.0) -> list[dict]:
    """Regroupe des mots horodatés en phrases (fin de phrase, pause ou changement d'intervenant)."""
    segs: list[dict] = []
    cur: dict | None = None
    for w in words:
        text, start, end, spk = w["text"], w["start"], w["end"], w.get("speaker")
        new = (cur is None or start - cur["end"] > max_gap or spk != cur.get("speaker")
               or (end - cur["start"] > max_len) or cur["text"].rstrip().endswith((".", "?", "!")))
        if new and text.strip():
            cur = {"start": start, "end": end, "text": text.strip(), **({"speaker": spk} if spk else {})}
            segs.append(cur)
        elif cur is not None:
            cur["text"] += text
            cur["end"] = end
    for s in segs:
        s["text"] = " ".join(s["text"].split())
    return segs


def _elevenlabs(wav: Path, model: str, lang: str, cfg: dict, diarize: bool) -> list[dict]:
    lang3 = {"fr": "fra", "en": "eng"}.get(lang, lang)
    with wav.open("rb") as f:
        r = httpx.post("https://api.elevenlabs.io/v1/speech-to-text", timeout=3600,
                       headers={"xi-api-key": cfg["elevenlabs_api_key"]},
                       data={"model_id": model, "language_code": lang3, "diarize": str(diarize).lower(),
                             "timestamps_granularity": "word", "tag_audio_events": "false"},
                       files={"file": (wav.name, f, "audio/wav")})
    r.raise_for_status()
    words = []
    for w in r.json().get("words", []):
        if w.get("type") == "audio_event":
            continue
        spk = w.get("speaker_id")
        words.append({"text": w["text"], "start": w["start"], "end": w["end"],
                      "speaker": f"Intervenant {spk.split('_')[-1]}" if diarize and spk else None})
    return _words_to_segments(words)


def _mistral(wav: Path, model: str, lang: str, cfg: dict, diarize: bool) -> list[dict]:
    data = [("model", model), ("language", lang), ("timestamp_granularities", "segment")]
    if diarize:
        data.append(("diarize", "true"))
    with wav.open("rb") as f:
        r = httpx.post("https://api.mistral.ai/v1/audio/transcriptions", timeout=3600,
                       headers={"Authorization": f"Bearer {cfg['mistral_api_key']}"},
                       data=data, files={"file": (wav.name, f, "audio/wav")})
    r.raise_for_status()
    out = []
    for s in r.json().get("segments", []):
        seg = {"start": float(s["start"]), "end": float(s["end"]), "text": s["text"].strip()}
        if s.get("speaker_id") is not None:
            seg["speaker"] = f"Intervenant {s['speaker_id']}"
        out.append(seg)
    return out


def fmt(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"
