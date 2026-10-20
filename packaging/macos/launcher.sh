#!/bin/bash
# Lanceur de « Cours IA.app » (Contents/MacOS/CoursIA).
# 1. installe/choisit la version du code la plus récente (celle du .app ou une mise à jour téléchargée) ;
# 2. installe Python et les dépendances au premier lancement / après une mise à jour (uv) ;
# 3. démarre l'appli (fenêtre native).
set -u

BUNDLE="$(cd "$(dirname "$0")/../.." && pwd)"
RES="$BUNDLE/Contents/Resources"
export COURS_IA_HOME="$HOME/Library/Application Support/CoursIA"
export COURS_IA_BUNDLE="$BUNDLE"
export COURS_IA_ICON="$RES/AppIcon.icns"
export PATH="$RES/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export UV_PROJECT_ENVIRONMENT="$COURS_IA_HOME/venv"
export UV_PYTHON_INSTALL_DIR="$COURS_IA_HOME/python"
export UV_CACHE_DIR="$COURS_IA_HOME/cache"
export UV_PYTHON_PREFERENCE=only-managed
export UV_NO_PROGRESS=1
export PYTHONUNBUFFERED=1
UV="$RES/bin/uv"

mkdir -p "$COURS_IA_HOME/versions" "$COURS_IA_HOME/logs"
LOG="$COURS_IA_HOME/logs/launcher.log"
# journal : on garde les ~2000 dernières lignes
[ -f "$LOG" ] && tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exec >>"$LOG" 2>&1
echo "=== $(date '+%Y-%m-%d %H:%M:%S') — lancement depuis $BUNDLE"

notify() { osascript -e "display notification \"$1\" with title \"Cours IA\"" >/dev/null 2>&1 || true; }
fail() {
  osascript -e "display alert \"Cours IA n'a pas pu démarrer\" message \"$1

Détails : ~/Library/Application Support/CoursIA/logs/launcher.log\" as critical" >/dev/null 2>&1
  exit 1
}
# vrai si la version $1 est strictement plus récente que $2
newer() { [ "$1" != "$2" ] && [ "$(printf '%s\n%s\n' "$1" "$2" | sort -t. -k1,1n -k2,2n -k3,3n | tail -1)" = "$1" ]; }

BUNDLED="$(cat "$RES/version")"
CURRENT="$(cat "$COURS_IA_HOME/current" 2>/dev/null || true)"
if [ -z "$CURRENT" ] || [ ! -f "$COURS_IA_HOME/versions/$CURRENT/pyproject.toml" ] || newer "$BUNDLED" "$CURRENT"; then
  echo "Installation du code $BUNDLED (contenu dans le .app)"
  rm -rf "$COURS_IA_HOME/versions/$BUNDLED"
  mkdir -p "$COURS_IA_HOME/versions/$BUNDLED"
  tar -xzf "$RES/app.tar.gz" -C "$COURS_IA_HOME/versions/$BUNDLED" || fail "Copie des fichiers impossible."
  echo "$BUNDLED" > "$COURS_IA_HOME/current"
  CURRENT="$BUNDLED"
fi
APP="$COURS_IA_HOME/versions/$CURRENT"
echo "Version utilisée : $CURRENT"

# dépendances : seulement au premier lancement ou quand la version change
STAMP="$COURS_IA_HOME/venv/.ok-$CURRENT"
if [ ! -f "$STAMP" ]; then
  if [ -d "$COURS_IA_HOME/venv" ]; then
    notify "Mise à jour vers la version $CURRENT…"
  else
    notify "Première ouverture : installation en cours (3 à 5 minutes). La fenêtre s'ouvrira toute seule."
  fi
  "$UV" sync --frozen --project "$APP" || fail "L'installation a échoué. Vérifie ta connexion internet, puis relance Cours IA."
  rm -f "$COURS_IA_HOME/venv/.ok-"*
  touch "$STAMP"
  # ménage : on ne garde que la version courante et la précédente
  ls -1t "$COURS_IA_HOME/versions" | tail -n +3 | while read -r old; do
    [ "$old" != "$CURRENT" ] && rm -rf "$COURS_IA_HOME/versions/$old"
  done
fi

cd "$APP" || fail "Dossier de l'appli introuvable."
exec "$UV" run --frozen --no-sync --project "$APP" python -m cours_ia
