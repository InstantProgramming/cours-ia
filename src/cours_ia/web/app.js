import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs";

/* =================================================================== outils */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const main = $("#main");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Erreur ${r.status}`);
  return r.json();
}
const send = (method, path, body) => api(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });
const post = (path, body) => send("POST", path, body);
function toast(msg, ms = 3500) {
  $(".toast")?.remove();
  const t = Object.assign(document.createElement("div"), { className: "toast", textContent: msg });
  document.body.append(t); setTimeout(() => t.remove(), ms);
}
const fmt = (sec) => {
  sec = Math.max(0, Math.floor(sec || 0));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return (h ? `${h}:${String(m).padStart(2, "0")}` : String(m).padStart(2, "0")) + ":" + String(s).padStart(2, "0");
};
const dur = (sec) => !sec ? "" : sec >= 3600 ? `${Math.floor(sec / 3600)} h ${String(Math.round((sec % 3600) / 60)).padStart(2, "0")}` : `${Math.round(sec / 60)} min`;
const parseTs = (str) => str.split(":").map(Number).reduce((a, b) => a * 60 + b, 0);
const today = () => new Date().toISOString().slice(0, 10);

/* pont vers l'appli native (pywebview) — repli navigateur sinon */
const native = () => window.pywebview?.api;
async function saveFile(name, content) {
  if (native()) {
    const p = await native().save_file(name, content);
    if (p) toast(`Enregistré : ${p}`);
    return;
  }
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([content])), download: name });
  a.click(); URL.revokeObjectURL(a.href);
}
function openExternal(url) {
  if (native()) native().open_url(url.startsWith("http") ? url : location.origin + url);
  else window.open(url, "_blank", "noopener");
}

/* préférences d'affichage */
const prefs = (() => { try { return JSON.parse(localStorage.getItem("coursia-prefs") || "{}"); } catch { return {}; } })();
function setPref(k, v) {
  prefs[k] = v;
  try { localStorage.setItem("coursia-prefs", JSON.stringify(prefs)); } catch {}
  const root = document.documentElement;
  if (k === "theme") v === "auto" ? delete root.dataset.theme : (root.dataset.theme = v);
  if (k === "size") root.dataset.size = v;
}

/* =================================================================== mermaid */
const isDark = () => document.documentElement.dataset.theme === "dark" ||
  (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
function initMermaid() {
  mermaid.initialize({ startOnLoad: false, theme: "base", securityLevel: "strict",
    fontFamily: "Inter, system-ui, sans-serif", flowchart: { htmlLabels: true, curve: "basis" },
    themeVariables: isDark()
      ? { primaryColor: "#252c44", primaryBorderColor: "#7c9cf5", primaryTextColor: "#ecebe8", lineColor: "#8d887f",
          secondaryColor: "#33291a", tertiaryColor: "#1b2e23", background: "#1f1e24", fontSize: "15px" }
      : { primaryColor: "#eef2fd", primaryBorderColor: "#2f5bd3", primaryTextColor: "#1f1d1a", lineColor: "#8a8378",
          secondaryColor: "#fdf5e6", tertiaryColor: "#ecf7f0", background: "#fffdf9", fontSize: "15px" } });
}
initMermaid();

/* =================================================================== Markdown enrichi */
const CALLOUTS = [
  [/^d[ée]finition/i, "def"], [/^(à|a) retenir|^essentiel|^retenir/i, "key"], [/^exemple/i, "ex"],
  [/^attention|^pi[èe]ge|^erreur/i, "warn"], [/^💡|^compl[ée]ment|^astuce|^remarque/i, "tip"],
];
function md(text) {
  const box = document.createElement("div");
  box.innerHTML = DOMPurify.sanitize(marked.parse(String(text || "")));
  for (const bq of $$("blockquote", box)) {
    const hit = CALLOUTS.find(([re]) => re.test(bq.textContent.trim()));
    if (hit) bq.classList.add(hit[1]);
  }
  for (const a of $$("a[href^='http']", box)) a.dataset.external = "1";
  return box.innerHTML.replace(/\[(\d{1,2}:\d{2}(?::\d{2})?)\]/g,
    (_, t) => `<a class="ts-link" data-seek="${parseTs(t)}">▶ ${t}</a>`);
}
// liens web → navigateur par défaut (dans la fenêtre native, sinon nouvel onglet)
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[href^='http']");
  if (a) { e.preventDefault(); openExternal(a.href); }
});

/* =================================================================== modales & menus */
function modal({ title, html = "", actions = [{ label: "OK", value: true, primary: true }], onMount }) {
  return new Promise((resolve) => {
    const back = document.createElement("div");
    back.className = "modal-back";
    back.innerHTML = `<div class="modal" role="dialog" aria-modal="true"><h2>${esc(title)}</h2><div class="mbody">${html}</div>
      <div class="actions">${actions.map((a, i) => `<button class="btn ${a.primary ? "primary" : ""} ${a.danger ? "danger solid" : ""}" data-i="${i}">${esc(a.label)}</button>`).join("")}</div></div>`;
    const close = (v) => { back.remove(); document.removeEventListener("keydown", key); resolve(v); };
    const key = (e) => { if (e.key === "Escape") close(null); };
    back.addEventListener("click", (e) => {
      if (e.target === back) return close(null);
      const b = e.target.closest("[data-i]");
      if (b) close(typeof actions[b.dataset.i].value === "function" ? actions[b.dataset.i].value(back) : actions[b.dataset.i].value);
    });
    document.addEventListener("keydown", key);
    document.body.append(back);
    onMount?.(back, close);
    ($("input,textarea", back) || $(".btn.primary", back))?.focus();
  });
}
const confirmModal = (title, text, label = "Confirmer", danger = false) =>
  modal({ title, html: `<p class="muted">${esc(text)}</p>`, actions: [{ label: "Annuler", value: false }, { label, value: true, primary: !danger, danger }] });

function menu(anchor, items) {
  $(".menu")?.remove();
  const m = document.createElement("div");
  m.className = "menu";
  m.innerHTML = items.map((it, i) => it === "-" ? "<hr>" : `<button data-i="${i}" class="${it.danger ? "danger" : ""}">${it.icon || ""} ${esc(it.label)}</button>`).join("");
  document.body.append(m);
  const r = anchor.getBoundingClientRect();
  m.style.top = `${r.bottom + 6}px`;
  m.style.left = `${Math.max(8, Math.min(r.right - m.offsetWidth, innerWidth - m.offsetWidth - 8))}px`;
  const off = (e) => { if (!m.contains(e.target)) { m.remove(); document.removeEventListener("mousedown", off); } };
  setTimeout(() => document.addEventListener("mousedown", off));
  m.addEventListener("click", (e) => {
    const b = e.target.closest("[data-i]");
    if (b) { m.remove(); items[b.dataset.i].run(); }
  });
}

/* =================================================================== état & navigation */
const state = { lessonId: null, data: null, poll: null, tab: "fiche", stepsSig: "", chat: [], status: null, lessons: [] };
const TABS = [["fiche", "📝 Fiche"], ["comprendre", "💡 Comprendre"], ["cartes", "🗺️ Schémas & cartes"],
  ["reviser", "🎯 S'entraîner"], ["transcription", "🎙️ Transcription"], ["tuteur", "💬 Tuteur"]];
const STEPS = [["source", "Récupération de la vidéo"], ["audio", "Préparation de l'audio"], ["transcript", "Transcription"],
  ["notes", "Rédaction de la fiche"], ["deep", "Approfondissements & vérifications"], ["animations", "Animations explicatives"]];

window.addEventListener("hashchange", route);
async function route() {
  clearInterval(state.poll);
  $(".menu")?.remove();
  const h = decodeURIComponent(location.hash.slice(1));
  const [view, id, tab] = h.split("/");
  let nav = "home";
  if (view === "c" && id) {
    if (id !== state.lessonId) { state.chat = []; state.stepsSig = ""; state.data = null; }
    state.lessonId = id; state.tab = tab || "fiche"; nav = "";
    await showLesson();
  } else {
    state.lessonId = null;
    if (view === "nouveau") { nav = "nouveau"; showNew(); }
    else if (view === "reviser") { nav = "reviser"; await showReview(); }
    else if (view === "reglages") { nav = "reglages"; await showSettings(); }
    else if (view === "imprimer" && id) { nav = ""; await showPrint(id); }
    else await showHome();
  }
  $$(".nav-link").forEach((a) => a.classList.toggle("active", a.dataset.nav === nav));
  renderSidebar();
  window.scrollTo(0, 0);
}

/* =================================================================== barre latérale */
async function refreshLessons() {
  state.lessons = await api("/api/lessons").catch(() => state.lessons);
  renderSidebar();
  return state.lessons;
}
function renderSidebar() {
  const q = $("#side-search").value.trim().toLowerCase();
  const list = state.lessons.filter((l) => !q || `${l.title} ${l.subject || ""}`.toLowerCase().includes(q));
  $("#lesson-list").innerHTML = list.length ? list.map((l) => {
    const cls = l.status === "terminé" ? "ok" : l.status === "erreur" ? "err" : "run";
    const sub = l.status === "terminé" ? (l.subject || "") : l.status === "erreur" ? "Erreur — à relancer" : `${l.status}…`;
    return `<a class="lesson-item ${l.id === state.lessonId ? "active" : ""}" href="#c/${l.id}">
      <div class="t">${esc(l.title)}</div><div class="s"><span class="dot ${cls}"></span><span>${esc(sub)}</span></div></a>`;
  }).join("") : `<p class="muted" style="padding:6px 10px;font-size:.85rem">${q ? "Aucun résultat." : "Aucun cours pour l'instant."}</p>`;
  const due = state.lessons.reduce((n, l) => n + (l.due || 0), 0);
  $("#due-badge").hidden = !due; $("#due-badge").textContent = due;
}
$("#side-search").addEventListener("input", renderSidebar);

async function refreshStatus() {
  state.status = await api("/api/status").catch(() => state.status);
  const s = state.status;
  if (s) {
    $("#version").textContent = `Version ${s.version}`;
    $("#update-badge").hidden = !s.update?.available;
  }
  return s;
}

/* =================================================================== accueil */
async function showHome() {
  const [lessons, s] = await Promise.all([refreshLessons(), refreshStatus()]);
  const due = lessons.reduce((n, l) => n + (l.due || 0), 0);
  const cards = lessons.reduce((n, l) => n + (l.cards || 0), 0);
  const mastered = lessons.reduce((n, l) => n + (l.mastered || 0), 0);
  const hour = new Date().getHours();
  const groups = {};
  for (const l of lessons) (groups[l.subject_group || "Autres cours"] ||= []).push(l);
  main.innerHTML = `<div class="page">
    ${bannersHtml(s)}
    <div class="hello"><div><h1>${hour < 18 ? "Bonjour" : "Bonsoir"} 👋</h1>
      <p class="muted" style="margin:0">${lessons.length ? "Prête à apprendre en comprenant ?" : "Commence par ajouter la vidéo d'un cours."}</p></div>
      <a class="btn primary big" href="#nouveau">＋ Nouveau cours</a></div>
    ${due ? `<div class="review-cta"><div style="flex:1"><h2>🧠 ${due} carte${due > 1 ? "s" : ""} à réviser aujourd'hui</h2>
      <p>5 minutes de révision espacée valent mieux qu'une heure de relecture.</p></div><a class="btn big" href="#reviser">Commencer</a></div>` : ""}
    ${lessons.length ? `<div class="stats">
      <div class="stat"><b>${lessons.length}</b><span>cours</span></div>
      <div class="stat"><b>${mastered}<small class="muted" style="font-size:.9rem"> / ${cards}</small></b><span>cartes maîtrisées</span></div>
      <div class="stat"><b>${dur(lessons.reduce((n, l) => n + (l.duration || 0), 0)) || "0 min"}</b><span>de cours analysés</span></div>
    </div>` : `<div class="empty card"><div style="font-size:46px">🎓</div><h2 style="margin:.4em 0">Aucun cours pour l'instant</h2>
      <p>Ajoute la vidéo d'un cours : tu obtiendras une fiche claire, des schémas, des explications et des quiz.</p>
      <a class="btn primary" href="#nouveau">Ajouter mon premier cours</a></div>`}
    ${Object.entries(groups).map(([g, ls]) => `<div class="subject-title">${esc(g)} <small>${ls.length} cours</small></div>
      <div class="grid-cards">${ls.map(courseCard).join("")}</div>`).join("")}
  </div>`;
  bindBanners();
}
function courseCard(l) {
  const pct = l.cards ? Math.round(100 * (l.mastered || 0) / l.cards) : 0;
  const running = !["terminé", "erreur"].includes(l.status);
  return `<a class="course-card" href="#c/${l.id}">
    <h3>${esc(l.title)}</h3>
    <p>${esc(running ? `⏳ ${l.status}…` : l.status === "erreur" ? "⚠️ Le traitement a échoué — ouvre le cours pour relancer" : l.one_line || "")}</p>
    <div class="meta">${l.duration ? `<span>⏱ ${dur(l.duration)}</span>` : ""}${l.cards ? `<span>🃏 ${pct} % maîtrisé</span>` : ""}
      ${l.due ? `<span style="color:var(--accent)">● ${l.due} à revoir</span>` : ""}</div>
    ${l.cards ? `<div class="mastery"><i style="width:${pct}%"></i></div>` : ""}
  </a>`;
}
function bannersHtml(s) {
  if (!s) return "";
  const out = [];
  if (!s.codex.ok) out.push(`<div class="banner warn">🔌 <div class="spacer"><b>Connecte ton compte ChatGPT</b> pour que l'IA puisse rédiger tes fiches.</div>
    <button class="btn primary" data-action="codex-login">Se connecter</button></div>`);
  if (s.update?.available) out.push(`<div class="banner info">✨ <div class="spacer"><b>Nouvelle version ${esc(s.update.latest)}</b> disponible.
    ${s.update.notes ? `<span class="muted">${esc(s.update.notes.slice(0, 140))}</span>` : ""}</div>
    <button class="btn primary" data-action="update">Mettre à jour</button></div>`);
  return out.join("");
}
function bindBanners(root = main) {
  $("[data-action=codex-login]", root)?.addEventListener("click", codexLogin);
  $("[data-action=update]", root)?.addEventListener("click", installUpdate);
}
async function codexLogin() {
  try { await post("/api/codex/login"); } catch (e) { return toast(e.message); }
  toast("Une page ChatGPT s'est ouverte dans ton navigateur : connecte-toi, puis reviens ici.", 8000);
  for (let i = 0; i < 90; i++) {
    await sleep(3000);
    const s = await refreshStatus();
    if (s?.codex.ok) { toast("✅ Compte ChatGPT connecté !"); route(); return; }
  }
}
async function installUpdate() {
  const ok = await confirmModal("Mettre à jour Cours IA ?", "L'appli va télécharger la nouvelle version puis redémarrer. Tes cours sont conservés.", "Mettre à jour");
  if (!ok) return;
  toast("Téléchargement de la mise à jour…", 60000);
  try { await post("/api/update/install"); toast("Mise à jour installée — redémarrage…", 60000); }
  catch (e) { toast("Échec de la mise à jour : " + e.message, 8000); }
}

/* =================================================================== nouveau cours */
function showNew() {
  const s = state.status;
  main.innerHTML = `<div class="page narrow">
    ${bannersHtml(s)}
    <h1>Nouveau cours</h1>
    <p class="muted">Ajoute la vidéo d'un cours. L'appli la transcrit, rédige la fiche, approfondit les notions difficiles,
      dessine les schémas et prépare tes révisions. Compte environ 10 à 20 minutes pour un cours d'une heure — tu peux faire autre chose en attendant.</p>
    <form class="new-form" id="new-form">
      <label class="drop" id="drop">
        <input type="file" name="file" accept="video/*,audio/*,.mkv,.avi" hidden>
        <span class="drop-icon">🎬</span>
        <span class="drop-text"><b>Glisse la vidéo ici</b> ou clique pour la choisir</span>
        <span class="drop-file muted">Vidéo ou enregistrement audio (MP4, MOV, MKV, MP3, M4A…)</span>
      </label>
      <div class="or">ou</div>
      <label class="field"><span>Lien de la vidéo</span><input class="input" name="url" placeholder="https://www.youtube.com/watch?v=…"></label>
      <label class="field"><span>Matière / précisions <span class="help">— facultatif, mais améliore nettement le résultat</span></span>
        <textarea class="input" name="hint" rows="2" placeholder="ex. « Droit des obligations, L2, Mme Martin — chapitre sur la responsabilité du fait des choses »"></textarea></label>
      <label class="field"><span>Titre <span class="help">— facultatif, sinon trouvé automatiquement</span></span><input class="input" name="title"></label>
      <div id="upload" hidden><div class="upload-bar"><i></i></div><p class="muted" style="margin:6px 0 0;font-size:.85rem" id="upload-txt"></p></div>
      <button class="btn primary big" type="submit">✨ Analyser ce cours</button>
    </form></div>`;
  bindBanners();
  const form = $("#new-form"), drop = $("#drop"), input = $("input[type=file]", form);
  const showFile = () => {
    const f = input.files[0];
    drop.classList.toggle("has-file", !!f);
    $(".drop-icon", drop).textContent = f ? "✅" : "🎬";
    $(".drop-text", drop).innerHTML = f ? `<b>${esc(f.name)}</b>` : "<b>Glisse la vidéo ici</b> ou clique pour la choisir";
    $(".drop-file", drop).textContent = f ? `${(f.size / 1e6).toFixed(0)} Mo — clique pour changer` : "";
  };
  input.addEventListener("change", showFile);
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault(); drop.classList.remove("over");
    if (e.dataTransfer.files.length) { input.files = e.dataTransfer.files; showFile(); }
  });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const file = input.files[0];
    if (!file) fd.delete("file");
    if (!file && !fd.get("url").trim()) return toast("Ajoute une vidéo ou colle un lien");
    const btn = $("button[type=submit]", form);
    btn.disabled = true;
    // XHR plutôt que fetch : on veut la progression de l'envoi des grosses vidéos
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/lessons");
    if (file) {
      $("#upload").hidden = false;
      xhr.upload.onprogress = (ev) => {
        const p = ev.total ? ev.loaded / ev.total : 0;
        $("#upload i").style.width = `${p * 100}%`;
        $("#upload-txt").textContent = `Import de la vidéo… ${Math.round(p * 100)} %`;
      };
    }
    btn.textContent = file ? "Import en cours…" : "Création…";
    xhr.onload = () => {
      if (xhr.status >= 300) { btn.disabled = false; btn.textContent = "✨ Analyser ce cours"; return toast("Erreur : " + xhr.responseText.slice(0, 200)); }
      const { id } = JSON.parse(xhr.responseText);
      refreshLessons(); location.hash = `#c/${id}`;
    };
    xhr.onerror = () => { btn.disabled = false; btn.textContent = "✨ Analyser ce cours"; toast("L'envoi a échoué"); };
    xhr.send(fd);
  });
}

