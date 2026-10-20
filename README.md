# Cours IA

Donne une vidéo de cours → obtiens la fiche du major de promo :

- **Transcription fiable** horodatée (Parakeet v3 / Whisper turbo en local, ou cloud), corrigée par l'IA
- **Fiche de cours** : résumé, problématique, plan, notes par partie (définitions, « à retenir », exemples, pièges),
  lexique, points sur lesquels le prof insiste — chaque partie renvoie au moment de la vidéo
- **Comprendre** : vulgarisation des notions difficiles (en simple, analogie, exemple réel, niveau expert),
  vérifications et sources via recherche web, **animations explicatives** (HyperFrames)
- **Schémas & cartes** : carte mentale, carte des concepts, chronologie, tableaux comparatifs
- **S'entraîner** : flashcards en **répétition espacée** (révision du jour sur tous les cours), quiz corrigé,
  sujets d'examen probables
- **Tuteur** : questions libres, « Je n'ai pas compris » / « Teste-moi » sur chaque partie
- Export Markdown et PDF

L'IA passe par **Codex avec l'abonnement ChatGPT** (pas de crédits API). Choix techniques : [docs/benchmark.md](docs/benchmark.md).

## Installer sur Mac (Apple Silicon)

1. Télécharger `CoursIA-x.y.z.dmg` depuis la page **Releases** du dépôt.
2. L'ouvrir, glisser **Cours IA** dans **Applications**.
3. Premier lancement : macOS bloque l'appli (non publiée sur l'App Store) → Réglages Système →
   Confidentialité et sécurité → **Ouvrir quand même**. L'installation prend ensuite 3 à 5 min (une fois).
4. Dans l'appli : **Se connecter** à ChatGPT.

Les **mises à jour** s'installent depuis l'appli (bandeau « Nouvelle version »). Les cours sont dans `Documents/CoursIA`.

## Publier une nouvelle version

1. Changer `__version__` dans `src/cours_ia/__init__.py` (et `version` dans `pyproject.toml`), puis `uv lock`.
2. Ajouter une section `## x.y.z` en tête de `CHANGELOG.md` (texte affiché dans l'appli).
3. Commit, puis `git tag vx.y.z && git push --tags`.

GitHub Actions ([.github/workflows/macos.yml](.github/workflows/macos.yml)) construit le `.dmg` sur un Mac M1,
le teste (installation, transcription MLX, Codex) et publie la release ; l'appli la détecte dans l'heure.

## Développement

```bash
uv sync
uv run cours-ia
```

`COURS_IA_NO_WINDOW=1` : serveur seul + navigateur. Autres variables : `COURS_IA_DATA` (dossier des cours),
`COURS_IA_HOME` (données de l'appli), `COURS_IA_PORT` (8765), `CODEX_BIN`, `COURS_IA_REPO` (dépôt des mises à jour).

Structure : `src/cours_ia/` (serveur FastAPI, pipeline, prompts, interface web dans `web/`),
`packaging/` (lanceur macOS, Info.plist, icône, script de build du .dmg).
