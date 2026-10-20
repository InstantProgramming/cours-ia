"""Génération des notes : transcription → fiche « major de promo » → approfondissements → animations.

Économie d'appels (abonnement ChatGPT Plus) : un cours = 3 appels en général
  1. fiche de cours complète (modèle fort, raisonnement élevé)
  2. approfondissements + vérification des faits avec recherche web
  3. animations explicatives (HTML/GSAP, jouées dans l'appli, export vidéo HyperFrames optionnel)
Les cours très longs sont d'abord condensés par blocs avec un modèle rapide.
"""

from __future__ import annotations

from . import llm

FAST_MODEL = "gpt-6-luna"


# ---------------------------------------------------------------- schémas JSON stricts

def S(type_, **kw):
    return {"type": type_, **kw}


def obj(**props) -> dict:
    return {"type": "object", "additionalProperties": False,
            "properties": props, "required": list(props)}


def arr(items: dict) -> dict:
    return {"type": "array", "items": items}


STR, NUM, INT = S("string"), S("number"), S("integer")

DIAGRAM = obj(
    kind=S("string", enum=["mermaid", "none"]),
    title=STR,
    code=S("string", description="Code Mermaid valide (vide si kind=none)"),
    caption=STR,
)

NOTES_SCHEMA = obj(
    title=STR,
    subject=S("string", description="Matière / domaine"),
    one_line=S("string", description="Le cours en une phrase"),
    summary_md=S("string", description="Résumé exécutif en Markdown, 8 à 15 lignes"),
    problematique=S("string", description="La question centrale à laquelle le cours répond"),
    plan=arr(STR),
    sections=arr(obj(
        id=STR,
        title=STR,
        start=S("number", description="Début en secondes dans la vidéo"),
        end=NUM,
        notes_md=S("string", description="Notes détaillées en Markdown (voir consignes)"),
        key_points=arr(STR),
        diagram=DIAGRAM,
    )),
    definitions=arr(obj(term=STR, definition=STR, section_id=STR)),
    timeline=arr(obj(date=STR, event=STR)),
    comparisons=arr(obj(title=STR, columns=arr(STR), rows=arr(arr(STR)))),
    mindmap_md=S("string", description="Carte mentale en Markdown (titres # / listes), pour markmap"),
    concept_map=DIAGRAM,
    to_deepen=arr(obj(concept=STR, why=STR, question=STR)),
    transcript_fixes=arr(obj(wrong=STR, right=STR)),
    flashcards=arr(obj(front=STR, back=STR)),
    quiz=arr(obj(question=STR, choices=arr(STR), answer_index=INT, explanation=STR)),
    exam_questions=arr(obj(question=STR, answer_outline_md=STR)),
    prof_hints=arr(S("string", description="Indices donnés par le prof : « ça tombe à l'examen », insistances…")),
)

DEEPEN_SCHEMA = obj(
    explanations=arr(obj(
        concept=STR,
        simple_md=S("string", description="Explication simple, comme à un ami intelligent de 15 ans"),
        analogy=STR,
        example=S("string", description="Exemple concret, de préférence réel (arrêt, entreprise, fait historique)"),
        expert_md=S("string", description="Ce qu'un très bon étudiant ajoute : nuances, débats, jurisprudence, auteurs"),
        pitfalls=arr(STR),
        sources=arr(obj(title=STR, url=STR)),
    )),
    fact_checks=arr(obj(claim=STR, verdict=S("string", enum=["exact", "imprécis", "faux", "à jour ?"]),
                        correction=STR, source_url=STR)),
    further_reading=arr(obj(title=STR, url=STR, why=STR)),
)

ANIM_SCHEMA = obj(
    animations=arr(obj(
        concept=S("string", description="Titre court de l'animation (8 mots max, sans lien)"),
        duration=S("number", description="Durée totale en secondes (20 à 60)"),
        html=S("string", description="Composition HyperFrames complète (voir consignes)"),
        narration=arr(obj(at=NUM, text=STR)),
    )),
)

FIX_DIAGRAM_SCHEMA = obj(code=STR)

CHUNK_SCHEMA = obj(condensed_md=STR)


# ---------------------------------------------------------------- outils

