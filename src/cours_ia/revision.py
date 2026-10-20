"""Révision espacée (système de Leitner) sur les flashcards de tous les cours.

Chaque carte a une boîte (0 à 5) ; « je savais » la fait monter, « à revoir » la renvoie en boîte 1.
La boîte fixe le délai avant la prochaine révision.
"""

from __future__ import annotations

import datetime as dt

from . import config, pipeline

INTERVALS = [0, 1, 3, 7, 16, 35]  # jours, par boîte
MASTERED_BOX = 3


def _today() -> str:
    return dt.date.today().isoformat()


def card_state(user: dict, idx: int) -> dict:
    return (user.get("srs") or {}).get(str(idx)) or {"box": 0, "due": _today()}


def stats(notes: dict | None, user: dict | None) -> dict:
    cards = (notes or {}).get("flashcards") or []
    user = user or {}
    states = [card_state(user, i) for i in range(len(cards))]
    return {
        "cards": len(cards),
        "mastered": sum(s["box"] >= MASTERED_BOX for s in states),
        "due": sum(s["due"] <= _today() for s in states),
    }


def due_cards(limit: int = 60) -> dict:
    due, total = [], 0
    if config.LESSONS_DIR.exists():
        for d in sorted(config.LESSONS_DIR.iterdir()):
            notes = pipeline.read_json(d / "notes.json")
            if not notes:
                continue
            user = pipeline.read_json(d / "user.json", {}) or {}
            meta = pipeline.read_json(d / "meta.json", {}) or {}
            for i, c in enumerate(notes.get("flashcards") or []):
                total += 1
                s = card_state(user, i)
                if s["due"] <= _today():
                    due.append({"lid": d.name, "idx": i, "front": c["front"], "back": c["back"],
                                "lesson_title": meta.get("title") or notes.get("title"), "box": s["box"]})
    # les cartes les moins sues d'abord, en mélangeant les cours
    due.sort(key=lambda c: (c["box"], hash((c["lid"], c["idx"])) % 997))
    return {"due": due[:limit], "count": len(due), "total": total}


def grade(lid: str, idx: int, ok: bool) -> dict:
    d = pipeline.lesson_dir(lid)
    user = pipeline.read_json(d / "user.json", {}) or {}
    srs = user.setdefault("srs", {})
    s = card_state(user, idx)
    box = min(s["box"] + 1, len(INTERVALS) - 1) if ok else 1
    days = INTERVALS[box] if ok else 0  # ratée : on la revoit dans la même session / aujourd'hui
    srs[str(idx)] = {"box": box, "due": (dt.date.today() + dt.timedelta(days=days)).isoformat()}
    pipeline.write_json(d / "user.json", user)
    return srs[str(idx)]
