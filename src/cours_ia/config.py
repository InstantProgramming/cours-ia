"""Réglages persistants (fichier JSON dans le dossier de données)."""

from __future__ import annotations

import json
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("COURS_IA_DATA", Path.home() / "Documents" / "CoursIA"))
LESSONS_DIR = DATA_DIR / "cours"
CONFIG_FILE = DATA_DIR / "config.json"

DEFAULTS: dict = {
    # Transcription : "auto" choisit le meilleur moteur local selon la machine
    "asr_engine": "auto",           # auto | mlx | faster-whisper | elevenlabs | mistral
    "asr_model": "",                # vide = modèle par défaut du moteur
    "diarization": False,           # identifier les intervenants (plus lent)
    "language": "fr",
    # LLM : Codex via l'abonnement ChatGPT, ou API en secours
    "llm_provider": "codex",        # codex | openrouter | anthropic
    "codex_model": "",              # vide = modèle par défaut de Codex
    "codex_reasoning": "high",      # low | medium | high
    "web_research": True,           # Codex peut chercher sur le web pour approfondir
    "openrouter_api_key": "",
    "openrouter_model": "anthropic/claude-sonnet-5.5",
    "anthropic_api_key": "",
    "anthropic_model": "claude-sonnet-5-5",
    "elevenlabs_api_key": "",
    "mistral_api_key": "",
    "explainer_videos": True,       # vidéos explicatives HyperFrames (si Node installé)
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return cfg


def save(values: dict) -> dict:
    cfg = load()
    cfg.update({k: v for k, v in values.items() if k in DEFAULTS})
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def public(cfg: dict) -> dict:
    """Config renvoyée au navigateur : on masque les clés API."""
    return {k: ("••••" + v[-4:] if k.endswith("_api_key") and v else v) for k, v in cfg.items()}