def fmt_ts(sec: float) -> str:
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def transcript_text(segments: list[dict], every: float = 30.0) -> str:
    """Transcription compacte : un repère temporel toutes les ~30 s pour économiser des tokens."""
    out, last_ts, last_spk = [], -every, None
    for seg in segments:
        prefix = ""
        if seg["start"] - last_ts >= every:
            prefix = f"\n[{fmt_ts(seg['start'])}] "
            last_ts = seg["start"]
        spk = seg.get("speaker")
        if spk and spk != last_spk:
            prefix += f"({spk}) "
            last_spk = spk
        out.append(prefix + seg["text"].strip())
    return " ".join(out).strip()


def _context(meta: dict) -> str:
    parts = [f"Titre fourni : {meta.get('title') or 'inconnu'}"]
    if meta.get("course_hint"):
        parts.append(f"Précisions de l'étudiante : {meta['course_hint']}")
    src = meta.get("source") or {}
    if src.get("uploader"):
        parts.append(f"Chaîne / auteur : {src['uploader']}")
    if src.get("description"):
        parts.append(f"Description de la vidéo : {src['description'][:1500]}")
    if src.get("chapters"):
        parts.append("Chapitres : " + "; ".join(f"{fmt_ts(c['start_time'])} {c['title']}" for c in src["chapters"]))
    if meta.get("duration"):
        parts.append(f"Durée : {fmt_ts(meta['duration'])}")
    return "\n".join(parts)


# ---------------------------------------------------------------- prompts

NOTES_PROMPT = """Tu es la meilleure étudiante de la promo (droit / économie / sciences humaines, niveau licence-master), \
réputée pour ses fiches que tout l'amphi s'arrache. Tu reçois la transcription automatique d'un cours en vidéo. \
Produis LA fiche de révision parfaite, en français, pour apprendre en COMPRENANT (pas en recopiant).

CONTEXTE
{context}

EXIGENCES
- Fidélité absolue au cours : n'invente rien. Ce que tu ajoutes pour clarifier est marqué « 💡 Complément : ».
- La transcription automatique contient des erreurs (noms propres, termes juridiques, articles de loi, chiffres). \
Corrige-les silencieusement dans les notes et liste les corrections certaines dans transcript_fixes \
(wrong = forme exacte présente dans la transcription).
- Découpe en sections qui suivent la logique du cours (pas des tranches de temps), avec start/end en secondes \
d'après les repères [mm:ss].
- notes_md de chaque section : Markdown structuré, phrases courtes, hiérarchie claire (### sous-titres, listes). Utilise :
  > **Définition — Terme** : …        (pour chaque notion)
  > **À retenir** : …                 (l'essentiel, 1 à 3 par section)
  > **Exemple** : …                   (exemples du prof, ou complément marqué)
  > **Attention** : …                 (pièges, confusions fréquentes, exceptions)
  Mets en **gras** les mots-clés. Cite précisément articles, arrêts, auteurs, dates, chiffres quand le prof les donne. \
Reformule le raisonnement (cause → conséquence, principe → exceptions, thèse → antithèse) plutôt que paraphraser.
- diagram : pour chaque section où un schéma aide vraiment (procédure, classification, causalité, chronologie, \
hiérarchie des normes, mécanisme économique…), donne un diagramme Mermaid SIMPLE et VALIDE \
(flowchart TD/LR, timeline, mindmap, quadrantChart ou sequenceDiagram). Règles Mermaid : identifiants ASCII sans espaces, \
libellés entre guillemets doubles ("…") dès qu'ils contiennent accents, parenthèses, deux-points ou apostrophes, \
pas de guillemets doubles à l'intérieur des libellés, ≤ 15 nœuds. Sinon kind="none" et code="".
- concept_map : un flowchart Mermaid qui relie les grandes notions du cours entre elles (liens étiquetés).
- mindmap_md : carte mentale complète du cours en Markdown (# titre, ## parties, - sous-points courts).
- timeline / comparisons : seulement si le cours s'y prête (dates, auteurs, régimes à comparer…), sinon listes vides.
- to_deepen : 3 à 6 notions difficiles, survolées ou implicites qui méritent une explication approfondie.
- prof_hints : ce sur quoi le prof insiste, annonce pour l'examen, répète.
- flashcards (15 à 30), quiz (8 à 12 QCM, 4 choix, une seule bonne réponse, explication), \
exam_questions (3 à 5 sujets probables avec plan de réponse en Markdown).

TRANSCRIPTION (repères [mm:ss])
<<<
{transcript}
>>>
"""