/* =================================================================== révision espacée (toutes matières) */
async function showReview() {
  const r = await api("/api/review");
  await refreshLessons();
  if (!r.due.length) {
    main.innerHTML = `<div class="page narrow"><div class="empty card"><div style="font-size:46px">🌿</div>
      <h2 style="margin:.4em 0">Rien à réviser aujourd'hui</h2>
      <p>${r.total ? `Tes ${r.total} cartes sont planifiées : reviens demain !` : "Les cartes apparaîtront ici après l'analyse d'un cours."}</p>
      <a class="btn" href="#">Retour à l'accueil</a></div></div>`;
    return;
  }
  runSession(r.due, "Révision du jour", async (card, ok) => {
    await post("/api/review/grade", { lid: card.lid, idx: card.idx, ok });
  }, () => { refreshLessons(); });
}

/** Session de cartes : file d'attente, les cartes ratées reviennent en fin de session. */
function runSession(cards, title, grade, onEnd, root = main) {
  const queue = [...cards];
  let done = 0, right = 0;
  const total = cards.length;
  root.innerHTML = `<div class="page narrow"><div class="row" style="margin-bottom:14px"><h1 style="margin:0">${esc(title)}</h1><span class="spacer"></span>
    <span class="muted" id="sess-count"></span></div>
    <div class="flash-wrap">
      <div class="session-progress bar"><i style="width:0"></i></div>
      <div class="flashcard" id="fc" tabindex="0"><div class="inner"><div class="face front"></div><div class="face back"></div></div></div>
      <div class="flash-actions" id="fc-show"><button class="btn primary big" id="btn-flip">Voir la réponse <span class="kbd">espace</span></button></div>
      <div class="flash-actions" id="fc-grade" hidden>
        <button class="btn big grade again" id="btn-again">😕 À revoir <span class="kbd">1</span></button>
        <button class="btn big grade good" id="btn-good">😊 Je savais <span class="kbd">2</span></button></div>
    </div></div>`;
  const fc = $("#fc", root);
  const draw = () => {
    $("#sess-count", root).textContent = `${done} / ${total}`;
    $(".session-progress i", root).style.width = `${100 * done / total}%`;
    fc.classList.remove("flipped");
    $("#fc-show", root).hidden = false; $("#fc-grade", root).hidden = true;
    if (!queue.length) {
      $(".front", fc).innerHTML = `<div style="font-size:40px">🎉</div>Session terminée !<div class="muted" style="font:400 1rem var(--sans);margin-top:8px">${right} / ${total} réussies du premier coup</div>`;
      $("#fc-show", root).innerHTML = `<a class="btn primary" href="#">Retour à l'accueil</a>`;
      document.removeEventListener("keydown", keys);
      onEnd?.();
      return;
    }
    const c = queue[0];
    $(".front", fc).innerHTML = `${c.lesson_title ? `<div class="from">${esc(c.lesson_title)}</div>` : ""}${md(c.front)}<div class="hint">clique pour retourner</div>`;
    $(".back", fc).innerHTML = md(c.back);
  };
  const flip = () => { if (!queue.length) return; fc.classList.add("flipped"); $("#fc-show", root).hidden = true; $("#fc-grade", root).hidden = false; };
  const answer = async (ok) => {
    if (!queue.length || !fc.classList.contains("flipped")) return;
    const c = queue.shift();
    if (ok) { done++; if (!c._missed) right++; } else { c._missed = true; queue.push(c); }
    grade(c, ok).catch(() => {});
    draw();
  };
  const keys = (e) => {
    if (!document.body.contains(fc)) return document.removeEventListener("keydown", keys);
    if (e.target.closest("input,textarea")) return;
    if (e.key === " ") { e.preventDefault(); fc.classList.contains("flipped") ? null : flip(); }
    if (e.key === "1") answer(false);
    if (e.key === "2") answer(true);
  };
  document.addEventListener("keydown", keys);
  fc.addEventListener("click", () => fc.classList.contains("flipped") ? fc.classList.remove("flipped") : flip());
  $("#btn-flip", root).addEventListener("click", flip);
  $("#btn-again", root).addEventListener("click", () => answer(false));
  $("#btn-good", root).addEventListener("click", () => answer(true));
  draw();
}

