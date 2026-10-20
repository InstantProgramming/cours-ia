# Benchmark des outils (octobre 2026)

Cible : Mac Apple Silicon, cours en français (droit / éco / lettres), une seule utilisatrice, abonnement ChatGPT Plus.

## Transcription (ASR)

| Modèle | WER FR | Horodatage | Mémoire | Vitesse | Licence | Mac | PC |
|---|---|---|---|---|---|---|---|
| **Parakeet TDT 0.6B v3** (`mlx-community/parakeet-tdt-0.6b-v3`) | **5,4 %** | phrases + mots | ~2–3 Go | la plus rapide (RTFx 1720) | CC-BY-4.0 | ✅ `parakeet-mlx` | NeMo |
| Canary 1B v2 | 4,8 % | segments | ~4–5 Go | RTFx 634 | CC-BY-4.0 | portage communautaire | NeMo (difficile) |
| Cohere Transcribe (2B) | 4,1 % | ❌ aucun | ~5 Go | RTFx 491 | Apache-2.0 | ❌ | — |
| Qwen3-ASR 1.7B | 5,7 % | via aligneur séparé | ~2 Go | RTFx 113 | Apache-2.0 | mlx-audio | — |
| **Whisper large-v3-turbo** | ~6,5 % | phrases + mots | ~2–4 Go | rapide | MIT | ✅ `mlx-whisper` | ✅ `faster-whisper` |
| Nemotron 3.5 ASR streaming 0.6B | ~9 % (FLEURS) | streaming | faible | temps réel | flou | — | — |
| Voxtral Small 24B | 4,1 % | — | trop gros | lent | Apache-2.0 | ❌ | ❌ |

WER : Open ASR Leaderboard (arXiv 2510.06961v4, mars 2026). Les vitesses sur M1/M2/M3 n'ont pas été mesurées
(estimation : 2–5 min par heure de cours pour Parakeet, 5–12 min pour Whisper turbo).

**Choix :**
- Mac : **Parakeet v3** par défaut. **Whisper turbo MLX** en option : on peut forcer le français et lui passer un
  glossaire (titre + précisions du cours), ce qui aide sur le vocabulaire juridique.
- PC NVIDIA : **faster-whisper large-v3-turbo** (int8_float16, ~3 Go de VRAM).
- Les erreurs restantes (noms propres, articles de loi) sont corrigées par le LLM au moment de la fiche
  (`transcript_fixes`), puis appliquées à l'affichage de la transcription.

## Diarisation (qui parle)

| Modèle | DER | Mac | Notes |
|---|---|---|---|
| **Nemotron-3-Diarization** (NVIDIA, sept. 2026) | DIHARD III 12,7 · CALLHOME 9,1 | ✅ `mlx-community/Nemotron-3-Diarization` via `mlx-audio` | ≤ 8 intervenants, pas de token HF |
| pyannote community-1 | AMI 17,0 · CALLHOME 26,7 | MPS non testé | token Hugging Face requis |

Choix : Nemotron sur Mac, pyannote sur PC (extra `diarisation-pc`). Désactivée par défaut (un seul prof).

## Transcription cloud (secours)

| Service | Prix / heure | Remarque |
|---|---|---|
| Mistral Voxtral Mini Transcribe V2 | ~0,18 $ | français natif, diarisation incluse |
| ElevenLabs Scribe v2 | ~0,22–0,27 $ | meilleur WER français mesuré (3,3 %) |
| Soniox async | ~0,10 $ | le moins cher vu |
| AssemblyAI / Deepgram / Gladia | 0,21–0,61 $ | diarisation souvent en supplément |

## LLM

- **Codex CLI** (`codex exec`) avec l'abonnement ChatGPT : pas de crédits API. Sortie JSON stricte via
  `--output-schema`, recherche web live via `codex --search exec`.
- Modèles : `gpt-6.1-sol` (qualité, 15–160 messages / 5 h sur Plus), `gpt-6-luna` (rapide, 350–3000 / 5 h).
- L'appli fait **~3 appels par cours** (fiche, approfondissements + vérifications web, animations) ;
  la réparation d'un schéma et les condensations de cours très longs passent par Luna.
- Secours : OpenRouter ou API Claude (clés dans les réglages).

## Visuels

| Outil | Usage dans l'appli |
|---|---|
| Mermaid 11 | schémas par section (procédures, classifications, causalités), carte des concepts, chronologie |
| markmap | carte mentale interactive de tout le cours |
| Tableaux HTML | comparaisons (régimes, doctrines, auteurs) |
| **HyperFrames** (HeyGen, Apache-2.0) | animations explicatives : composition HTML + GSAP générée par le LLM, jouée directement dans l'appli, export MP4 via `npx hyperframes render` (Node 22 + Chrome + FFmpeg) |

Écartés : Manim (maths, lourd), Excalidraw (JSON peu fiable à générer), **VoiceStudio** (AGPL, bêta, simple
surcouche des mêmes moteurs ASR, surtout orienté TTS/doublage).
