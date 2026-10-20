#!/bin/bash
# Construit « Cours IA.app » et « CoursIA-<version>.dmg » dans dist/ (à lancer sur macOS, Apple Silicon).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/cours_ia/__init__.py)"
UV_URL="${UV_URL:-https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-apple-darwin.tar.gz}"
DIST="$ROOT/dist"
APP="$DIST/Cours IA.app"
echo "→ Cours IA $VERSION"

rm -rf "$DIST" && mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/bin"

# 1. archive du code (c'est aussi l'archive des mises à jour publiée dans la release)
tar --exclude "__pycache__" -czf "$DIST/cours-ia-$VERSION.tar.gz" pyproject.toml uv.lock .python-version README.md src
cp "$DIST/cours-ia-$VERSION.tar.gz" "$APP/Contents/Resources/app.tar.gz"
echo "$VERSION" > "$APP/Contents/Resources/version"

# 2. lanceur + Info.plist
cp packaging/macos/launcher.sh "$APP/Contents/MacOS/CoursIA"
chmod +x "$APP/Contents/MacOS/CoursIA"
sed "s/__VERSION__/$VERSION/g" packaging/macos/Info.plist > "$APP/Contents/Info.plist"

# 3. uv (binaire officiel signé d'Astral)
curl -fsSL "$UV_URL" | tar -xz -C "$DIST"
cp "$DIST/uv-aarch64-apple-darwin/uv" "$APP/Contents/Resources/bin/uv"
chmod +x "$APP/Contents/Resources/bin/uv"
rm -rf "$DIST/uv-aarch64-apple-darwin"

# 4. icône
"$APP/Contents/Resources/bin/uv" run --no-project --with pillow python packaging/make_icon.py "$DIST/icon.png"
ICONSET="$DIST/AppIcon.iconset"; mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$DIST/icon.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s * 2)) $((s * 2)) "$DIST/icon.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"
rm -rf "$ICONSET" "$DIST/icon.png"

# 5. signature ad hoc (pas de compte développeur Apple : macOS demandera une confirmation au 1er lancement)
codesign --force --deep --sign - "$APP" || echo "⚠️ signature ad hoc impossible (non bloquant)"

# 6. image disque : l'appli, un raccourci « Applications » et la notice
STAGE="$DIST/dmg"; mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp packaging/macos/LISEZ-MOI.txt "$STAGE/LISEZ-MOI.txt"
# hdiutil échoue parfois (« Resource busy ») sur les runners : quelques essais
for i in 1 2 3 4 5; do
  hdiutil create -volname "Cours IA" -srcfolder "$STAGE" -ov -format UDZO "$DIST/CoursIA-$VERSION.dmg" && break
  sleep 5
done
test -f "$DIST/CoursIA-$VERSION.dmg"
rm -rf "$STAGE"
echo "✔ $DIST/CoursIA-$VERSION.dmg"