/* =================================================================== cours */
async function showLesson() {
  try { state.data = await api(`/api/lessons/${state.lessonId}`); }
  catch { main.innerHTML = `<div class="empty">Cours introuvable. <a href="#">Retour</a></div>`; return; }
  renderLesson();
  const running = () => !["terminé", "erreur"].includes(state.data.meta.status);
  if (running()) {
    state.poll = setInterval(async () => {
      const d = await api(`/api/lessons/${state.lessonId}`).catch(() => null);
      if (!d || d.meta.id !== state.lessonId) return;
      const sig = JSON.stringify(d.meta.steps);
      const hadNotes = !!state.data.notes;
      state.data = d;
      // on ne redessine pas tout (vidéo, défilement) si la fiche est déjà affichée
      if (sig !== state.stepsSig && (!hadNotes || state.tab === "comprendre")) { renderLesson(); refreshLessons(); }
      else { state.stepsSig = sig; renderProgress(); }
      if (!running()) {
        clearInterval(state.poll); refreshLessons();
        if (d.meta.status === "terminé") { toast("✅ Ton cours est prêt !"); renderLesson(); }
      }
    }, 2000);
  }
}

function renderLesson() {
  const { meta, notes } = state.data;
  state.stepsSig = JSON.stringify(meta.steps);
  const title = meta.title || notes?.title;
  main.innerHTML = `<div class="page">
    <div class="lesson-head">
      <div>
        ${notes?.subject ? `<span class="pill">${esc(notes.subject)}</span>` : ""}
        <h1>${esc(title)}</h1>
        ${notes?.one_line ? `<p class="one-line">${esc(notes.one_line)}</p>` : ""}
      </div>
      <div class="head-actions">
        ${notes ? `<div class="read-tools no-print"><button class="btn icon" id="btn-size" title="Taille du texte">Aa</button></div>` : ""}
        <button class="btn icon" id="btn-more" title="Plus d'actions">⋯</button>
      </div>
    </div>
    <div id="progress"></div>
    ${notes ? `<div class="tabs">${TABS.map(([k, l]) => {
      const soon = k === "comprendre" && !state.data.deep && !["terminé", "erreur"].includes(meta.status);
      return `<button class="tab ${k === state.tab ? "active" : ""}" data-tab="${k}">${l}${soon ? ' <span class="soon">⏳</span>' : ""}</button>`;
    }).join("")}</div><div id="tab"></div>` : ""}</div>`;
  renderProgress();
  $$(".tab").forEach((b) => b.addEventListener("click", () => { location.hash = `#c/${meta.id}/${b.dataset.tab}`; }));
  $("#btn-more").addEventListener("click", (e) => lessonMenu(e.currentTarget));
  $("#btn-size")?.addEventListener("click", (e) => menu(e.currentTarget, [
    { label: "Petit", icon: "A", run: () => setPref("size", "s") },
    { label: "Normal", icon: "A", run: () => setPref("size", "") },
    { label: "Grand", icon: "A", run: () => setPref("size", "l") },
    { label: "Très grand", icon: "A", run: () => setPref("size", "xl") },
  ]));
  if (notes) renderTab();
}