CHUNK_PROMPT = """Voici la partie {i}/{n} de la transcription automatique d'un long cours ({context_title}). \
Condense-la en notes Markdown très détaillées et fidèles (≈ 30 % de la longueur), en conservant TOUS les repères \
temporels [mm:ss] en début de paragraphe, les définitions, exemples, chiffres, références et insistances du prof. \
Corrige les erreurs évidentes de transcription.

<<<
{transcript}
>>>
"""

DEEPEN_PROMPT = """Tu es un tuteur expert ({subject}) et pédagogue hors pair. Une étudiante révise le cours « {title} ». \
Utilise la recherche web pour t'appuyer sur des sources fiables et à jour (Légifrance, Cour de cassation, Conseil d'État, \
Conseil constitutionnel, EUR-Lex, INSEE, Banque de France, OCDE, Vie-publique, Cairn, encyclopédies universitaires…). \
Réponds en français.

1. explanations : pour chaque notion ci-dessous, explique-la pour qu'elle la COMPRENNE vraiment : version simple, \
analogie parlante, exemple concret réel, puis le niveau « major de promo » (nuances, débats doctrinaux, jurisprudence \
ou données récentes), pièges classiques, et 1 à 3 sources (URL réelles consultées).
2. fact_checks : vérifie les affirmations factuelles importantes du résumé ci-dessous (articles de loi, dates, chiffres, \
réformes). Signale ce qui est faux, imprécis ou a changé depuis (réforme, revirement). Ne liste que les points vérifiés.
3. further_reading : 3 à 5 ressources de qualité pour aller plus loin.

NOTIONS À APPROFONDIR
{to_deepen}

RÉSUMÉ DU COURS
{summary}
"""

ANIM_PROMPT = """Tu es motion designer pédagogique. Crée {n} courtes animations explicatives (20 à 60 s chacune) \
pour faire comprendre visuellement ces notions d'un cours de {subject} (« {title} ») :
{concepts}

Chaque animation est une composition HyperFrames : un SEUL fichier HTML autonome, 1920×1080, fond clair, \
typographie lisible (titres ≥ 64px, texte ≥ 40px), en français, qui montre un mécanisme étape par étape \
(apparition progressive de blocs, flèches qui se tracent, mise en évidence, comparaison côte à côte, frise qui défile…). \
Pas d'images externes ni de vidéo : formes HTML/CSS/SVG uniquement. Occupe bien l'espace (éléments grands et \
centrés), garde libre la bande inférieure de 160 px et n'écris PAS les sous-titres dans le HTML : l'appli affiche \
la narration par-dessus. Pas de sources ni d'URL à l'écran.

Format OBLIGATOIRE du champ html :
<!doctype html><html><head><meta charset="utf-8"><style>…</style></head><body>
<div id="stage" data-composition-id="explainer" data-start="0" data-width="1920" data-height="1080" \
style="width:1920px;height:1080px;position:relative;overflow:hidden">
  … éléments ; chaque élément animé visible dans le temps porte class="clip" data-start="s" data-duration="s" data-track-index="n" …
</div>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js"></script>
<script>
  const tl = gsap.timeline({{ paused: true }});
  … animations GSAP positionnées en secondes absolues (3e argument) …
  window.__timelines = window.__timelines || {{}};
  window.__timelines.explainer = tl;
</script></body></html>

Règles HyperFrames : le moteur affiche/masque lui-même chaque élément .clip selon data-start/data-duration \
(secondes absolues) ; n'anime JAMAIS opacity, visibility, autoAlpha ou display d'un élément .clip : anime ses \
enfants (div intérieure) pour les entrées/sorties. Une scène = une section.clip ; les scènes ne se chevauchent pas.
La timeline DOIT être en pause (le lecteur la pilote) et durer exactement `duration` secondes. \
narration : sous-titres horodatés (at = seconde d'apparition) qui expliquent ce qu'on voit.

Contexte (extraits des notes) :
{context}
"""

