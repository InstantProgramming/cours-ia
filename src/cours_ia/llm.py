"""Appels LLM : Codex CLI (abonnement ChatGPT) en priorité, OpenRouter / Anthropic en secours.

Toutes les fonctions renvoient du JSON validé par un schéma : on demande au modèle une
réponse structurée et on la relit, pour que le pipeline ne dépende pas de texte libre.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx


class LLMError(RuntimeError):
    pass


# ---------------------------------------------------------------- Codex CLI

BUNDLED_CODEX = Path(os.environ.get("COURS_IA_HOME", Path.home() / ".cours-ia")) / "bin" / "codex"
CODEX_RELEASE = "https://github.com/openai/codex/releases/latest/download/codex-aarch64-apple-darwin.tar.gz"


def find_codex() -> str | None:
    global _codex_path
    if _codex_path and Path(_codex_path).exists():
        return _codex_path
    _codex_path = _search_codex()
    return _codex_path


_codex_path: str | None = None


def _search_codex() -> str | None:
    if os.environ.get("CODEX_BIN"):
        return os.environ["CODEX_BIN"]
    found = shutil.which("codex")
    if found:
        return found
    candidates: list[str] = []
    if platform.system() == "Darwin":
        candidates += [str(BUNDLED_CODEX), "/Applications/Codex.app/Contents/Resources/codex",
                       "/opt/homebrew/bin/codex", "/usr/local/bin/codex",
                       str(Path.home() / ".local/bin/codex")]
    elif platform.system() == "Windows":
        candidates += [str(Path(os.environ.get("APPDATA", "")) / "npm" / "codex.cmd")]
        # app Codex du Microsoft Store : WindowsApps n'est pas listable, on demande le chemin au système
        try:
            loc = subprocess.run(["powershell", "-NoProfile", "-Command",
                                  "(Get-AppxPackage OpenAI.Codex).InstallLocation"],
                                 capture_output=True, text=True, timeout=20).stdout.strip()
            if loc:
                candidates.append(str(Path(loc) / "app" / "resources" / "codex.exe"))
        except (OSError, subprocess.TimeoutExpired):
            pass
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def codex_status() -> dict:
    exe = find_codex()
    if not exe:
        return {"ok": False, "detail": "Codex introuvable. Installe l'app Codex ou `brew install --cask codex`."}
    try:
        out = subprocess.run([exe, "login", "status"], capture_output=True, text=True, timeout=30,
                             encoding="utf-8", errors="replace")
        txt = (out.stdout + out.stderr).strip()
        return {"ok": out.returncode == 0 and "Logged in" in txt, "detail": txt, "path": exe}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": str(e), "path": exe}


def _codex_json(prompt: str, schema: dict, cfg: dict, *, web: bool, model: str | None,
                effort: str | None, timeout: int, log=None) -> dict:
    exe = find_codex()
    if not exe:
        raise LLMError("Codex CLI introuvable")
    with tempfile.TemporaryDirectory(prefix="coursia-") as tmp:
        tmp_path = Path(tmp)
        schema_file = tmp_path / "schema.json"
        out_file = tmp_path / "out.json"
        schema_file.write_text(json.dumps(schema), encoding="utf-8")
        cmd = [exe]
        if web:
            cmd.append("--search")
        cmd += ["exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only",
                "-C", str(tmp_path), "--output-schema", str(schema_file),
                "-o", str(out_file), "--json", "--color", "never"]
        model = model or cfg.get("codex_model")
        if model:
            cmd += ["-m", model]
        effort = effort or cfg.get("codex_reasoning")
        if effort:
            cmd += ["-c", f'model_reasoning_effort="{effort}"']
        if not web:
            cmd += ["-c", 'web_search="disabled"']
        cmd.append("-")
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace")
        assert proc.stdin and proc.stdout
        proc.stdin.write(prompt)
        proc.stdin.close()
        errors: list[str] = []
        try:
            for line in proc.stdout:
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                item = ev.get("item") or {}
                if log and ev.get("type") == "item.completed" and item.get("type") == "web_search":
                    q = item.get("query") or (item.get("action") or {}).get("url") or ""
                    if q:
                        log(f"🔎 Recherche web : {q[:120]}")
                if ev.get("type") in ("error", "turn.failed"):
                    errors.append(json.dumps(ev, ensure_ascii=False)[:500])
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise LLMError("Codex : délai dépassé")
        if not out_file.exists() or not out_file.read_text(encoding="utf-8").strip():
            err = proc.stderr.read() if proc.stderr else ""
            raise LLMError("Codex n'a pas répondu. " + " | ".join(errors) + err[-800:])
        return _parse_json(out_file.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- API de secours

def _openai_compatible_json(prompt: str, schema: dict, *, url: str, key: str, model: str,
                            timeout: int, extra: dict | None = None) -> dict:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "reponse", "strict": True, "schema": schema}},
        **(extra or {}),
    }
    r = httpx.post(url, json=body, timeout=timeout, headers={"Authorization": f"Bearer {key}"})
    r.raise_for_status()
    return _parse_json(r.json()["choices"][0]["message"]["content"])


def _anthropic_json(prompt: str, schema: dict, cfg: dict, timeout: int) -> dict:
    body = {
        "model": cfg["anthropic_model"],
        "max_tokens": 32000,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {"format": {"type": "json_schema", "schema": schema}},
    }
    r = httpx.post("https://api.anthropic.com/v1/messages", json=body, timeout=timeout,
                   headers={"x-api-key": cfg["anthropic_api_key"], "anthropic-version": "2023-06-01"})
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")
    return _parse_json(text)


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    try:
        return json.loads(text[start:end + 1])
    except (json.JSONDecodeError, ValueError) as e:
        raise LLMError(f"Réponse JSON invalide : {e}: {text[:300]}") from e


# ---------------------------------------------------------------- point d'entrée

def ask_json(prompt: str, schema: dict, cfg: dict, *, web: bool = False, model: str | None = None,
             effort: str | None = None, timeout: int = 1800, log=None, retries: int = 1) -> dict:
    """Envoie `prompt` et renvoie un dict conforme à `schema`."""
    provider = cfg.get("llm_provider", "codex")
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            if provider == "codex":
                return _codex_json(prompt, schema, cfg, web=web and cfg.get("web_research", True),
                                   model=model, effort=effort, timeout=timeout, log=log)
            if provider == "openrouter":
                extra = {"plugins": [{"id": "web"}]} if web and cfg.get("web_research", True) else None
                return _openai_compatible_json(prompt, schema, url="https://openrouter.ai/api/v1/chat/completions",
                                               key=cfg["openrouter_api_key"], model=cfg["openrouter_model"],
                                               timeout=timeout, extra=extra)
            if provider == "anthropic":
                return _anthropic_json(prompt, schema, cfg, timeout)
            raise LLMError(f"Fournisseur inconnu : {provider}")
        except (LLMError, httpx.HTTPError, KeyError) as e:
            last = e
            # quota de l'abonnement atteint : on bascule sur le modèle rapide, aux limites bien plus larges
            if provider == "codex" and QUOTA_RE.search(str(e)) and model != FALLBACK_MODEL:
                if log:
                    log(f"⚠️ Quota ChatGPT atteint : bascule sur le modèle rapide ({FALLBACK_MODEL})")
                return ask_json(prompt, schema, cfg, web=web, model=FALLBACK_MODEL, effort="medium",
                                timeout=timeout, log=log, retries=0)
            if log and attempt < retries:
                log(f"⚠️ Appel LLM raté ({e}), nouvel essai…")
    raise LLMError(str(last))


FALLBACK_MODEL = "gpt-6-luna"
QUOTA_RE = re.compile(r"usage limit|rate.?limit|quota|429|too many requests", re.I)


def ensure_codex(log=print) -> str | None:
    """Mac : si Codex n'est pas installé, télécharge le CLI officiel (release GitHub d'OpenAI)."""
    exe = find_codex()
    if exe or platform.system() != "Darwin":
        return exe
    import io
    import tarfile

    log("Installation de Codex (l'IA de ChatGPT)…")
    data = httpx.get(CODEX_RELEASE, follow_redirects=True, timeout=300).raise_for_status().content
    BUNDLED_CODEX.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        member = next(m for m in tar.getmembers() if m.isfile() and Path(m.name).name.startswith("codex"))
        BUNDLED_CODEX.write_bytes(tar.extractfile(member).read())
    BUNDLED_CODEX.chmod(0o755)
    return find_codex()


def codex_login() -> None:
    """Lance `codex login` : ouvre la page de connexion ChatGPT dans le navigateur."""
    exe = ensure_codex()
    if not exe:
        raise LLMError("Codex introuvable")
    subprocess.Popen([exe, "login"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