function lessonMenu(anchor) {
  const { meta, notes } = state.data;
  const items = [{ label: "Renommer", icon: "✏️", run: renameLesson }];
  if (notes) {
    items.push({ label: "Imprimer / PDF", icon: "🖨", run: () => openExternal(`/#imprimer/${meta.id}`) });
    items.push({ label: "Exporter en Markdown", icon: "⬇", run: async () => {
      const r = await fetch(`/api/lessons/${meta.id}/export.md`);
      saveFile(`${(meta.title || "cours").replace(/[\\/:*?"<>|]/g, "-")}.md`, await r.text());
    } });
  }
  items.push({ label: "Régénérer…", icon: "↻", run: rerunDialog });
  if (native()) items.push({ label: "Ouvrir le dossier du cours", icon: "📁", run: () => post(`/api/lessons/${meta.id}/reveal`) });
  items.push("-", { label: "Mettre à la corbeille", icon: "🗑", danger: true, run: async () => {
    if (!await confirmModal("Mettre ce cours à la corbeille ?", "Il pourra être récupéré dans le dossier « corbeille » de Cours IA.", "Mettre à la corbeille", true)) return;
    await send("DELETE", `/api/lessons/${meta.id}`); toast("Cours mis à la corbeille"); location.hash = "";
  } });
  menu(anchor, items);
}

async function renameLesson() {
  const title = await modal({ title: "Renommer le cours", html: `<input class="input" id="rn" value="${esc(state.data.meta.title)}">`,
    actions: [{ label: "Annuler", value: null }, { label: "Renommer", primary: true, value: (m) => $("#rn", m).value.trim() }],
    onMount: (m, close) => $("#rn", m).addEventListener("keydown", (e) => { if (e.key === "Enter") close($("#rn", m).value.trim()); }) });
  if (!title) return;
  await send("PATCH", `/api/lessons/${state.lessonId}`, { title });
  state.data.meta.title = title; renderLesson(); refreshLessons();
}

async function rerunDialog() {
  const opts = [["transcript", "Tout refaire depuis la transcription", "Si la transcription est mauvaise (après avoir changé de moteur dans les réglages)."],
    ["notes", "Réécrire la fiche", "Nouvelle fiche, puis approfondissements et animations."],
    ["deep", "Refaire les approfondissements", "Explications, vérifications et sources."],
    ["animations", "Refaire les animations", "Nouvelles animations explicatives."]];
  let pick = "notes";
  const ok = await modal({ title: "Que veux-tu régénérer ?",
    html: `<div class="option-list">${opts.map(([k, t, d]) => `<button class="option ${k === pick ? "on" : ""}" data-k="${k}"><div><b>${t}</b><small>${d}</small></div></button>`).join("")}</div>`,
    actions: [{ label: "Annuler", value: false }, { label: "Régénérer", primary: true, value: true }],
    onMount: (m) => $$(".option", m).forEach((b) => b.addEventListener("click", () => {
      pick = b.dataset.k; $$(".option", m).forEach((x) => x.classList.toggle("on", x === b));
    })) });
  if (!ok) return;
  await post(`/api/lessons/${state.lessonId}/rerun`, { from_step: pick });
  toast("C'est reparti !"); showLesson(); refreshLessons();
}

const STEP_EST = { source: 60, audio: 15, transcript: 0, notes: 420, deep: 300, animations: 120 };
function remaining(meta) {
  const d = meta.duration || 3600;
  let total = 0;
  for (const [k] of STEPS) {
    const st = meta.steps?.[k];
    if (st === "done" || st === "skipped") continue;
    const est = k === "transcript" ? Math.max(60, d / 15) : STEP_EST[k];
    total += st === "running" ? est * (1 - (meta.step_progress || 0)) * 0.7 : est;
  }
  return Math.max(1, Math.round(total / 60));
}

function renderProgress() {
  const { meta } = state.data;
  const box = $("#progress");
  if (!box) return;
  if (meta.status === "terminé") { box.innerHTML = ""; return; }
  const doneN = STEPS.filter(([k]) => ["done", "skipped"].includes(meta.steps?.[k])).length;
  const pct = Math.round(100 * (doneN + (meta.step_progress || 0)) / STEPS.length);
  const logHtml = (meta.log || []).slice(-14).map((l) => esc(l.msg)).join("\n");
  const err = meta.status === "erreur";
  if (state.data.notes && !err) {
    const open = $("#progress details")?.open ? "open" : "";
    box.innerHTML = `<div class="card progress-card compact"><div class="row"><span>⏳ ${esc(meta.status)}… <span class="muted">≈ ${remaining(meta)} min</span></span>
      <div class="bar spacer"><i style="width:${pct}%"></i></div></div>
      <details ${open}><summary>Détails</summary><div class="log">${logHtml}</div></details></div>`;
    return;
  }
  box.innerHTML = `<div class="card progress-card">
    <div class="row"><h2 style="margin:0;font-size:1.2rem">${err ? "⚠️ Le traitement s'est arrêté" : "Analyse du cours en cours…"}</h2><span class="spacer"></span>
      ${err ? "" : `<span class="muted">environ ${remaining(meta)} min restantes</span>`}</div>
    ${err ? `<div class="banner err" style="margin:14px 0 0">${esc(friendlyError(meta.error))}<span class="spacer"></span>
      <button class="btn primary" id="retry">Réessayer</button></div>` : `<p class="muted" style="margin:6px 0 0">Tu peux fermer cette page ou ajouter un autre cours : une notification te préviendra quand la fiche sera prête.</p>`}
    <div class="stepper">${STEPS.map(([k, l], i) => {
      const st = meta.steps?.[k] || "todo";
      const extra = st === "running" && meta.step_progress ? ` — ${Math.round(meta.step_progress * 100)} %` : "";
      return `<div class="st ${st}"><span class="ic">${st === "done" ? "✓" : st === "error" ? "!" : st === "running" ? "" : i + 1}</span>${l}${extra}</div>`;
    }).join("")}</div>
    <div class="bar"><i style="width:${pct}%"></i></div>
    <details><summary class="muted" style="font-size:.8rem;margin-top:10px">Journal détaillé</summary><div class="log">${logHtml}</div></details></div>`;
  $("#retry")?.addEventListener("click", async () => {
    const step = STEPS.map(([k]) => k).find((k) => meta.steps[k] === "error") || "source";
    await post(`/api/lessons/${meta.id}/rerun`, { from_step: step }); showLesson(); refreshLessons();
  });
}
function friendlyError(e = "") {
  if (/usage limit|rate limit|429|quota/i.test(e)) return "Le quota de ton abonnement ChatGPT est atteint pour le moment. Réessaie dans quelques heures, ou choisis le modèle « rapide » dans les réglages.";
  if (/Codex introuvable|not logged|login/i.test(e)) return "L'appli n'est pas connectée à ChatGPT. Va dans Réglages → Se connecter.";
  if (/HTTP Error 4|Unsupported URL|Video unavailable/i.test(e)) return "Impossible de récupérer la vidéo depuis ce lien. Télécharge-la et dépose le fichier à la place.";
  if (/moteur de transcription/i.test(e)) return e;
  return "Erreur : " + e;
}

function renderTab() {
  const tab = $("#tab");
  ({ fiche: tabFiche, comprendre: tabComprendre, cartes: tabCartes, reviser: tabReviser,
     transcription: tabTranscript, tuteur: tabTuteur }[state.tab] || tabFiche)(tab);
  tab.addEventListener("click", (e) => {
    const a = e.target.closest("[data-seek]");
    if (a) { e.preventDefault(); seek(+a.dataset.seek); }
    const ask = e.target.closest("[data-ask]");
    if (ask) { state.pendingQuestion = ask.dataset.ask; location.hash = `#c/${state.lessonId}/tuteur`; }
  });
}