FIX_DIAGRAM_PROMPT = """Ce diagramme Mermaid ne s'affiche pas. Erreur : {error}
Renvoie une version corrigée, plus simple si besoin, qui respecte la syntaxe Mermaid 11 \
(identifiants ASCII, libellés entre guillemets doubles, pas de caractères spéciaux non échappés). Même contenu.

{code}
"""


# ---------------------------------------------------------------- étapes

def build_notes(segments: list[dict], meta: dict, cfg: dict, log) -> dict:
    text = transcript_text(segments)
    context = _context(meta)
    words = len(text.split())
    # Au-delà de ~2 h 30 de parole on condense d'abord par blocs (modèle rapide), sinon un seul appel.
    if words > 28000:
        chunks = _split(text, 9000)
        log(f"Cours long ({words} mots) : condensation en {len(chunks)} blocs…")
        parts = []
        for i, chunk in enumerate(chunks, 1):
            log(f"Condensation du bloc {i}/{len(chunks)}…", progress=0.05 + 0.25 * i / len(chunks))
            r = llm.ask_json(CHUNK_PROMPT.format(i=i, n=len(chunks), context_title=meta.get("title"), transcript=chunk),
                             CHUNK_SCHEMA, cfg, model=FAST_MODEL, effort="medium", log=log)
            parts.append(r["condensed_md"])
        text = "\n\n".join(parts)
    log("Rédaction de la fiche de cours (la meilleure élève prend ses notes)…", progress=0.35)
    notes = llm.ask_json(NOTES_PROMPT.format(context=context, transcript=text), NOTES_SCHEMA, cfg,
                         effort=cfg.get("codex_reasoning") or "high", log=log)
    return notes


def deepen(notes: dict, cfg: dict, log) -> dict:
    items = notes.get("to_deepen") or []
    if not items:
        return {"explanations": [], "fact_checks": [], "further_reading": []}
    log(f"Approfondissement de {len(items)} notions + vérification des faits (recherche web)…")
    to_deepen = "\n".join(f"- {x['concept']} — {x['why']} (question : {x['question']})" for x in items)
    summary = notes.get("summary_md", "") + "\n\n" + "\n".join(
        f"## {s['title']}\n" + "\n".join(f"- {p}" for p in s.get("key_points", [])) for s in notes.get("sections", []))
    return llm.ask_json(DEEPEN_PROMPT.format(subject=notes.get("subject", ""), title=notes.get("title", ""),
                                             to_deepen=to_deepen, summary=summary),
                        DEEPEN_SCHEMA, cfg, web=True, effort="medium", log=log)


def animations(notes: dict, deep: dict, cfg: dict, log, n: int = 2) -> dict:
    concepts = [e["concept"] for e in deep.get("explanations", [])][:n] or \
               [x["concept"] for x in notes.get("to_deepen", [])][:n]
    if not concepts:
        return {"animations": []}
    log(f"Création de {len(concepts)} animation(s) explicative(s)…")
    ctx = []
    for e in deep.get("explanations", []):
        if e["concept"] in concepts:
            ctx.append(f"### {e['concept']}\n{e['simple_md']}\nAnalogie : {e['analogy']}\nExemple : {e['example']}")
    return llm.ask_json(ANIM_PROMPT.format(n=len(concepts), subject=notes.get("subject", ""),
                                           title=notes.get("title", ""),
                                           concepts="\n".join(f"- {c}" for c in concepts),
                                           context="\n\n".join(ctx) or notes.get("summary_md", "")),
                        ANIM_SCHEMA, cfg, effort="medium", log=log)


def fix_diagram(code: str, error: str, cfg: dict) -> str:
    r = llm.ask_json(FIX_DIAGRAM_PROMPT.format(code=code, error=error), FIX_DIAGRAM_SCHEMA, cfg,
                     model=FAST_MODEL, effort="low", timeout=300)
    return r["code"]


def _split(text: str, words_per_chunk: int) -> list[str]:
    words = text.split(" ")
    return [" ".join(words[i:i + words_per_chunk]) for i in range(0, len(words), words_per_chunk)]