/* ---------- vidéo ---------- */
function videoHtml() {
  const m = state.data.meta;
  return m.playable ? `<video id="video" controls preload="metadata" src="/media/${m.id}/${encodeURIComponent(m.playable)}"></video>` : "";
}
function seek(t) {
  const v = $("#video");
  if (!v) { location.hash = `#c/${state.lessonId}/transcription`; setTimeout(() => seek(t), 500); return; }
  v.currentTime = t; v.play().catch(() => {});
  if (v.getBoundingClientRect().top < 0) v.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

/* ---------- onglet Fiche ---------- */
function tabFiche(root) {
  const n = state.data.notes;
  root.innerHTML = `<div class="layout">
    <article class="prose">
      <div class="card"><h2 style="margin-top:0">Résumé</h2>${md(n.summary_md)}
        ${n.problematique ? `<div class="problem">${esc(n.problematique)}</div>` : ""}
        ${n.plan?.length ? `<h3>Plan du cours</h3><ol>${n.plan.map((p) => `<li>${esc(p)}</li>`).join("")}</ol>` : ""}
      </div>
      ${n.prof_hints?.length ? `<div class="keypoints" style="margin-top:18px"><h4>🎯 Le prof a insisté sur…</h4>
        <ul>${n.prof_hints.map((h) => `<li>${esc(h)}</li>`).join("")}</ul></div>` : ""}
      ${n.sections.map((s) => `<section class="section" id="sec-${esc(s.id)}">
        <div class="section-head"><h2>${esc(s.title)}</h2><a class="ts-link" data-seek="${s.start}" title="Revoir ce passage">▶ ${fmt(s.start)}</a></div>
        <div class="section-tools no-print">
          <button class="btn sm ghost" data-ask="Explique-moi plus simplement la partie « ${esc(s.title)} », avec un exemple concret.">🤔 Je n'ai pas compris</button>
          <button class="btn sm ghost" data-ask="Pose-moi 3 questions pour vérifier que j'ai compris la partie « ${esc(s.title)} », une par une.">✅ Teste-moi</button>
        </div>
        ${md(s.notes_md)}
        ${s.diagram?.kind === "mermaid" && s.diagram.code ? diagramBox(s.diagram, `section:${s.id}`) : ""}
        ${s.key_points?.length ? `<div class="keypoints"><h4>À retenir</h4><ul>${s.key_points.map((k) => `<li>${esc(k)}</li>`).join("")}</ul></div>` : ""}
      </section>`).join("")}
      ${n.definitions?.length ? `<h2>Lexique</h2><table><tbody>${n.definitions.map((d) =>
        `<tr><th style="width:28%">${esc(d.term)}</th><td>${esc(d.definition)}</td></tr>`).join("")}</tbody></table>` : ""}
    </article>
    <aside class="side">
      ${videoHtml()}
      <div class="card toc"><b>Sommaire</b>${n.sections.map((s) =>
        `<a data-goto="sec-${esc(s.id)}"><span class="ts">${fmt(s.start)}</span><span>${esc(s.title)}</span></a>`).join("")}</div>
    </aside></div>`;
  $$("[data-goto]", root).forEach((a) => a.addEventListener("click", () => document.getElementById(a.dataset.goto)?.scrollIntoView({ behavior: "smooth" })));
  // sommaire : surligne la partie en cours de lecture
  const io = new IntersectionObserver((entries) => {
    for (const en of entries) if (en.isIntersecting) $$(".toc a", root).forEach((a) => a.classList.toggle("current", a.dataset.goto === en.target.id));
  }, { rootMargin: "-20% 0px -70% 0px" });
  $$(".section", root).forEach((s) => io.observe(s));
  renderDiagrams(root);
}

/* ---------- diagrammes Mermaid (réparation automatique) ---------- */
let diagSeq = 0;
const diagCodes = [];
function diagramBox(d, where) {
  diagCodes.push(d.code);
  return `<div class="diagram" data-where="${esc(where)}" data-code="${diagCodes.length - 1}">
    ${d.title ? `<div class="dtitle"><span>${esc(d.title)}</span><span class="muted no-print" style="font-weight:400">🔍 clic pour agrandir</span></div>` : ""}
    <div class="dbody"><p class="muted">Dessin du schéma…</p></div>${d.caption ? `<div class="cap">${esc(d.caption)}</div>` : ""}</div>`;
}
async function renderDiagrams(root) {
  for (const box of $$(".diagram[data-where]", root)) await renderOne(box, diagCodes[+box.dataset.code]);
}
async function renderOne(box, code, repaired = false) {
  const body = $(".dbody", box);
  try {
    const { svg } = await mermaid.render(`mmd${++diagSeq}`, code);
    body.innerHTML = svg;
    body.onclick = () => {
      const lb = Object.assign(document.createElement("div"), { className: "lightbox", innerHTML: svg });
      lb.onclick = () => lb.remove();
      document.body.append(lb);
    };
  } catch (err) {
    document.getElementById(`dmmd${diagSeq}`)?.remove();
    if (repaired) { body.innerHTML = `<p class="muted">Ce schéma n'a pas pu être dessiné.</p>`; return; }
    body.innerHTML = `<p class="muted">Schéma en cours de réparation…</p>`;
    try {
      const r = await post(`/api/lessons/${state.lessonId}/fix-diagram`,
        { code, error: String(err.message || err).slice(0, 500), where: box.dataset.where });
      diagCodes[+box.dataset.code] = r.code;
      await renderOne(box, r.code, true);
    } catch { body.innerHTML = `<p class="muted">Ce schéma n'a pas pu être dessiné.</p>`; }
  }
}

/* ---------- onglet Comprendre ---------- */
function tabComprendre(root) {
  const deep = state.data.deep, anims = state.data.animations;
  if (!deep) {
    root.innerHTML = `<div class="empty card">⏳ Les explications approfondies sont en préparation (recherches et vérifications sur le web).<br>
      En attendant, la fiche est déjà lisible.</div>`;
    return;
  }
  const animList = anims?.animations || [];
  root.innerHTML = `<div class="prose" style="max-width:980px">
    <div class="subnav no-print">${animList.length ? `<a class="chip" data-goto="anims">🎬 Animations</a>` : ""}
      ${deep.explanations.map((e, i) => `<a class="chip" data-goto="exp-${i}">${esc(e.concept)}</a>`).join("")}
      ${deep.fact_checks?.length ? `<a class="chip" data-goto="facts">🔍 Vérifications</a>` : ""}</div>
    ${animList.length ? `<div id="anims">${animList.map((a, i) => `<div class="anim card" data-i="${i}">
        <h3>🎬 ${esc(a.concept)}</h3>
        <div class="anim-stage"><iframe src="/media/${state.lessonId}/${a.file}" title="${esc(a.concept)}" tabindex="-1"></iframe>
          <div class="anim-caption"></div><div class="anim-big-play"><span>▶</span></div></div>
        <div class="anim-controls"><button class="btn sm play" title="Lecture / pause">▶</button><input type="range" min="0" max="${a.duration}" step="0.05" value="0">
          <span class="muted tlabel" style="font-size:.8rem;min-width:84px">0:00 / ${fmt(a.duration)}</span>
          ${state.status?.hyperframes ? `<button class="btn sm render" ${state.data.renders?.[i]?.status === "running" ? "disabled" : ""}>${renderLabel(i)}</button>` : ""}</div>
      </div>`).join("")}</div>` : ""}
    ${deep.explanations.map((e, i) => `<div class="card explain" id="exp-${i}">
      <h2>${esc(e.concept)}</h2>
      <div class="explain-grid">
        <div class="e-simple"><h4>En simple</h4>${md(e.simple_md)}</div>
        <div class="e-analogy"><h4>Analogie</h4>${md(e.analogy)}</div>
        <div class="e-example"><h4>Exemple concret</h4>${md(e.example)}</div>
      </div>
      <details class="expert" open><summary><b>🎓 Niveau major de promo</b></summary>${md(e.expert_md)}</details>
      ${e.pitfalls?.length ? `<blockquote class="warn"><p><strong>Pièges classiques</strong></p><ul>${e.pitfalls.map((p) => `<li>${esc(p)}</li>`).join("")}</ul></blockquote>` : ""}
      <div class="row">${e.sources?.length ? `<div class="sources spacer">Sources : ${e.sources.map((s) => `<a href="${esc(s.url)}" data-external="1">${esc(s.title)}</a>`).join(" · ")}</div>` : '<span class="spacer"></span>'}
        <button class="btn sm ghost no-print" data-ask="Je n'ai toujours pas compris « ${esc(e.concept)} ». Réexplique autrement, avec une autre analogie.">🤔 Autre explication</button></div>
    </div>`).join("")}
    ${deep.fact_checks?.length ? `<h2 id="facts">🔍 Vérifications</h2><p class="muted">Ce que le prof a dit, vérifié avec des sources à jour.</p>
      <div class="card">${deep.fact_checks.map((f) => `<div class="fact">
      <span class="verdict v-${esc(f.verdict.split(" ")[0])}">${esc(f.verdict)}</span>
      <div><b>${esc(f.claim)}</b><br>${esc(f.correction)} ${f.source_url ? `<a href="${esc(f.source_url)}">source</a>` : ""}</div></div>`).join("")}</div>` : ""}
    ${deep.further_reading?.length ? `<h2>📚 Pour aller plus loin</h2><ul>${deep.further_reading.map((r) =>
      `<li><a href="${esc(r.url)}">${esc(r.title)}</a> — ${esc(r.why)}</li>`).join("")}</ul>` : ""}
  </div>`;
  $$("[data-goto]", root).forEach((a) => a.addEventListener("click", () => document.getElementById(a.dataset.goto)?.scrollIntoView({ behavior: "smooth" })));
  $$(".anim", root).forEach((el) => setupAnimation(el, animList[+el.dataset.i]));
}

function renderLabel(i) {
  const r = state.data.renders?.[i];
  if (r?.status === "running") return "⏳ Export…";
  if (r?.status === "done") return "⬇ Vidéo MP4";
  return "🎞 Exporter en MP4";
}

function setupAnimation(el, a) {
  const iframe = $("iframe", el), stage = $(".anim-stage", el), cap = $(".anim-caption", el), big = $(".anim-big-play", el);
  const range = $("input[type=range]", el), play = $(".play", el), label = $(".tlabel", el);
  let tl = null, t = 0, playing = false, last = 0, clips = [];
  const fit = () => { iframe.style.transform = `scale(${stage.clientWidth / 1920})`; };
  new ResizeObserver(fit).observe(stage); fit();
  const show = () => {
    tl?.seek(t, false);
    // comme le moteur HyperFrames : un .clip n'est visible qu'entre data-start et data-start + data-duration
    for (const c of clips) {
      const s = parseFloat(c.dataset.start || 0), d = parseFloat(c.dataset.duration || Infinity);
      c.style.visibility = t >= s && t < s + d ? "" : "hidden";
    }
    range.value = t; label.textContent = `${fmt(t)} / ${fmt(a.duration)}`;
    cap.textContent = [...(a.narration || [])].filter((n) => n.at <= t + 0.01).pop()?.text || "";
  };
  iframe.addEventListener("load", () => {
    const w = iframe.contentWindow;
    tl = w.__timelines?.explainer || Object.values(w.__timelines || {})[0];
    if (!tl) { cap.textContent = "Animation illisible — régénère les animations."; return; }
    clips = [...iframe.contentDocument.querySelectorAll(".clip[data-start]")];
    tl.pause(); show();
  });
  const loop = (now) => {
    if (!playing) return;
    t = Math.min(a.duration, t + (now - last) / 1000); last = now; show();
    if (t >= a.duration) { playing = false; play.textContent = "↺"; big.hidden = false; return; }
    requestAnimationFrame(loop);
  };
  const toggle = () => {
    if (playing) { playing = false; play.textContent = "▶"; return; }
    if (t >= a.duration) t = 0;
    playing = true; big.hidden = true; play.textContent = "❚❚"; last = performance.now(); requestAnimationFrame(loop);
  };
  play.addEventListener("click", toggle);
  stage.addEventListener("click", toggle);
  range.addEventListener("input", () => { t = +range.value; big.hidden = true; show(); });
  $(".render", el)?.addEventListener("click", async (e) => {
    const i = +el.dataset.i, r = state.data.renders?.[i];
    if (r?.status === "done") {
      // appli native : montre la vidéo dans le Finder ; navigateur : l'ouvre dans un onglet
      if (native()) post(`/api/lessons/${state.lessonId}/reveal`, { path: r.file });
      else openExternal(`/media/${state.lessonId}/${r.file}`);
      return;
    }
    try {
      await post(`/api/lessons/${state.lessonId}/animations/${i}/render`);
      e.target.disabled = true; e.target.textContent = "⏳ Export…";
      toast("Export vidéo lancé (quelques minutes la première fois)");
      const timer = setInterval(async () => {
        const d = await api(`/api/lessons/${state.lessonId}`);
        state.data.renders = d.renders;
        const st = d.renders?.[i]?.status;
        if (st !== "running") {
          clearInterval(timer); e.target.disabled = false; e.target.textContent = renderLabel(i);
          toast(st === "done" ? "🎞 Vidéo prête" : "L'export a échoué", 5000);
        }
      }, 4000);
    } catch (err) { toast(err.message); }
  });
}

/* ---------- onglet Schémas & cartes ---------- */
function tabCartes(root) {
  const n = state.data.notes;
  const diagrams = n.sections.filter((s) => s.diagram?.kind === "mermaid" && s.diagram.code);
  root.innerHTML = `<div class="prose">
    <div class="subnav no-print">${n.mindmap_md ? `<a class="chip" data-goto="mm-sec">🧠 Carte mentale</a>` : ""}
      ${n.concept_map?.code ? `<a class="chip" data-goto="cm-sec">🔗 Liens entre notions</a>` : ""}
      ${n.timeline?.length ? `<a class="chip" data-goto="tl-sec">📅 Chronologie</a>` : ""}
      ${n.comparisons?.length ? `<a class="chip" data-goto="cmp-sec">⚖️ Comparaisons</a>` : ""}
      ${diagrams.length ? `<a class="chip" data-goto="all-sec">🧩 Tous les schémas (${diagrams.length})</a>` : ""}</div>
    ${n.mindmap_md ? `<h2 id="mm-sec" style="margin-top:0">🧠 Carte mentale du cours</h2>
      <div class="row no-print" style="margin-bottom:8px"><span class="muted" style="font-size:.85rem">Molette pour zoomer · glisser pour déplacer · clic sur un point pour déplier</span>
      <span class="spacer"></span><button class="btn sm" id="mm-expand">Tout déplier</button><button class="btn sm" id="mm-fit">Recentrer</button></div>
      <div class="markmap-box"><svg id="mm"></svg></div>` : ""}
    ${n.concept_map?.kind === "mermaid" && n.concept_map.code ? `<h2 id="cm-sec">🔗 Comment les notions s'articulent</h2>${diagramBox(n.concept_map, "concept_map")}` : ""}
    ${n.timeline?.length ? `<h2 id="tl-sec">📅 Chronologie</h2>
      <table><tbody>${n.timeline.map((t) => `<tr><th style="width:20%">${esc(t.date)}</th><td>${esc(t.event)}</td></tr>`).join("")}</tbody></table>` : ""}
    ${n.comparisons?.length ? `<div id="cmp-sec">${n.comparisons.map((c) => `<h2>⚖️ ${esc(c.title)}</h2><table><thead><tr>${c.columns.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
      <tbody>${c.rows.map((r) => `<tr>${r.map((x) => `<td>${md(x)}</td>`).join("")}</tr>`).join("")}</tbody></table>`).join("")}</div>` : ""}
    ${diagrams.length ? `<h2 id="all-sec">🧩 Tous les schémas du cours</h2>
      ${diagrams.map((s) => diagramBox({ ...s.diagram, title: `${s.title}${s.diagram.title ? " — " + s.diagram.title : ""}` }, `section:${s.id}`)).join("")}` : ""}
  </div>`;
  $$("[data-goto]", root).forEach((a) => a.addEventListener("click", () => document.getElementById(a.dataset.goto)?.scrollIntoView({ behavior: "smooth" })));
  if (n.mindmap_md) {
    const { Transformer, Markmap } = window.markmap;
    const { root: data } = new Transformer().transform(n.mindmap_md);
    const mm = Markmap.create("#mm", { autoFit: true, duration: 300, maxWidth: 300, initialExpandLevel: 2,
      spacingVertical: 10, spacingHorizontal: 90, paddingX: 12 }, data);
    $("#mm-fit").addEventListener("click", () => mm.fit());
    $("#mm-expand").addEventListener("click", () => {
      const open = (node) => { node.payload = { ...node.payload, fold: 0 }; node.children?.forEach(open); };
      open(data); mm.setData(data); mm.fit();
    });
  }
  renderDiagrams(root);
}

/* ---------- onglet S'entraîner ---------- */
function tabReviser(root) {
  const n = state.data.notes, user = state.data.user || {};
  const srs = user.srs || {};
  const dueN = n.flashcards.filter((_, i) => !srs[i] || srs[i].due <= today()).length;
  const mastered = n.flashcards.filter((_, i) => (srs[i]?.box || 0) >= 3).length;
  root.innerHTML = `<div class="prose" style="max-width:900px">
    <div class="card row" style="gap:18px">
      <div class="spacer"><h2 style="margin:0">🃏 Flashcards</h2>
        <p class="muted" style="margin:4px 0 0">${n.flashcards.length} cartes · ${mastered} maîtrisées · ${dueN} à revoir maintenant</p>
        <div class="mastery" style="margin-top:10px"><i style="width:${100 * mastered / (n.flashcards.length || 1)}%"></i></div></div>
      <button class="btn primary big" id="start-cards" ${dueN ? "" : "disabled"}>${dueN ? "Réviser les cartes" : "Tout est à jour ✓"}</button>
      <button class="btn" id="all-cards">Revoir toutes les cartes</button>
    </div>
    <h2>✅ Quiz <small class="muted" id="quiz-score"></small></h2><div id="quiz"></div>
    <h2>📝 Sujets d'examen probables</h2><p class="muted">Essaie de faire le plan toi-même avant d'ouvrir la correction.</p>
    ${(n.exam_questions || []).map((q) => `<details class="exam"><summary>${esc(q.question)}</summary>${md(q.answer_outline_md)}</details>`).join("")}
  </div>`;
  const startSession = (all) => {
    const idxs = n.flashcards.map((_, i) => i).filter((i) => all || !srs[i] || srs[i].due <= today());
    const cards = idxs.map((i) => ({ ...n.flashcards[i], lid: state.lessonId, idx: i }));
    runSession(cards, "Flashcards", (c, ok) => post("/api/review/grade", { lid: c.lid, idx: c.idx, ok }),
      () => api(`/api/lessons/${state.lessonId}`).then((d) => { state.data = d; refreshLessons(); }), root);
  };
  $("#start-cards").addEventListener("click", () => startSession(false));
  $("#all-cards").addEventListener("click", () => startSession(true));

  const answers = { ...(user.quiz || {}) };
  const quiz = $("#quiz");
  const drawQuiz = () => {
    const good = Object.entries(answers).filter(([i, a]) => n.quiz[i]?.answer_index === a).length;
    const nAns = Object.keys(answers).length;
    $("#quiz-score").textContent = nAns ? `— ${good} / ${nAns} bonnes réponses` : "";
    quiz.innerHTML = n.quiz.map((q, i) => {
      const a = answers[i];
      return `<div class="quiz-q card"><b>${i + 1}. ${esc(q.question)}</b><div class="choices">
        ${q.choices.map((c, j) => `<button class="btn choice ${a === undefined ? "" : j === q.answer_index ? "right" : j === a ? "wrong" : ""}"
          data-q="${i}" data-c="${j}" ${a !== undefined ? "disabled" : ""}>${"ABCD"[j] || j + 1}. ${esc(c)}</button>`).join("")}</div>
        ${a !== undefined ? `<div class="quiz-expl">${a === q.answer_index ? "✅ Bravo ! " : "❌ "}${md(q.explanation)}</div>` : ""}</div>`;
    }).join("") + (nAns ? `<button class="btn" id="quiz-reset">↺ Recommencer le quiz</button>` : "");
    $$(".choice", quiz).forEach((b) => b.addEventListener("click", () => {
      answers[b.dataset.q] = +b.dataset.c; post(`/api/lessons/${state.lessonId}/user`, { quiz: answers }); drawQuiz();
    }));
    $("#quiz-reset")?.addEventListener("click", () => {
      for (const k in answers) delete answers[k]; post(`/api/lessons/${state.lessonId}/user`, { quiz: {} }); drawQuiz();
    });
  };
  drawQuiz();
}

/* ---------- onglet Transcription ---------- */
function tabTranscript(root) {
  const tr = state.data.transcript, fixes = state.data.notes?.transcript_fixes || [];
  const fix = (t) => fixes.reduce((s, f) => f.wrong ? s.split(f.wrong).join(f.right) : s, t);
  root.innerHTML = `<div class="layout">
    <div><input class="input" id="tsearch" placeholder="🔎 Rechercher un mot dans le cours…" style="margin-bottom:12px">
      <div id="tcount" class="muted" style="font-size:.85rem;margin:-4px 0 8px"></div>
      <div class="transcript">${tr.segments.map((s, i) => `<div class="tseg" data-i="${i}" data-seek="${s.start}">
        <span class="ts">${fmt(s.start)}</span><span>${s.speaker ? `<span class="spk">${esc(s.speaker)}</span>` : ""}<span class="tx">${esc(fix(s.text))}</span></span></div>`).join("")}</div></div>
    <aside class="side">${videoHtml()}<label class="check" style="font-size:.85rem"><input type="checkbox" id="follow" checked> Suivre la vidéo</label>
      <p class="muted"><small>Clique une phrase pour revoir ce moment. Transcrit avec ${esc(tr.engine)}${fixes.length ? ` · ${fixes.length} correction(s) automatique(s)` : ""}.</small></p></aside></div>`;
  const segs = $$(".tseg", root);
  let lastI = -1;
  $("#video")?.addEventListener("timeupdate", (e) => {
    const t = e.target.currentTime;
    const i = tr.segments.findLastIndex((s) => s.start <= t);
    if (i === lastI) return;
    segs[lastI]?.classList.remove("now"); segs[i]?.classList.add("now"); lastI = i;
    if ($("#follow").checked && !e.target.paused) segs[i]?.scrollIntoView({ block: "center", behavior: "smooth" });
  });
  $("#tsearch").addEventListener("input", (e) => {
    const q = e.target.value.trim().toLowerCase();
    let n = 0;
    segs.forEach((el, i) => {
      const txt = fix(tr.segments[i].text);
      const hit = !q || txt.toLowerCase().includes(q);
      n += hit && q ? 1 : 0;
      el.style.display = hit ? "" : "none";
      $(".tx", el).innerHTML = q && hit ? esc(txt).replace(new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), (m) => `<mark>${m}</mark>`) : esc(txt);
    });
    $("#tcount").textContent = q ? `${n} passage(s) trouvé(s)` : "";
  });
}

/* ---------- onglet Tuteur ---------- */
const SUGGESTIONS = ["Résume-moi ce cours en 5 points essentiels", "Quelles sont les notions les plus difficiles et pourquoi ?",
  "Fais-moi un plan de dissertation sur le thème principal", "Pose-moi 3 questions pour vérifier que j'ai compris",
  "Donne-moi un cas pratique corrigé"];
function tabTuteur(root) {
  if (!state.chat.length) state.chat = state.data.user?.chat || [];
  root.innerHTML = `<div class="chat-wrap"><div class="chat" id="chat"></div>
    <div class="suggestions" id="sugg"></div>
    <form class="chat-form" id="chat-form">
      <textarea class="input" name="q" rows="1" placeholder="Pose ta question sur le cours… (Entrée pour envoyer)"></textarea>
      <button class="btn primary">Envoyer</button></form>
    ${state.chat.length ? `<button class="btn sm ghost" id="chat-clear" style="margin-top:8px">Effacer la conversation</button>` : ""}</div>`;
  const ta = $("textarea", root);
  const draw = (thinking = false) => {
    $("#chat").innerHTML = (state.chat.length ? state.chat.map((m) => `<div class="msg ${m.role === "user" ? "user" : "bot"} ${m.role === "user" ? "" : "prose"}">
      ${m.role === "user" ? esc(m.content) : md(m.content) + (m.timestamps?.length ? `<p class="row" style="gap:6px">${m.timestamps.map((t) => `<a class="ts-link" data-seek="${t}">▶ ${fmt(t)}</a>`).join("")}</p>` : "")}</div>`).join("")
      : `<div class="empty">💬 Ton tuteur connaît tout le cours et peut chercher sur le web.<br>Demande une explication, un exemple, un plan, un entraînement…</div>`)
      + (thinking ? `<div class="msg bot typing"><span></span><span></span><span></span></div>` : "");
    $("#sugg").innerHTML = thinking ? "" : SUGGESTIONS.slice(0, state.chat.length ? 3 : 5).map((s) => `<button class="chip" type="button">${esc(s)}</button>`).join("");
    $$("#sugg .chip").forEach((b) => b.addEventListener("click", () => ask(b.textContent)));
  };
  const ask = async (q) => {
    q = q.trim(); if (!q) return;
    ta.value = "";
    state.chat.push({ role: "user", content: q });
    draw(true);
    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
    try {
      const r = await post(`/api/lessons/${state.lessonId}/ask`, { question: q, history: state.chat.slice(0, -1) });
      state.chat.push({ role: "assistant", content: r.answer_md, timestamps: r.timestamps });
    } catch (err) {
      state.chat.push({ role: "assistant", content: "⚠️ " + friendlyError(err.message) });
    }
    draw();
    post(`/api/lessons/${state.lessonId}/user`, { chat: state.chat.slice(-30) });
  };
  draw();
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(ta.value); } });
  ta.addEventListener("input", () => { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 160) + "px"; });
  $("#chat-form").addEventListener("submit", (e) => { e.preventDefault(); ask(ta.value); });
  $("#chat-clear")?.addEventListener("click", () => { state.chat = []; post(`/api/lessons/${state.lessonId}/user`, { chat: [] }); tabTuteur(root); });
  if (state.pendingQuestion) { const q = state.pendingQuestion; state.pendingQuestion = null; ask(q); }
}

/* =================================================================== impression */
async function showPrint(id) {
  const d = await api(`/api/lessons/${id}`);
  const n = d.notes, deep = d.deep;
  state.lessonId = id;
  document.body.style.display = "block"; $("#sidebar").hidden = true;
  main.innerHTML = `<div class="print-page prose">
    <p class="no-print banner info">Utilise <b>Imprimer → Enregistrer en PDF</b> pour obtenir un PDF. <button class="btn primary" onclick="print()">Imprimer</button></p>
    <span class="pill">${esc(n.subject)}</span><h1>${esc(d.meta.title || n.title)}</h1><p><i>${esc(n.one_line)}</i></p>
    <h2>Résumé</h2>${md(n.summary_md)}<div class="problem">${esc(n.problematique)}</div>
    ${n.sections.map((s) => `<section class="section"><h2>${esc(s.title)}</h2>${md(s.notes_md)}
      ${s.diagram?.kind === "mermaid" && s.diagram.code ? diagramBox(s.diagram, `section:${s.id}`) : ""}
      ${s.key_points?.length ? `<div class="keypoints"><h4>À retenir</h4><ul>${s.key_points.map((k) => `<li>${esc(k)}</li>`).join("")}</ul></div>` : ""}</section>`).join("")}
    ${n.definitions?.length ? `<h2>Lexique</h2><table><tbody>${n.definitions.map((x) => `<tr><th>${esc(x.term)}</th><td>${esc(x.definition)}</td></tr>`).join("")}</tbody></table>` : ""}
    ${(deep?.explanations || []).map((e) => `<h2>Pour bien comprendre : ${esc(e.concept)}</h2>${md(e.simple_md)}<p><b>Analogie :</b> ${esc(e.analogy)}</p>
      <p><b>Exemple :</b> ${esc(e.example)}</p>${md(e.expert_md)}`).join("")}
  </div>`;
  await renderDiagrams(main);
  setTimeout(() => print(), 600);
}

/* =================================================================== réglages */
async function showSettings() {
  const s = await refreshStatus();
  const c = s.config;
  const opt = (v, cur, l) => `<option value="${v}" ${v === cur ? "selected" : ""}>${l}</option>`;
  const engineLabel = { parakeet: "Parakeet v3 — local, rapide, très précis (recommandé)", "mlx-whisper": "Whisper turbo — local, suit mieux le vocabulaire",
    "faster-whisper": "Whisper turbo — local (PC)", elevenlabs: "ElevenLabs Scribe — en ligne, le plus précis (~0,25 $/h, clé requise)",
    mistral: "Mistral Voxtral — en ligne, le moins cher (~0,18 $/h, clé requise)" };
  main.innerHTML = `<div class="page narrow"><h1>Réglages</h1>
    ${s.update?.available ? bannersHtml({ codex: { ok: true }, update: s.update }) : ""}
    <form class="settings" id="settings">
      <fieldset><legend>Compte ChatGPT</legend>
        <div class="row"><span class="dot ${s.codex.ok ? "ok" : "err"}"></span><span class="spacer">${s.codex.ok ? "Connecté — l'IA utilise ton abonnement ChatGPT." : "Non connecté."}</span>
          <button class="btn ${s.codex.ok ? "" : "primary"}" type="button" data-action="codex-login">${s.codex.ok ? "Changer de compte" : "Se connecter"}</button></div>
        <label class="field"><span>Qualité de l'IA</span><select class="input" name="codex_model">
          ${opt("", c.codex_model, "Maximale — recommandé")}${opt("gpt-6-luna", c.codex_model, "Rapide — si le quota ChatGPT est souvent atteint")}</select>
          <span class="help">Si le quota est atteint pendant une analyse, l'appli bascule automatiquement sur le modèle rapide.</span></label>
        <label class="check"><input type="checkbox" name="web_research" ${c.web_research ? "checked" : ""}> Vérifier et approfondir avec des recherches sur le web</label>
        <label class="check"><input type="checkbox" name="explainer_videos" ${c.explainer_videos ? "checked" : ""}> Créer des animations explicatives</label>
      </fieldset>
      <fieldset><legend>Affichage</legend>
        <div class="row"><span class="spacer">Thème</span><div class="seg" id="seg-theme">${[["auto", "Auto"], ["light", "Clair"], ["dark", "Sombre"]].map(([v, l]) =>
          `<button type="button" data-v="${v}" class="${(prefs.theme || "auto") === v ? "on" : ""}">${l}</button>`).join("")}</div></div>
        <div class="row"><span class="spacer">Taille du texte des fiches</span><div class="seg" id="seg-size">${[["s", "Petit"], ["", "Normal"], ["l", "Grand"], ["xl", "Très grand"]].map(([v, l]) =>
          `<button type="button" data-v="${v}" class="${(prefs.size || "") === v ? "on" : ""}">${l}</button>`).join("")}</div></div>
      </fieldset>
      <fieldset><legend>Transcription</legend>
        <label class="field"><span>Moteur</span><select class="input" name="asr_engine">
          ${opt("auto", c.asr_engine, `Automatique (${engineLabel[s.engine_auto]?.split(" —")[0] || "en ligne"})`)}
          ${s.engines.map((e) => opt(e, c.asr_engine, engineLabel[e] || e)).join("")}</select></label>
        <label class="check"><input type="checkbox" name="diarization" ${c.diarization ? "checked" : ""}> Distinguer les personnes qui parlent (questions d'étudiants, plusieurs profs…)</label>
      </fieldset>
      <details class="card" style="padding:14px 20px"><summary><b>Avancé</b> <span class="muted">— clés API (facultatif)</span></summary>
        <div class="settings" style="margin-top:14px">
          <label class="field"><span>Fournisseur d'IA</span><select class="input" name="llm_provider">
            ${opt("codex", c.llm_provider, "Codex — abonnement ChatGPT")}${opt("openrouter", c.llm_provider, "OpenRouter (payant à l'usage)")}${opt("anthropic", c.llm_provider, "Claude API (payant à l'usage)")}</select></label>
          <label class="field"><span>Clé OpenRouter</span><input class="input" name="openrouter_api_key" value="${esc(c.openrouter_api_key)}" type="password"></label>
          <label class="field"><span>Modèle OpenRouter</span><input class="input" name="openrouter_model" value="${esc(c.openrouter_model)}"></label>
          <label class="field"><span>Clé API Claude</span><input class="input" name="anthropic_api_key" value="${esc(c.anthropic_api_key)}" type="password"></label>
          <label class="field"><span>Clé ElevenLabs</span><input class="input" name="elevenlabs_api_key" value="${esc(c.elevenlabs_api_key)}" type="password"></label>
          <label class="field"><span>Clé Mistral</span><input class="input" name="mistral_api_key" value="${esc(c.mistral_api_key)}" type="password"></label>
        </div></details>
      <div class="row"><span class="muted spacer" style="font-size:.85rem">Version ${esc(s.version)} · cours enregistrés dans ${esc(s.data_dir)}</span>
        <button class="btn" type="button" id="check-update">Rechercher une mise à jour</button></div>
    </form></div>`;
  bindBanners();
  $$("[data-action=codex-login]").forEach((b) => b.addEventListener("click", codexLogin));
  const form = $("#settings");
  // enregistrement automatique à chaque modification
  form.addEventListener("change", async (e) => {
    if (!e.target.name) return;
    const body = { [e.target.name]: e.target.type === "checkbox" ? e.target.checked : e.target.value };
    await post("/api/config", body); toast("✓ Enregistré", 1500);
  });
  $$("#seg-theme button").forEach((b) => b.addEventListener("click", () => {
    setPref("theme", b.dataset.v); $$("#seg-theme button").forEach((x) => x.classList.toggle("on", x === b)); initMermaid();
  }));
  $$("#seg-size button").forEach((b) => b.addEventListener("click", () => {
    setPref("size", b.dataset.v); $$("#seg-size button").forEach((x) => x.classList.toggle("on", x === b));
  }));
  $("#check-update").addEventListener("click", async () => {
    const u = await api("/api/update?force=1").catch((e) => ({ error: e.message }));
    if (u.available) { await refreshStatus(); showSettings(); }
    else toast(u.error ? "Impossible de vérifier : " + u.error : "✓ Tu as la dernière version");
  });
}

/* =================================================================== démarrage */
refreshStatus();
refreshLessons();
route();
setInterval(refreshLessons, 15000);
