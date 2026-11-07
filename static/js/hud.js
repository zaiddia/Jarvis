/* J.A.R.V.I.S. — lógica del HUD flotante */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const body = document.body;
  const root = document.documentElement;
  const el = {
    shell: $("#shell"), reactor: $("#reactor"), orb: $("#orb"), mode: $("#mode"),
    preview: $("#preview"), chat: $("#chat"), log: $("#log"),
    viewChat: $("#view-chat"), viewLog: $("#view-log"),
    input: $("#input"), bar: $("#bar"), btnMic: $("#btn-mic"), btnSize: $("#btn-size"),
  };

  const params = new URLSearchParams(location.search);
  body.dataset.size = params.get("size") || "compacto";
  body.classList.toggle("solid", params.get("solid") === "1");   // fondo sólido (sin transparencia)

  let current = {};                 // ajustes públicos
  let st = { mode: "idle" };        // estado en vivo
  let native = true;                // ¿ventana propia (pywebview) o navegador?
  let hasMessages = false;

  let tutorOn = false;                                     // 9.4: modo tutor socrático
  const MODES = { idle: "EN ESPERA", awaiting: "TE ESCUCHO…", thinking: "PROCESANDO", speaking: "RESPONDIENDO" };
  let dictating = false;

  /* ---------------- Temporizadores ---------------- */
  const timersBox = document.getElementById("timers");
  let timers = [];        // [{id,label,remaining,total}]
  let lastTick = Date.now();

  function fmtClock(s) {
    s = Math.max(0, Math.round(s));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
    const p = (n) => String(n).padStart(2, "0");
    return h ? `${h}:${p(m)}:${p(ss)}` : `${m}:${p(ss)}`;
  }
  function renderTimers() {
    timersBox.hidden = timers.length === 0;
    timersBox.innerHTML = "";
    timers.forEach((t) => {
      const el = document.createElement("div");
      el.className = "tmr" + (t.remaining <= 10 ? " urgent" : "");
      const time = document.createElement("span");
      time.className = "tmr-time";
      time.textContent = "⏱ " + fmtClock(t.remaining);
      el.appendChild(time);
      if (t.label) {
        const lab = document.createElement("span");
        lab.className = "tmr-label";
        lab.textContent = t.label;
        el.appendChild(lab);
      }
      timersBox.appendChild(el);
    });
  }
  function setTimers(list) {
    timers = list;
    lastTick = Date.now();
    renderTimers();
    if (list.length) poke();
  }
  // Cuenta regresiva suave entre mensajes del servidor (que llegan cada segundo)
  setInterval(() => {
    if (!timers.length) return;
    const now = Date.now();
    const dt = (now - lastTick) / 1000;
    lastTick = now;
    let changed = false;
    timers.forEach((t) => { const r = Math.max(0, t.remaining - dt); if (Math.round(r) !== Math.round(t.remaining)) changed = true; t.remaining = r; });
    if (changed) renderTimers();
  }, 250);

  /* ---------------- 7.0: tarjetas holográficas ---------------- */
  const holo = { box: $("#holo"), t: $("#holo-t"), i: $("#holo-i"), b: $("#holo-b"), time: $("#holo-time"),
                 steps: $("#holo-steps"), bar: $("#holo-bar"), timer: null };
  function holoBody(text) {
    // Números con su unidad, resaltados (23 grados, 15 minutos, 07:30, 40 %)
    const frag = document.createDocumentFragment();
    const re = /(\d+(?:[.,:]\d+)?\s?(?:%|por ciento|grados|°|minutos?|horas?|segundos?|pasos?)?)/g;
    let last = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > last) frag.append(text.slice(last, m.index));
      const b = document.createElement("b"); b.textContent = m[0]; frag.append(b);
      last = m.index + m[0].length;
    }
    if (last < text.length) frag.append(text.slice(last));
    return frag;
  }
  function showCard(c) {
    if (!c || body.dataset.size === "orbe") { el.reactor.classList.add("ping"); setTimeout(() => el.reactor.classList.remove("ping"), 900); return; }
    holo.box.dataset.kind = c.kind || "";
    holo.i.textContent = c.icon || "✦";
    holo.t.textContent = c.title || "";
    holo.time.textContent = c.time || "";
    holo.b.textContent = "";
    holo.b.append(holoBody(String(c.body || "")));
    holo.steps.hidden = !c.steps;
    holo.steps.innerHTML = "";
    (c.steps || []).forEach((s, i) => {
      const d = document.createElement("i");
      d.className = i < c.step ? "done" : i === c.step ? "now" : "";
      d.title = s;
      holo.steps.appendChild(d);
    });
    holo.box.hidden = false;
    holo.box.classList.remove("in"); void holo.box.offsetWidth; holo.box.classList.add("in");
    const secs = Math.max(3, Math.min(30, c.secs || 9));
    holo.bar.style.transition = "none"; holo.bar.style.width = "100%"; void holo.bar.offsetWidth;
    holo.bar.style.transition = `width ${secs}s linear`; holo.bar.style.width = "0%";
    clearTimeout(holo.timer);
    holo.timer = setTimeout(() => { holo.box.classList.add("out"); setTimeout(() => { holo.box.hidden = true; holo.box.classList.remove("out"); }, 380); }, secs * 1000);
    poke();
  }
  $("#holo").addEventListener("click", () => { clearTimeout(holo.timer); holo.box.hidden = true; });

  /* ---------------- Utilidades ---------------- */
  function setTheme(name) { root.dataset.theme = name || "cyan"; }

  function hint() {
    if (st.mic === "error") return "El micrófono falló · mira el registro o elige otro en Ajustes › Escucha";
    if (st.mic !== "on") return current.mic_enabled === false ? "Micrófono en pausa · pulsa el botón del micrófono para activarlo"
      : "Activando el micrófono…";
    if (!current.wake_word_enabled) return "Te escucho · habla o escribe una orden";
    const w = (current.wake_words || "jarvis").split(",")[0].trim();
    return `Di «${w.charAt(0).toUpperCase() + w.slice(1)}» o escribe una orden`;
  }

  function texPlain(f) {
    for (let i = 0; i < 4; i++) {
      f = f.replace(/\\sqrt\{([^{}]*)\}/g, (m, a) => (/^\w+$/.test(a) ? "√" + a : `√(${a})`))
        .replace(/\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}/g, (m, a, b) => `${/^[\w.]+$/.test(a) ? a : "(" + a + ")"}/${/^[\w.]+$/.test(b) ? b : "(" + b + ")"}`);
    }
    return f.replace(/\\(pm|cdot|times|leq?|geq?|neq|pi)\b/g, (x, o) => ({ pm: "±", cdot: "·", times: "×", le: "≤", leq: "≤", ge: "≥", geq: "≥", neq: "≠", pi: "π" }[o]))
      .replace(/\^\{?2\}?/g, "²").replace(/\^\{?3\}?/g, "³").replace(/\\[a-zA-Z]+/g, "").replace(/[{}]/g, "");
  }
  function setPreview(text, cls = "") {
    el.preview.className = `preview ${cls}`;
    text = String(text).replace(/\$\$?([^$]+)\$\$?/g, (m, f) => texPlain(f));   // 11.8: sin LaTeX crudo
    el.preview.textContent = String(text).replace(/\*\*|`/g, "").replace(/\n\s*(?:[-•*]|\d+[.)])\s+/g, " · ").replace(/\s*\n\s*/g, " ");
    void el.preview.offsetWidth;
    el.preview.classList.add("flash");
  }

  function setLevel(v) { el.reactor.style.setProperty("--lvl", v); el.shell.style.setProperty("--lvl", v); }

  function updateSizeButton() {
    const expanded = body.dataset.size === "expandido";
    $("use", el.btnSize).setAttribute("href", expanded ? "#i-collapse" : "#i-expand");
    el.btnSize.title = expanded ? "Reducir" : "Expandir";
  }
  updateSizeButton();

  /* ---------------- Atenuación en reposo ---------------- */
  let lastActivity = Date.now();
  let pendingN = 0, momentInfo = null, momentAt = 0;
  function poke() { lastActivity = Date.now(); body.classList.remove("dim"); }
  ["mousemove", "mousedown", "keydown", "wheel"].forEach((e) => document.addEventListener(e, poke, { passive: true }));
  setInterval(() => {
    const idle = st.mode === "idle" && document.activeElement !== el.input;
    const busy = body.classList.contains("inclass") || body.classList.contains("working") || body.classList.contains("projecting") ||
      timers.length > 0 || pendingN > 0 || dictating;                            // 11.8: en clase, con pendientes o trabajando no se apaga
    body.classList.toggle("dim", !!current.hud_dim_idle && idle && !busy && Date.now() - lastActivity > 9000);
  }, 1000);

  /* ---------------- 12.0: rostro holográfico ---------------- */
  let face = null;
  function setFace(on) {
    body.classList.toggle("has-face", on);
    if (on && !face && window.JarvisFace) { const box = document.createElement("div"); box.className = "face-box"; el.reactor.appendChild(box); face = window.JarvisFace(box, {}); face.mode(st.mode); }
    if (!on && face) { face.el.parentNode.remove(); face = null; }
  }

  /* ---------------- Estado ---------------- */
  function led(id, s) { $(id).dataset.s = s; }
  function applyState(s) {
    st = { ...st, ...s };
    if (face) face.mode(st.mode);
    body.dataset.state = st.mode || "idle";
    if (dictating) { el.mode.textContent = "✎ DICTANDO"; } else
    el.mode.textContent = (tutorOn ? "🎓 TUTOR · " : "") + (st.resting ? "· DESCANSANDO · " : st.viewing ? (st.viewing === "camara" ? "◉ VIENDO CÁMARA · " : "◉ VIENDO PANTALLA · ")
      : st.live && st.mode !== "speaking" ? "● EN VIVO · " : "") + ((st.mode || "idle") === "idle" && momentText() ? momentText() : (MODES[st.mode] || MODES.idle));
    led("#led-mic", { on: "on", off: "off", error: "err" }[st.mic] || "off");
    led("#led-ai", { ok: "on", warn: "warn", error: "err" }[st.ai] || "off");
    led("#led-tts", { ok: "on", off: "off", error: "err" }[st.tts] || "off");
    $("#led-mic").title = `Micrófono: ${st.mic || "—"}`;
    $("#led-ai").title = `IA: ${st.ai_label || st.ai || "—"}`;
    $("#led-tts").title = `Voz: ${st.tts || "—"}`;
    $("#led-cop").hidden = !st.copilot;           // copiloto activo: mira tu pantalla
    $("#led-net").hidden = st.net !== "offline";  // sin internet: modo local
    if (st.mode !== "idle") poke();
    if (st.mode === "awaiting") setPreview("Te escucho… di tu orden", "dim");
    if (st.mode === "speaking") setLevel(0);
    if (!hasMessages && st.mode === "idle") setPreview(hint(), "dim");
  }

  function momentText() {                                                         // 11.8: «EN CLASE · 7A · 12 MIN», «10A EN 8 MIN»…
    const m = momentInfo;
    if (!m) return "";
    const el2 = Math.floor((Date.now() - momentAt) / 60000);
    if (m.id === "clase") { const f = m.falta != null ? Math.max(0, m.falta - el2) : null; return `EN CLASE${m.curso ? " · " + m.curso : ""}${f != null ? " · " + f + " MIN" : ""}`; }
    if (m.siguiente && m.en != null && m.en - el2 <= 60) { const e = Math.max(0, m.en - el2); return `${(m.curso || m.siguiente).toUpperCase()} ${e ? "EN " + e + " MIN" : "AHORA"}`; }
    return String(m.titulo || "").toUpperCase();
  }
  setInterval(() => { if (momentInfo) applyState({}); }, 30000);
  function applySettings(s) {
    current = s || {};
    setTheme(current.theme);
    root.dataset.look = current.look || "clasico";                                // 12.6: estilo Aurora o Clásico
    body.dataset.text = current.hud_text_size || "normal";                       // 11.8: tamaño de la letra
    setFace(!!current.hud_avatar);                                                // 12.0: rostro holográfico en vez del reactor
    el.shell.style.setProperty("--alpha", body.classList.contains("solid")
      ? 0.96 : (current.hud_opacity || 82) / 100);
    const on = !!current.mic_enabled;
    el.btnMic.classList.toggle("off", !on);
    $("use", el.btnMic).setAttribute("href", on ? "#i-mic" : "#i-mic-off");
    el.btnMic.title = on ? "Pausar micrófono" : "Activar micrófono";
    applyState({});
  }

  /* ---------------- Conversación y registro ---------------- */
  const nearBottom = (b) => b.scrollHeight - b.scrollTop - b.clientHeight < 60;

  let lastDay = "";
  function addChat(item, live = true) {
    $(".empty", el.chat)?.remove();
    hasMessages = true;
    const m = document.createElement("div");
    const isUser = item.role === "user";
    m.className = `msg ${isUser ? "user" : "jarvis"}${item.source === "PC" ? " pc" : ""}`;
    if (!isUser && /^(No pude|No puedo|Falta |Faltan |Error|No encontré|Sin conexión|No hay conexión)/i.test(item.text || "")) m.classList.add("err");   // 12.6: errores con barra roja
    if (!live) m.style.animation = "none";
    const meta = document.createElement("div");
    meta.className = "msg-meta";
    const SRC = { voz: "VOZ", telegram: "CELULAR", orbe: "REACTOR", movil: "PANEL DEL CELULAR", mcp: "OTRA IA" };
    meta.textContent = isUser ? "TÚ" + (SRC[item.source] ? " · " + SRC[item.source] : "") : "JARVIS";
    const day = item.date || "";
    if (day && day !== lastDay) {                                   // 9.2: separador por día
      lastDay = day;
      const today = new Date(), y = new Date(Date.now() - 864e5);
      const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      const sep = document.createElement("div");
      sep.className = "day";
      sep.textContent = day === iso(today) ? "Hoy" : day === iso(y) ? "Ayer" : `${day.slice(8, 10)}/${day.slice(5, 7)}/${day.slice(0, 4)}`;
      el.chat.appendChild(sep);
    }
    const t = document.createElement("span");
    t.className = "t";
    t.textContent = item.time || "";
    meta.append(t);
    const b = document.createElement("div");
    b.className = "msg-body";
    if (isUser) b.textContent = item.text; else b.innerHTML = window.JMD ? window.JMD.md(item.text) : md(item.text);
    m.append(meta, b);
    if (!isUser && item.text && item.text.length > 2) {                       // 11.8: proyectar, Word, más corto, en voz, graficar
      $$(".msg.lastj", el.chat).forEach((x) => x.classList.remove("lastj"));
      m.classList.add("lastj");
      m.append(msgActions(item.text));
    }
    if (!isUser) {                                          // 9.0: copiar la respuesta
      const cp = document.createElement("button");
      cp.type = "button"; cp.className = "copy"; cp.title = "Copiar"; cp.textContent = "Copiar";
      cp.addEventListener("click", () => navigator.clipboard.writeText(item.text).then(() => { cp.textContent = "✓ Copiado"; setTimeout(() => (cp.textContent = "Copiar"), 1400); }, () => {}));
      meta.append(cp);
    }
    $(".msg.typing", el.chat)?.remove();
    const stick = nearBottom(el.viewChat);
    el.chat.appendChild(m);
    if (!stick && !isUser && live) newBelow(true);
    while (el.chat.children.length > 160) el.chat.firstChild.remove();
    if (stick || isUser) el.viewChat.scrollTop = el.viewChat.scrollHeight;
    if (live) setPreview(isUser ? `› ${item.text}` : item.text, isUser ? "user" : "");
  }

  function msgActions(text) {
    const box = mk("div", "macts");
    const act = (label, action, ok) => {
      const bt = mk("button", "", label); bt.type = "button";
      bt.addEventListener("click", () => socket.emit("msg_action", { text, action }, (r) => {
        if (r && r.ok) { bt.classList.add("done"); setTimeout(() => bt.classList.remove("done"), 1600); if (ok) setPreview(ok, "dim"); }
        else setPreview((r && r.error) || "No se pudo.", "dim");
      }));
      box.append(bt);
    };
    act("▣ Proyectar", "proyectar", "Listo, en el proyector.");
    act("Word", "word", "Listo el Word.");
    if (text.length > 220) act("Más corto", "corto");
    act("🔊 Oír", "voz");
    if (window.JMD && window.JMD.graphable(text)) act("📈 Graficar", "graficar");
    return box;
  }

  /* 9.0: formato ligero (negritas, cursivas, código y listas) sobre texto ya escapado: nunca se inserta HTML ajeno */
  function esc(s) { return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
  function inline(s) {
    return s.replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
      .replace(/(^|[\s(«])\*([^*\n]+)\*(?=[\s.,;:!?)»]|$)/g, "$1<i>$2</i>").replace(/(^|[\s(«])_([^_\n]+)_(?=[\s.,;:!?)»]|$)/g, "$1<i>$2</i>");
  }
  function md(text) {
    const lines = esc(text).split("\n");
    let out = "", list = "";
    const close = () => { if (list) { out += `</${list}>`; list = ""; } };
    lines.forEach((ln) => {
      let m;
      if ((m = ln.match(/^\s*(?:[-•*]|·)\s+(.*)$/))) { if (list !== "ul") { close(); out += "<ul>"; list = "ul"; } out += `<li>${inline(m[1])}</li>`; }
      else if ((m = ln.match(/^\s*\d+[.)]\s+(.*)$/))) { if (list !== "ol") { close(); out += "<ol>"; list = "ol"; } out += `<li>${inline(m[1])}</li>`; }
      else { close(); out += ln.trim() ? `<p>${inline(ln)}</p>` : ""; }
    });
    close();
    return out;
  }
  function showTyping(on) {
    const cur = $(".msg.typing", el.chat);
    if (!on) { cur?.remove(); return; }
    if (cur) return;
    const m = document.createElement("div");
    m.className = "msg jarvis typing";
    m.innerHTML = '<div class="msg-meta">JARVIS</div><div class="msg-body"><i></i><i></i><i></i></div>';
    const stick = nearBottom(el.viewChat);
    el.chat.appendChild(m);
    if (stick) el.viewChat.scrollTop = el.viewChat.scrollHeight;
  }
  const btnNew = document.createElement("button");
  btnNew.type = "button"; btnNew.className = "newbelow"; btnNew.textContent = "↓ Nuevos mensajes"; btnNew.hidden = true;
  btnNew.addEventListener("click", () => { el.viewChat.scrollTop = el.viewChat.scrollHeight; newBelow(false); });
  el.viewChat.after(btnNew);
  function newBelow(on) { btnNew.hidden = !on; }
  // Las órdenes sugeridas en una respuesta (en `código`) se copian a la barra con un clic
  el.chat.addEventListener("click", (e) => {
    const c = e.target.closest(".msg.jarvis code");
    if (!c) return;
    el.input.value = c.textContent; el.input.focus();
  });
  el.viewChat.addEventListener("scroll", () => { if (nearBottom(el.viewChat)) newBelow(false); }, { passive: true });

  let lastDash = null;
  function emptyChat() {
    lastDay = "";
    el.chat.innerHTML = "";
    el.chat.append(mk("div", "empty welcome"));
    hasMessages = false;
    drawWelcome();
  }
  function drawWelcome() {                                                       // 11.8: inicio útil según el momento del día
    const w = $(".empty.welcome", el.chat);
    if (!w) return;
    w.textContent = "";
    const h = new Date().getHours();
    const mo = lastDash && lastDash.momento;
    w.append(mk("div", "wh", (h < 12 ? "Buenos días" : h < 19 ? "Buenas tardes" : "Buenas noches") + (mo ? ` · ${mo.titulo}` : "")));
    let sub = "Pídeme lo que necesites por voz o escribiendo.";
    if (mo) {
      if (mo.id === "clase") sub = `Estás en clase${mo.curso ? " con " + mo.curso : ""}${mo.tema ? " · " + mo.tema : ""}${mo.falta != null ? ` · faltan ${mo.falta} min` : ""}.`;
      else if (mo.siguiente) sub = `Tu próxima clase: ${mo.siguiente}, ${mo.en <= 0 ? "ahora" : mo.en < 60 ? "en " + mo.en + " min" : "a las " + mo.a_las}${mo.tema ? " · tema: " + mo.tema : ""}.`;
      else if (mo.id === "noche") sub = (mo.manana || []).length ? `Mañana tienes ${mo.manana.length} clase${mo.manana.length === 1 ? "" : "s"}: ${mo.manana.map((c) => c.t).join(", ")}.` : "Mañana no tienes clases en el horario.";
      const n = (lastDash.bandeja || []).length;
      if (n) sub += ` Tienes ${n} cosa${n === 1 ? "" : "s"} en la bandeja.`;
    }
    w.append(mk("div", "ws", sub));
    const acts = ((mo && mo.acciones) || []).slice(0, 4);
    if (acts.length) {
      const g = mk("div", "wb");
      acts.forEach((a) => { const b = mk("button", "", a.t); b.type = "button"; b.addEventListener("click", () => run(a.cmd)); g.append(b); });
      w.append(g);
    }
    w.append(mk("div", "wt", "Ctrl+K busca una orden · arrastra un archivo para leerlo · «hazme una ilustración de…»"));
  }

  function logClass(line) {
    if (line.includes("[ERROR]")) return "error";
    if (line.includes("[AVISO]")) return "warn";
    if (line.includes("[USUARIO]")) return "user";
    if (line.includes("[VOZ]")) return "voice";
    if (line.includes("[SISTEMA]") || line.includes("[VOSK]")) return "muted";
    if (/\[(JARVIS|PC|ALARMA|NUMEROLOGÍA|RUTINA|OFFICE|WHATSAPP)\]/.test(line)) return "jarvis";
    return "";
  }
  function addLog(line) {
    const d = document.createElement("div");
    d.className = logClass(line);
    d.textContent = line;
    const stick = nearBottom(el.viewLog);
    const lq = document.getElementById("log-q"), lf = document.querySelector(".lf.active");
    if (lf && lf.dataset.f !== "all" && !d.classList.contains(lf.dataset.f)) d.hidden = true;
    if (lq && lq.value && !d.textContent.toLowerCase().includes(lq.value.toLowerCase())) d.hidden = true;
    el.log.appendChild(d);
    while (el.log.children.length > 400) el.log.firstChild.remove();
    if (stick) el.viewLog.scrollTop = el.viewLog.scrollHeight;
  }

  /* ---------------- Socket ---------------- */
  if (typeof io === "undefined") { setPreview("No se pudo cargar Socket.IO.", "dim"); return; }
  const socket = io();
  window.JarvisHUD = {                                    // 12.13: para la píldora (pildora.js)
    socket, mode: () => st.mode || "idle", mic: () => st.mic || "off", settings: () => current, native: () => native,
    pending: () => pendingN, dictating: () => dictating, poke: () => poke(),
    dragging: () => body.classList.contains("dragging"), input: el.input,
  };

  /* ================= 8.6: panel «Hoy», tarjetas de archivos, sugerencias, paleta y subtítulos ================= */
  const dash = $("#dash"), viewHoy = $("#view-hoy"), chips = $("#chips"), xtabHoy = $("#xtab-hoy");
  function mk(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  let collapsed = {};
  try { collapsed = JSON.parse(localStorage.getItem("hud-collapsed") || "{}"); } catch (e) { collapsed = {}; }
  function card(title, extraCls = "", key = "") {
    const c = mk("section", "dcard " + extraCls);
    const h = mk("h4", "", title);
    key = key || title.split(" ·")[0];
    if (collapsed[key]) c.classList.add("folded");
    h.title = "Clic para plegar o desplegar";
    h.addEventListener("click", () => {
      c.classList.toggle("folded");
      collapsed[key] = c.classList.contains("folded");
      try { localStorage.setItem("hud-collapsed", JSON.stringify(collapsed)); } catch (e) { /* sin almacenamiento */ }
    });
    c.append(h);
    return c;
  }
  function weatherIcon(t) {
    const s = plain(t);
    return /tormenta|electric/.test(s) ? "⛈" : /lluv|llovizna|chubasc/.test(s) ? "🌧" : /nublado|nubes|cubierto/.test(s) ? "☁" :
      /niebla|bruma/.test(s) ? "🌫" : /parcial|algunas nubes/.test(s) ? "⛅" : /despejado|soleado|sol/.test(s) ? "☀" : "🌡";
  }

  function placeDash() {
    const wide = body.dataset.size === "expandido" && el.shell.clientWidth >= 640;
    body.classList.toggle("wide", wide);
    if (wide) { if (dash.parentNode !== el.shell) el.shell.insertBefore(dash, chips); }
    else if (dash.parentNode !== viewHoy) viewHoy.appendChild(dash);
    xtabHoy.hidden = wide;
    if (wide && !viewHoy.hidden) $('.xtab[data-view="chat"]').click();
  }
  window.addEventListener("resize", placeDash);
  /* ================= 9.2: campana de avisos, favoritos, tarjeta «Cursos», encabezado compacto y búsqueda ================= */
  // Encabezado compacto en el HUD expandido: la última línea va en la misma fila que el título
  const headEl = $(".head"), previewHome = el.preview.nextSibling;
  function placePreview() {
    if (body.dataset.size === "expandido") { if (el.preview.parentNode !== headEl) headEl.insertBefore(el.preview, $("#vu")); }
    else if (el.preview.parentNode === headEl) el.shell.insertBefore(el.preview, previewHome);
  }
  window.addEventListener("resize", placePreview);

  // Campana
  const ntc = { box: $("#ntc"), list: $("#ntc-list"), badge: $("#bell-n") };
  function setUnread(n) { ntc.badge.hidden = !n; ntc.badge.textContent = n > 9 ? "9+" : String(n); }
  function drawNotices(r) {
    ntc.list.innerHTML = "";
    const items = (r && r.items) || [];
    if (!items.length) ntc.list.append(mk("p", "dempty", "Sin avisos por ahora."));
    items.forEach((n) => {
      const row = mk("div", "ntc-item " + n.kind);
      row.append(mk("span", "ntc-k", { aviso: "🔔", aprobar: "✓", error: "⚠" }[n.kind] || "•"), mk("span", "ntc-t", n.text), mk("span", "ntc-h2", n.hora));
      if (n.kind === "aprobar") {
        row.classList.add("click"); row.addEventListener("click", () => { closeNotices(); if (body.classList.contains("wide")) { dashHidden = false; applyDashHidden(); } else $('.xtab[data-view="hoy"]').click(); });
        const ap = ((lastDash && lastDash.bandeja) || []).find((x) => x.tipo === "aprobar" && n.text.includes(x.t.slice(0, 40)));
        if (ap) {                                                                  // 11.8: aprobar desde la campana
          const bb = mk("span", "dbtns"), ok = mk("button", "mini ok", "Sí"), no = mk("button", "mini", "No"); ok.type = no.type = "button";
          const go = (yes) => (e) => { e.stopPropagation(); socket.emit("approval_resolve", { id: ap.id, ok: yes }, () => { refreshDash(); socket.emit("notices", { seen: true }, drawNotices); }); };
          ok.addEventListener("click", go(true)); no.addEventListener("click", go(false)); bb.append(ok, no); row.append(bb);
        }
      }
      ntc.list.append(row);
    });
    setUnread(r ? r.unread : 0);
  }
  function openNotices() { if (body.dataset.size !== "expandido") setSize("expandido"); ntc.box.hidden = false; body.classList.add("ntcopen"); socket.emit("notices", { seen: true }, drawNotices); }
  function closeNotices() { ntc.box.hidden = true; body.classList.remove("ntcopen"); }
  $("#btn-health").addEventListener("click", () => socket.emit("open_health"));       // 12.8: panel de salud
  $("#btn-bell").addEventListener("click", () => (ntc.box.hidden ? openNotices() : closeNotices()));
  $("#ntc-clear").addEventListener("click", () => socket.emit("notices", { clear: true, seen: true }, drawNotices));
  socket.on("notice", (n) => { setUnread(n.unread); if (!ntc.box.hidden) socket.emit("notices", { seen: true }, drawNotices); else { $("#btn-bell").classList.remove("ring"); void $("#btn-bell").offsetWidth; $("#btn-bell").classList.add("ring"); } });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !ntc.box.hidden) closeNotices(); });
  document.addEventListener("mousedown", (e) => { if (!ntc.box.hidden && !e.target.closest("#ntc, #btn-bell")) closeNotices(); });

  // Favoritos
  let favs = [];
  function toggleFav(cmd, cb) { socket.emit("favorite_toggle", { cmd }, (r) => { favs = r.favorites || []; refreshDash(); if (cb) cb(); }); }

  // Búsqueda en la conversación (Ctrl+F)
  const chatQ = $("#chat-q");
  function filterChat() {
    const q = plain(chatQ.value);
    $$(".msg, .day", el.chat).forEach((m) => { m.hidden = !!q && (m.classList.contains("day") || !plain(m.textContent).includes(q)); });
  }
  chatQ.addEventListener("input", filterChat);
  chatQ.addEventListener("keydown", (e) => { if (e.key === "Escape") { chatQ.value = ""; filterChat(); chatQ.hidden = true; el.input.focus(); } });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "f" && body.dataset.size === "expandido") {
      e.preventDefault(); $('.xtab[data-view="chat"]').click(); chatQ.hidden = false; chatQ.focus(); chatQ.select();
    }
  });


  /* ---------- 10.9: barra del año, modo clase, línea del día, mapa del curso y avisos con botones ---------- */
  const fmtMS = (sec) => `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
  function yearBar(a) {
    const box = mk("div", "ybar");
    const track = mk("div", "ytrack");
    const total = a.total || a.periodos.reduce((x, y) => x + y, 0);
    a.periodos.forEach((n, i) => {
      const seg = mk("i", "yseg" + (i + 1 === a.periodo ? " cur" : i + 1 < a.periodo ? " done" : ""));
      seg.style.flex = String(n); seg.title = `Periodo ${i + 1}: ${n} semanas`;
      track.append(seg);
    });
    if (a.semana) { const mkr = mk("b", "ymark"); mkr.style.left = `${Math.min(100, (a.semana - 0.5) / total * 100)}%`; track.append(mkr); }
    const info = mk("div", "yinfo");
    info.append(mk("span", "", a.semana ? `Semana ${a.semana}/${total} · P${a.periodo} (${a.semana_periodo}/${a.periodos[a.periodo - 1]})` : `Periodo ${a.periodo}`));
    if (a.plan) info.append(mk("span", a.plan.dif < -1 ? "ybad" : a.plan.dif < 0 ? "ywarn" : "yok",
      a.plan.dif === 0 ? "plan al día" : a.plan.dif > 0 ? `adelantado ${a.plan.dif}` : `atrasado ${-a.plan.dif} (${a.plan.curso})`));
    if (a.cierre != null && a.cierre >= 0) info.append(mk("span", a.cierre <= 7 ? "ywarn" : "", a.cierre === 0 ? "cierre hoy" : `cierre en ${a.cierre} d`));
    box.append(track, info);
    if (a.plan) { box.classList.add("click"); box.title = "¿Cómo voy con la planeación?"; box.addEventListener("click", () => run("¿cómo voy con la planeación?")); }
    return box;
  }
  let lcTimer = null;
  function inClassCard(e) {
    const k = card(momentInfo && momentInfo.id === "clase" ? "Clase guiada · momentos" : "En clase", "live", "EnClase");
    clearInterval(lcTimer);
    if (e.clase) {
      const cl = e.clase;
      k.append(mk("div", "lc-tema", `${cl.tema}${cl.curso ? " · " + cl.curso : ""}`));
      k.append(mk("div", "lc-mom", `${cl.i}/${cl.n} · ${cl.momento}`));
      const clock = mk("div", "lc-clock" + (cl.left <= 60 ? " end" : ""), fmtMS(cl.left));
      const t0 = Date.now(), left0 = cl.left;
      lcTimer = setInterval(() => { const l = Math.max(0, left0 - Math.round((Date.now() - t0) / 1000)); clock.textContent = fmtMS(l); clock.classList.toggle("end", l <= 60); }, 1000);
      const bar = mk("div", "dbar cls"); const i = mk("i"); i.style.width = `${Math.round(100 * (1 - cl.left / Math.max(1, cl.min * 60)))}%`; bar.append(i);
      const btns = mk("div", "dbtns");
      [["Siguiente", "siguiente momento"], ["+5 min", "dame 5 minutos más"], ["Terminar", "termina la clase"]].forEach(([t, cmd]) => {
        const b = mk("button", "mini" + (t === "Siguiente" ? " ok" : ""), t); b.type = "button"; b.addEventListener("click", () => run(cmd)); btns.append(b);
      });
      k.append(clock, bar, btns);
    }
    (e.qr || []).forEach((q) => {
      const r = mk("div", "drow lc-qr"); r.append(mk("span", "", "▣ " + q.t), mk("b", "", q.de ? `${q.n}/${q.de}` : String(q.n)));
      const b = mk("button", "mini", "Cerrar"); b.type = "button"; b.addEventListener("click", () => run(q.cmd)); r.append(b);
      k.append(r);
    });
    return k;
  }
  let dayOpen = null;
  function dayLine(dia) {
    const k = card(`Hoy · ${dia.length} clase${dia.length === 1 ? "" : "s"}`, "", "Clase");
    const tl = mk("div", "tline");
    const acts = mk("div", "tacts");
    dia.forEach((x, idx) => {
      const b = mk("div", "tblk " + x.estado);
      b.append(mk("span", "th", x.inicio), mk("b", "", x.curso || x.t), mk("span", "tm", x.t.replace(x.curso, "").trim()));
      const p = mk("i", "tprog"); p.style.width = `${Math.round(x.progreso * 100)}%`; b.append(p);
      b.title = `${x.t} · ${x.inicio}–${x.fin}`;
      b.addEventListener("click", () => { dayOpen = dayOpen === idx ? null : idx; showActs(); });
      tl.append(b);
    });
    function showActs() {
      acts.innerHTML = "";
      tl.querySelectorAll(".tblk").forEach((b, i) => b.classList.toggle("sel", i === dayOpen));
      if (dayOpen == null || !dia[dayOpen]) return;
      dia[dayOpen].acciones.forEach((a) => { const bt = mk("button", "mini", a.t); bt.type = "button"; bt.addEventListener("click", () => run(a.cmd)); acts.append(bt); });
    }
    if (dayOpen == null) { const cur = dia.findIndex((x) => x.estado === "ahora"); if (cur >= 0) dayOpen = cur; }
    showActs();
    k.append(tl, acts);
    return k;
  }
  // Mapa del curso: estudiantes × actividades coloreado por desempeño
  const map = { box: null };
  function openMap(curso) {
    if (body.dataset.size !== "expandido") setSize("expandido");
    socket.emit("course_map", { curso }, (r) => {
      if (!r || !r.rows) return;
      map.box?.remove();
      const box = mk("div", "cmap"); map.box = box;
      const head = mk("div", "cmap-h");
      head.append(mk("b", "", `Mapa · ${r.curso}`), mk("span", "dmeta", `${r.rows.length} estudiantes · ${r.acts.length} actividades`));
      const risk = mk("button", "mini", "En riesgo"); risk.type = "button"; risk.addEventListener("click", () => { box.remove(); run(`¿quiénes están en riesgo en ${r.curso}?`); });
      const zx = mk("button", "mini", "Zeti"); zx.type = "button"; zx.addEventListener("click", () => { box.remove(); run(`exporta las notas de ${r.curso} para Zeti`); });
      const close = mk("button", "mini", "✕"); close.type = "button"; close.addEventListener("click", () => box.remove());
      head.append(risk, zx, close);
      const sc = r.escala || { superior: 4.5, alto: 4.0, basico: 3.0 };
      const cls = (v) => (v == null ? "e" : v >= sc.superior ? "s" : v >= sc.alto ? "a" : v >= sc.basico ? "b" : "x");
      const grid = mk("div", "cmap-g");
      grid.style.gridTemplateColumns = `minmax(120px, 1.6fr) repeat(${r.acts.length}, minmax(22px, 1fr)) 44px`;
      grid.append(mk("span", "ch", "Estudiante"));
      r.acts.forEach((a) => { const h = mk("span", "ch act " + a.dim); h.append(mk("b", "", a.f), mk("small", "", a.a.slice(0, 12))); h.title = `${a.a} (${a.dim})`; grid.append(h); });
      grid.append(mk("span", "ch", "Val"));
      r.rows.forEach((row) => {
        const nm = mk("span", "cn", row.n); nm.title = "Ver su ficha"; nm.addEventListener("click", () => { box.remove(); run(`ficha de ${row.n} de ${r.curso}`); });
        grid.append(nm);
        row.c.forEach((v, i) => { const c = mk("i", "cc " + cls(v), v == null ? "" : Number(v).toFixed(1).replace(".", ",")); c.title = `${row.n} · ${r.acts[i].a}: ${v == null ? "sin nota" : v}`; grid.append(c); });
        grid.append(mk("b", "cv " + cls(row.val), row.val == null ? "—" : `${String(row.val).replace(".", ",")} ${row.letra}`));
      });
      box.append(head, grid);
      document.querySelector(".shell").append(box);
    });
  }
  // Avisos con botones: las aprobaciones nuevas salen como notificación con Sí / No / Ver
  const toastBox = mk("div", "toasts"); document.body.append(toastBox);
  const toasted = new Set();
  function toast(text, buttons, ms = 25000) {
    toastBox.classList.toggle("slim", body.dataset.size !== "expandido");          // 11.8: en el compacto, una sola línea
    const t = mk("div", "toast");
    t.append(mk("span", "tt", text));
    const bb = mk("div", "dbtns");
    buttons.forEach(([label, fn, ok]) => { const b = mk("button", "mini" + (ok ? " ok" : ""), label); b.type = "button"; b.addEventListener("click", () => { fn(); t.remove(); }); bb.append(b); });
    const x = mk("button", "mini", "✕"); x.type = "button"; x.addEventListener("click", () => t.remove()); bb.append(x);
    t.append(bb); toastBox.append(t);
    while (toastBox.children.length > 3) toastBox.firstChild.remove();
    setTimeout(() => t.remove(), ms);
    poke();
  }
  socket.on("approvals", (d) => {
    (d && d.pending || []).forEach((a) => {
      if (toasted.has(a.id)) return;
      toasted.add(a.id);
      const dashVisible = body.dataset.size === "expandido" && ((body.classList.contains("wide") && !dashHidden) || !viewHoy.hidden);
      if (dashVisible) { refreshDash(); return; }                                 // 11.8: ya se ve en la bandeja: sin aviso encima
      toast(`Por aprobar: ${a.titulo}`, [["Sí", () => socket.emit("approval_resolve", { id: a.id, ok: true }, refreshDash), true],
        ["No", () => socket.emit("approval_resolve", { id: a.id, ok: false }, refreshDash)],
        ["Ver", () => { setSize("expandido"); openNotices(); }]]);
    });
  });
  socket.on("connect", () => socket.emit("dashboard", {}, (d) => (d && d.aprobar || []).forEach((a) => toasted.add(a.id))));
  socket.on("notice", (n) => {                                                     // alertas importantes: también como aviso con botón
    if (!n || n.kind === "aprobar" || !/^(aviso|alerta|error)$/.test(n.kind || "")) return;
    if (!/alerta|recordatorio|venc|urgente|riesgo|perder|cierre|novedad/i.test(n.text)) return;
    toast(n.text.length > 160 ? n.text.slice(0, 157) + "…" : n.text, [["Ver", () => { setSize("expandido"); openNotices(); }, true]], 15000);
  });

  function renderDash(d) {
    if (!d) return;
    dash.innerHTML = "";
    const top = mk("div", "dtop");
    top.append(mk("span", "dclock", d.hora), mk("span", "ddate", d.fecha));
    if (d.clima) top.append(mk("span", "dweather", weatherIcon(d.clima) + "  " + d.clima));
    dash.append(top);
    if (d.anio) dash.append(yearBar(d.anio));                // 10.9: barra del año
    lastDash = d;
    const mo = d.momento;
    body.classList.toggle("inclass", !!d.en_clase || (mo && mo.id === "clase"));
    if (mo) {                                                // 11.8: el HUD según el momento del día
      const was = momentInfo && momentInfo.id;
      momentInfo = mo; momentAt = Date.now(); body.dataset.moment = mo.id;
      dash.append(momentCard(mo));
      if (mo.id === "clase" && was && was !== "clase" && !body.classList.contains("wide") && body.dataset.size === "expandido") $('.xtab[data-view="hoy"]').click();
      applyState({});
    }
    if (d.en_clase) dash.append(inClassCard(d.en_clase));    // 10.9: modo clase
    renderJobs(d.trabajos || []);
    if (d.bandeja) dash.append(inboxCard(d.bandeja));        // 11.8: una sola bandeja (aprobaciones y lo que necesita tu atención)
    else if (d.atencion && d.atencion.length) {              // 9.3: lo que necesita tu atención
      const k = card(`Atención · ${d.atencion.length}`, "att", "Atención");
      d.atencion.forEach((x) => {
        const r = mk("div", "drow click" + (x.p === 1 ? " hot" : ""));
        r.append(mk("span", "", (x.p === 1 ? "● " : "○ ") + x.t));
        r.addEventListener("click", () => (/\s$/.test(x.cmd) ? fill(x.cmd) : run(x.cmd)));
        k.append(r);
      });
      dash.append(k);
    }
    const c = d.clase || {};
    if (d.dia && d.dia.length) dash.append(dayLine(d.dia));  // 10.9: línea del día
    else if (c.ahora || c.siguiente) {
      const k = card("Clase");
      if (c.ahora) {
        const r = mk("div", "drow now"); r.append(mk("b", "", c.ahora), mk("span", "dmeta", `faltan ${c.falta} min · hasta ${c.hasta}`)); k.append(r);
        if (c.progreso != null) { const bar = mk("div", "dbar cls"); const i = mk("i"); i.style.width = `${Math.round(c.progreso * 100)}%`; bar.append(i); k.append(bar); }
      }
      if (c.siguiente) { const r = mk("div", "drow"); r.append(mk("span", "", (c.ahora ? "Luego: " : "Siguiente: ") + c.siguiente),
        mk("span", "dmeta", c.en != null ? (c.en <= 0 ? "ahora" : `en ${c.en} min`) : (c.hoy ? c.a_las : `${c.a_las} · otro día`))); k.append(r); }
      dash.append(k);
    }
    if (!d.bandeja && d.aprobar && d.aprobar.length) {
      const k = card("Por aprobar", "warn");
      d.aprobar.forEach((a) => {
        const r = mk("div", "drow ap"); r.append(mk("span", "", a.t));
        const ok = mk("button", "mini ok", "Aprobar"), no = mk("button", "mini", "No");
        ok.type = no.type = "button";
        ok.addEventListener("click", () => socket.emit("approval_resolve", { id: a.id, ok: true }, refreshDash));
        no.addEventListener("click", () => socket.emit("approval_resolve", { id: a.id, ok: false }, refreshDash));
        const b = mk("span", "dbtns"); b.append(ok, no); r.append(b); k.append(r);
      });
      dash.append(k);
    }
    if (d.proyecto) {
      const p = d.proyecto, k = card(`Proyecto · ${p.hechos}/${p.total}`);
      k.append(mk("div", "drow", p.nombre));
      const bar = mk("div", "dbar"); const i = mk("i"); i.style.width = `${Math.round(100 * p.hechos / Math.max(1, p.total))}%`; bar.append(i); k.append(bar);
      const steps = mk("div", "dsteps");
      (p.pasos || []).forEach((s) => { const x = mk("i", { hecho: "done", "en marcha": "now", error: "bad", omitido: "bad" }[s.e] || ""); x.title = `${s.t} · ${s.e}`; steps.append(x); });
      k.append(steps); dash.append(k);
    }
    if (d.agenda && d.agenda.length) {
      const k = card("Agenda");
      d.agenda.forEach((e) => {
        const soon = e.en != null && e.en >= 0 && e.en <= 15;
        const r = mk("div", "drow" + (soon ? " soon" : ""));
        const when = e.en != null && e.en >= 0 && e.en < 120 ? `en ${e.en} min` : (e.hoy ? e.h : `${e.d.slice(8, 10)}/${e.d.slice(5, 7)} ${e.h}`);
        r.append(mk("span", "", e.t), mk("span", "dmeta", when)); k.append(r);
      });
      dash.append(k);
    }
    if (d.pendientes && d.pendientes.length) {
      const k = card(`Pendientes · ${d.n_pendientes}`);
      d.pendientes.forEach((p) => {
        const r = mk("label", "drow todo");
        const cb = mk("input"); cb.type = "checkbox"; cb.title = "Marcar como hecho";
        cb.addEventListener("change", () => { r.classList.add("done"); socket.emit("notes_done", { id: p.id, done: true }, () => setTimeout(refreshDash, 500)); });
        r.append(cb, mk("span", "", p.t)); k.append(r);
      });
      dash.append(k);
    }
    if (d.correos) {
      const k = card(`Correos importantes · ${d.correos.n}`);
      k.append(mk("div", "drow", d.correos.de.join(", ")));
      k.classList.add("click"); k.addEventListener("click", () => run("¿qué correos importantes tengo?"));
      dash.append(k);
    }
    favs = d.favoritos || favs;
    setUnread(d.avisos_sin_leer || 0);
    if (d.cursos && d.cursos.length) {                       // 9.2: cómo va cada curso
      const k = card("Cursos");
      d.cursos.forEach((c) => {
        const row = mk("div", "drow click course");
        const name = mk("b", "", c.curso), avg = mk("span", "dmeta", `${String(c.promedio).replace(".", ",")} · ${c.n} est.`);
        const bar = mk("div", "dist");
        [["Superior", "s"], ["Alto", "a"], ["Básico", "b"], ["Bajo", "x"]].forEach(([lbl, cls]) => {
          const v = c.dist[lbl] || 0; if (!v) return;
          const seg = mk("i", cls); seg.style.flex = String(v); seg.title = `${lbl}: ${v}`; bar.append(seg);
        });
        const top = mk("div", "course-top"); top.append(name, avg);
        row.append(top, bar);
        row.addEventListener("click", () => openMap(c.curso));                        // 10.9: mapa del curso
        k.append(row);
      });
      dash.append(k);
    }
    if (d.riesgo && d.riesgo.length) {
      const k = card("En riesgo", "bad");
      d.riesgo.forEach((r) => { const row = mk("div", "drow click"); row.append(mk("b", "", r.curso), mk("span", "dmeta", `${r.n}: ${r.nombres.join(", ")}${r.n > r.nombres.length ? "…" : ""}`));
        row.addEventListener("click", () => run(`¿quiénes están en riesgo en ${r.curso}?`)); k.append(row); });
      dash.append(k);
    }
    if (d.hice && d.hice.length) dash.append(doneCard(d.hice));   // 11.8: lo que hice hoy, con deshacer
    if (dash.children.length === 1) dash.append(mk("p", "dempty", "Nada urgente. Escribe tu horario en Ajustes › Memoria para ver aquí tus clases."));
    renderChips(d.sugerencias || []);
    pendingN = (d.bandeja || []).length;
    drawOrb(d.orbe);
    if (!hasMessages) drawWelcome();
  }
  /* ---------- 11.8: tarjeta del momento del día ---------- */
  function momentCard(mo) {
    const k = card(`Ahora · ${mo.titulo}`, "mom " + mo.id, "Momento");
    if (mo.id === "clase") {
      k.append(mk("div", "mom-big", mo.curso ? `Clase con ${mo.curso}` : "En clase"));
      k.append(mk("div", "mom-sub", [mo.tema, mo.falta != null ? `faltan ${mo.falta} min` : "", mo.hasta ? `hasta ${mo.hasta}` : ""].filter(Boolean).join(" · ")));
      if (mo.lista) k.append(rosterGrid(mo.lista, mo.tema));
    } else if (mo.siguiente) {
      k.append(mk("div", "mom-big", mo.siguiente));
      k.append(mk("div", "mom-sub", (mo.en <= 0 ? "ahora" : mo.en < 60 ? `en ${mo.en} min` : `a las ${mo.a_las}`) + (mo.quedan > 1 ? ` · ${mo.quedan} clases más hoy` : "")));
      const t = mk("div", "mom-tema"); t.append("Tema: "); t.append(mk("b", "", mo.tema || "sin planeación para esta semana")); k.append(t);
    } else if (mo.id === "noche") {
      if (!(mo.manana || []).length) k.append(mk("div", "mom-sub", "Mañana no tienes clases en el horario."));
      (mo.manana || []).forEach((c) => {
        const r = mk("div", "mom-row"), g = mk("div", "grow");
        g.append(mk("span", "", `${c.a_las} · ${c.t}`)); g.append(mk("small", "", c.tema ? "Tema: " + c.tema : "Sin tema planeado"));
        const b = mk("button", "mini", "Preparar"); b.type = "button"; b.addEventListener("click", () => run(c.cmd));
        r.append(g, b); k.append(r);
      });
    }
    const acts = mk("div", "mom-acts");
    (mo.acciones || []).forEach((a, i) => { const b = mk("button", "mini" + (i === 0 && mo.id !== "clase" ? " ok" : ""), a.t); b.type = "button"; b.addEventListener("click", () => run(a.cmd)); acts.append(b); });
    if (acts.children.length) k.append(acts);
    return k;
  }
  let rsMenu = null;
  function closeRs() { rsMenu?.remove(); rsMenu = null; }
  document.addEventListener("mousedown", (e) => { if (rsMenu && !e.target.closest(".rs-menu, .rs")) closeRs(); });
  function rosterGrid(r, tema) {
    const g = mk("div", "roster");
    const ausentes = r.estudiantes.filter((x) => x.falta).length;
    g.title = `${r.estudiantes.length} estudiantes${ausentes ? " · " + ausentes + " con falla hoy" : ""} · clic en un nombre para anotar`;
    r.estudiantes.forEach((x) => {
      const parts = x.n.split(/\s+/);
      const c = mk("div", "rs" + (x.falta ? " falta" : ""), parts.length > 1 ? `${parts[0]} ${parts[1][0]}.` : x.n);
      c.title = x.n + (x.falta ? " · falla hoy" : "") + (x.pos ? ` · ${x.pos} participación(es) hoy` : "");
      if (x.pos) c.append(mk("b", "", "+" + x.pos));
      c.addEventListener("click", (e) => {
        closeRs();
        const m = mk("div", "rs-menu"); rsMenu = m;
        m.append(mk("b", "", x.n));
        const send = (action, texto) => socket.emit("roster_act", { curso: r.clave || r.curso, est: x.n, action, texto: texto || "", tema: tema || "" }, (res) => {
          closeRs();
          setPreview(res && res.ok ? res.msg : (res && res.error) || "No se pudo.", "dim");
          if (res && res.ok) refreshDash();
        });
        const opt = (t, fn) => { const b = mk("button", "", t); b.type = "button"; b.addEventListener("click", fn); m.append(b); };
        opt("✓ Participó", () => send("positiva"));
        opt(x.falta ? "Presente (quitar falla)" : "✗ Falla", () => send(x.falta ? "presente" : "falla"));
        const f = mk("form"), inp = mk("input", "rv-in"); inp.placeholder = "Observación… (Enter)"; f.append(inp);
        f.addEventListener("submit", (ev) => { ev.preventDefault(); if (inp.value.trim()) send("obs", inp.value.trim()); });
        m.append(f);
        opt("Ver su ficha", () => { closeRs(); run(`ficha de ${x.n} de ${r.curso}`); });
        document.body.append(m);
        const rc = c.getBoundingClientRect();
        m.style.left = Math.min(rc.left, innerWidth - m.offsetWidth - 6) + "px";
        m.style.top = (rc.bottom + m.offsetHeight + 6 > innerHeight ? Math.max(4, rc.top - m.offsetHeight - 4) : rc.bottom + 4) + "px";
        e.stopPropagation();
      });
      g.append(c);
    });
    return g;
  }
  /* ---------- 11.8: bandeja única con atajos (S aprueba, N rechaza u oculta, ↑ ↓ para moverte) ---------- */
  let ibSel = 0;
  function inboxCard(items) {
    const k = card(items.length ? `Bandeja · ${items.length}` : "Bandeja", "inbox", "Bandeja");
    k.tabIndex = 0;
    if (!items.length) { k.append(mk("div", "dmeta", "Todo al día ✓")); return k; }
    ibSel = Math.min(ibSel, items.length - 1);
    items.forEach((x, i) => {
      const r = mk("div", "ib" + (x.tipo === "aprobar" ? " ap" : "") + (x.p === 1 ? " hot" : "") + (i === ibSel ? " sel" : ""));
      r.append(mk("span", "ik", x.tipo === "aprobar" ? "✓" : x.p === 1 ? "●" : "○"));
      const t = mk("span", "it", x.tipo === "aprobar" ? `Aprobar: ${x.t}` : x.t);
      t.addEventListener("click", () => ibDo(x, true));
      r.append(t);
      const bb = mk("span", "dbtns");
      if (x.tipo === "aprobar") {
        const ok = mk("button", "mini ok", "Sí"), no = mk("button", "mini", "No"); ok.type = no.type = "button";
        ok.addEventListener("click", () => ibDo(x, true)); no.addEventListener("click", () => ibDo(x, false)); bb.append(ok, no);
      } else {
        const hide = mk("button", "mini", "Ocultar"); hide.type = "button"; hide.title = "No mostrar hasta mañana";
        hide.addEventListener("click", () => ibDo(x, false)); bb.append(hide);
      }
      r.append(bb); k.append(r);
    });
    k.append(mk("div", "ib-help", "Atajos: Alt+B · S = sí / abrir · N = no / ocultar · ↑ ↓"));
    k.addEventListener("keydown", (e) => {
      const key = e.key.toLowerCase();
      if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); ibSel = Math.max(0, Math.min(items.length - 1, ibSel + (e.key === "ArrowDown" ? 1 : -1))); $$(".ib", k).forEach((r, i) => r.classList.toggle("sel", i === ibSel)); }
      else if (key === "s" || e.key === "Enter") { e.preventDefault(); ibDo(items[ibSel], true); }
      else if (key === "n" || e.key === "Delete") { e.preventDefault(); ibDo(items[ibSel], false); }
      else if (e.key === "Escape") { k.blur(); el.input.focus(); }
    });
    return k;
  }
  function ibDo(x, yes) {
    if (!x) return;
    const again = () => { refreshDash(); setTimeout(() => $(".dcard.inbox")?.focus(), 250); };
    if (x.tipo === "aprobar") socket.emit("approval_resolve", { id: x.id, ok: yes }, again);
    else if (yes) { if (x.cmd) (/\s$/.test(x.cmd) ? fill(x.cmd) : run(x.cmd)); }
    else socket.emit("inbox_snooze", { k: x.k }, again);
  }
  document.addEventListener("keydown", (e) => {
    if (e.altKey && !e.ctrlKey && e.key.toLowerCase() === "b") {
      e.preventDefault();
      if (body.dataset.size !== "expandido") setSize("expandido");
      if (body.classList.contains("wide")) { dashHidden = false; applyDashHidden(); } else $('.xtab[data-view="hoy"]').click();
      setTimeout(() => $(".dcard.inbox")?.focus(), 200);
    }
  });
  /* ---------- 11.8: lo que hice hoy, con deshacer ---------- */
  function hjRow(x, after) {
    const r = mk("div", "hj" + (x.deshecho ? " undone" : ""));
    r.append(mk("span", "hh", x.hora), mk("span", "ht", x.texto));
    if (x.puede && !x.deshecho) {
      const u = mk("button", "mini", "Deshacer"); u.type = "button";
      u.addEventListener("click", () => socket.emit("journal_undo", { id: x.id }, (res) => { setPreview(res ? res.msg : "No se pudo.", "dim"); refreshDash(); if (after) after(res); }));
      r.append(u);
    }
    return r;
  }
  function doneCard(items) {
    const k = card(`Lo que hice hoy · ${items.length}${items.length >= 6 ? "+" : ""}`, "", "Hice");
    items.forEach((x) => k.append(hjRow(x)));
    const all = mk("button", "text-btn", "Ver todo"); all.type = "button"; all.addEventListener("click", openJournal); k.append(all);
    return k;
  }
  let hjBox = null;
  function openJournal() {
    if (body.dataset.size !== "expandido") setSize("expandido");
    socket.emit("journal", {}, (r) => {
      hjBox?.remove();
      const box = mk("div", "hjall"); hjBox = box;
      const h = mk("h4", "", "Lo que hice hoy");
      const x = mk("button", "mini", "✕"); x.type = "button"; x.addEventListener("click", () => { box.remove(); hjBox = null; }); h.append(x);
      box.append(h);
      const items = (r && r.items) || [];
      if (!items.length) box.append(mk("p", "dempty", "Hoy todavía no he hecho nada por ti."));
      items.forEach((it) => box.append(hjRow(it, () => openJournal())));
      el.shell.append(box);
    });
  }
  socket.on("journal", () => { if (hjBox) openJournal(); });
  /* ---------- 11.8: el orbe informa (anillo con el tiempo de la clase y número de pendientes) ---------- */
  function drawOrb(o) {
    const ring = $("#orb-prog"), fg = $("#orb-prog-fg"), badge = $("#orb-badge");
    if (!ring) return;
    const C = 2 * Math.PI * 47;
    if (o && o.progreso != null) {
      ring.hidden = false; fg.style.strokeDasharray = String(C); fg.style.strokeDashoffset = String(C * (1 - o.progreso));
      ring.classList.toggle("end", o.falta != null && o.falta <= 5);
    } else ring.hidden = true;
    const n = (o && o.pendientes) || 0;
    badge.hidden = !n; badge.textContent = n > 9 ? "9+" : String(n);
    $("#orb").title = (o && o.clase ? `En clase · ${o.clase}${o.falta != null ? " · faltan " + o.falta + " min" : ""}\n` : "") +
      (n ? `${n} en la bandeja · ` : "") + "arrastra para mover · doble clic para cambiar de tamaño";
  }
  /* ---------- 11.8: lo que está en el proyector ---------- */
  const projPill = $("#proj-pill");
  socket.on("projecting", (d) => {
    const on = !!(d && d.on);
    projPill.hidden = !on; body.classList.toggle("projecting", on);
    if (on) $("#proj-t").textContent = "Proyectando: " + (d.title || (d.kind === "imagen" ? "imagen" : "respuesta"));
  });
  projPill.addEventListener("click", () => socket.emit("project_clear", {}));
  /* ---------- 12.5: qué IA responde (nube o la de tu equipo) ---------- */
  const aiChip = $("#ai-chip");
  function drawAiNow(a) {
    if (!a || !aiChip) return;
    aiChip.hidden = false;
    aiChip.dataset.donde = a.donde;
    $("#ai-chip-t").textContent = a.donde === "nube" ? `☁ ${a.proveedor}` : a.donde === "local" ? `⌂ Local · ${a.modelo}` : "✕ Sin IA";
    aiChip.title = (a.donde === "nube" ? `Responde la IA en la nube: ${a.proveedor}${a.modelo ? " · " + a.modelo : ""}.`
      : a.donde === "local" ? `Responde la IA de tu equipo: ${a.modelo}${a.sin_internet ? " (no hay internet)" : ""}.` : a.texto + ".")
      + (a.donde !== "local" ? (a.respaldo ? ` Si se cae el internet: ${a.respaldo}.` : " Si se cae el internet: no hay IA de respaldo (Ajustes › IA).") : "")
      + " Clic: Ajustes de IA.";
  }
  socket.on("ai_now", drawAiNow);
  socket.on("connect", () => socket.emit("ai_now", {}, drawAiNow));
  aiChip.addEventListener("click", () => socket.emit("open_settings"));
  /* ---------- 12.9: modo Docente / Asistente general ---------- */
  const modeChip = $("#mode-chip");
  function drawMode(m) {
    if (!m || !modeChip) return;
    modeChip.hidden = false;
    modeChip.dataset.mode = m.mode;
    $("#mode-chip-i").textContent = m.mode === "docente" ? "✎" : "◎";
    $("#mode-chip-t").textContent = (m.mode === "docente" ? "Docente" : "General") + (m.auto ? "" : " ·fijo");
    modeChip.title = `Modo ${m.label}${m.auto ? " (automático: docente en tu jornada o en el Wi-Fi del colegio)" : " (elegido por ti)"}. Clic: cambiar.`;
    document.body.dataset.amode = m.mode;
  }
  socket.on("assistant_mode", drawMode);
  socket.on("connect", () => socket.emit("assistant_mode", {}, drawMode));
  modeChip.addEventListener("click", () => socket.emit("assistant_mode", { set: "toggle" }, drawMode));

  /* ---------- 11.8: tamaño de la letra ---------- */
  function textSize(dir) {
    const order = ["normal", "grande", "proyector"];
    const i = order.indexOf(body.dataset.text || "normal");
    const next = dir == null ? order[(i + 1) % 3] : order[Math.max(0, Math.min(2, i + dir))];
    body.dataset.text = next;
    socket.emit("hud_text_size", { size: next });
    setPreview(`Letra: ${next === "normal" ? "normal" : next === "grande" ? "grande" : "para proyectar"}`, "dim");
  }
  $("#btn-text").addEventListener("click", () => textSize());
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && (e.key === "+" || e.key === "=" || e.key === "-")) { e.preventDefault(); textSize(e.key === "-" ? -1 : 1); }
  });
  /* las sugerencias: rueda del ratón para moverlas y sin cortes escondidos */
  chips.addEventListener("wheel", (e) => { if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) { chips.scrollLeft += e.deltaY; e.preventDefault(); } }, { passive: false });
  const chipsEnd = () => chips.classList.toggle("end", chips.scrollLeft + chips.clientWidth >= chips.scrollWidth - 4);
  chips.addEventListener("scroll", chipsEnd, { passive: true });

  function renderChips(list) {
    chips.innerHTML = "";
    list.forEach((s) => {
      const b = mk("button", "chip" + (s.kind === "aprobar" ? " hot" : s.kind === "fav" ? " fav" : ""), s.t); b.type = "button";
      if (s.kind === "fav") b.addEventListener("contextmenu", (e) => { e.preventDefault(); toggleFav(s.cmd); });
      b.title = s.fill ? "Completa la orden y pulsa Enter" : s.cmd;
      b.addEventListener("click", () => s.fill ? fill(s.cmd) : run(s.cmd));
      chips.append(b);
    });
    setTimeout(chipsEnd, 0);
  }
  function run(cmd) { socket.emit("manual_command", { command: cmd }); poke(); }
  function fill(cmd) {
    el.input.value = cmd;
    el.input.focus();
    const gap = cmd.indexOf("  ");
    const pos = gap >= 0 ? gap + 1 : cmd.length;
    el.input.setSelectionRange(pos, pos);
  }
  function refreshDash() { socket.emit("dashboard", {}, renderDash); }

  /* 9.0: franja «Trabajando…» con lo que Jarvis hace en segundo plano */
  const jobsBox = $("#jobs");
  let jobsData = [], jobsAt = Date.now();
  function renderJobs(list) {
    jobsData = list || []; jobsAt = Date.now();
    jobsBox.hidden = !jobsData.length;
    jobsBox.innerHTML = "";
    jobsData.forEach((j) => {
      const r = mk("div", "job");
      r.append(mk("span", "spin"), mk("span", "jt", j.t));
      if (j.s >= 0) { const s = mk("span", "js"); s.dataset.s = j.s; r.append(s); }
      jobsBox.append(r);
    });
    tickJobs();
    body.classList.toggle("working", jobsData.length > 0);
  }
  function tickJobs() {
    $$(".js", jobsBox).forEach((s) => { const v = Number(s.dataset.s) + Math.round((Date.now() - jobsAt) / 1000); s.textContent = v >= 60 ? `${Math.floor(v / 60)} min ${v % 60} s` : `${v} s`; });
  }
  setInterval(tickJobs, 1000);
  socket.on("jobs", ({ jobs }) => renderJobs(jobs));

  /* 9.0: ocultar o mostrar el panel «Hoy» (el chat ocupa todo el ancho) */
  const btnDash = $("#btn-dash");
  let dashHidden = false;
  try { dashHidden = localStorage.getItem("hud-dash-hidden") === "1"; } catch (e) { dashHidden = false; }
  function applyDashHidden() { body.classList.toggle("dash-hidden", dashHidden); btnDash.classList.toggle("off", dashHidden); btnDash.title = dashHidden ? "Mostrar el panel Hoy" : "Ocultar el panel Hoy"; }
  btnDash.addEventListener("click", () => { dashHidden = !dashHidden; try { localStorage.setItem("hud-dash-hidden", dashHidden ? "1" : "0"); } catch (e) { /* sin almacenamiento */ } applyDashHidden(); });
  applyDashHidden();

  /* 9.0: historial de órdenes con ↑ y ↓ en la barra */
  let hist = [], hpos = -1, draft = "";
  try { hist = JSON.parse(localStorage.getItem("hud-history") || "[]"); } catch (e) { hist = []; }
  function remember(cmd) {
    hist = [cmd, ...hist.filter((x) => x !== cmd)].slice(0, 60); hpos = -1;
    try { localStorage.setItem("hud-history", JSON.stringify(hist)); } catch (e) { /* sin almacenamiento */ }
  }
  el.input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowUp" && hist.length && (el.input.value === "" || hpos >= 0)) {
      e.preventDefault(); if (hpos < 0) draft = el.input.value; hpos = Math.min(hist.length - 1, hpos + 1); el.input.value = hist[hpos];
    } else if (e.key === "ArrowDown" && hpos >= 0) {
      e.preventDefault(); hpos -= 1; el.input.value = hpos >= 0 ? hist[hpos] : draft;
    }
  });

  /* 9.0: registro con filtro y búsqueda */
  const logQ = $("#log-q");
  let logFilter = "all";
  function applyLogFilter() {
    const q = plain(logQ.value);
    $$("div", el.log).forEach((d) => {
      const okType = logFilter === "all" || d.classList.contains(logFilter);
      d.hidden = !(okType && (!q || plain(d.textContent).includes(q)));
    });
  }
  $$(".lf").forEach((b) => b.addEventListener("click", () => { logFilter = b.dataset.f; $$(".lf").forEach((x) => x.classList.toggle("active", x === b)); applyLogFilter(); }));
  logQ.addEventListener("input", applyLogFilter);

  /* 9.0: arrastra una foto al HUD para revisar el trabajo de un estudiante */
  let dragDepth = 0;
  document.addEventListener("dragenter", (e) => { if ([...(e.dataTransfer?.types || [])].includes("Files")) { dragDepth++; body.classList.add("dropping"); } });
  document.addEventListener("dragleave", () => { dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) body.classList.remove("dropping"); });
  document.addEventListener("dragover", (e) => e.preventDefault());
  document.addEventListener("drop", (e) => {
    e.preventDefault(); dragDepth = 0; body.classList.remove("dropping");
    if (grading.open) {                                                          // 10.5: hojas de respuesta → a calificar
      const imgs = [...(e.dataTransfer?.files || [])].filter((x) => /^image\//.test(x.type));
      (async () => {
        for (const f of imgs) {
          const data = await new Promise((ok) => { const rd = new FileReader(); rd.onload = () => ok(rd.result); rd.readAsDataURL(f); });
          await new Promise((ok) => socket.emit("grade_upload", { data }, (r) => { setPreview(r && r.ok ? r.msg : `${f.name}: ${(r && r.msg) || "no se pudo"}`, r && r.ok ? "" : "dim"); ok(); }));
        }
      })();
      return;
    }
    sendFiles([...(e.dataTransfer?.files || [])]);                             // 11.6: cualquier archivo o imagen al chat
  });
  function reviewImage(dataUrl) {                                                // 9.0: revisar la foto como trabajo de un estudiante
    socket.emit("review_upload", { data: dataUrl }, (r) => {
      if (!r || !r.ok) { setPreview((r && r.error) || "No pude abrir la imagen.", "dim"); return; }
      if (body.dataset.size !== "expandido") setSize("expandido");
      addReviewCard(r.preview, 1);
    });
  }
  function reviewAttach(ids) {                                                   // 12.3: una foto, varias páginas o un PDF del chat
    socket.emit("review_from_attach", { ids }, (r) => {
      if (!r || !r.ok) { setPreview((r && r.error) || "No pude abrir el trabajo.", "dim"); return; }
      if (body.dataset.size !== "expandido") setSize("expandido");
      addReviewCard(r.preview, r.paginas, r);
    });
  }

  /* 11.6: subir archivos al chat (clip, arrastrar o pegar): leerlos, preguntarles y convertirlos */
  const OK_EXT = /\.(png|jpe?g|webp|gif|bmp|tiff?|pdf|docx|xlsx|xlsm|csv|tsv|pptx|txt|md|json|html?|xml)$/i;
  const readUrl = (f) => new Promise((ok, no) => { const rd = new FileReader(); rd.onload = () => ok(rd.result); rd.onerror = no; rd.readAsDataURL(f); });
  async function sendFiles(list) {
    const files = list.filter((f) => OK_EXT.test(f.name || "") || /^image\//.test(f.type)).slice(0, 10);
    const bad = list.length - files.length;
    if (!files.length) { setPreview("Ese tipo de archivo no lo puedo leer (imágenes, PDF, Word, Excel, CSV, PowerPoint o texto).", "dim"); return; }
    const big = files.filter((f) => f.size > 18 * 1024 * 1024);
    if (big.length) setPreview(`${big.map((f) => f.name).join(", ")}: muy grande (máximo 18 MB).`, "dim");
    const ids = [], urls = {}, errs = [];
    let last = null;
    setPreview(`Subiendo ${files.length > 1 ? files.length + " archivos" : files[0].name}…`, "dim");
    for (const f of files.filter((x) => x.size <= 18 * 1024 * 1024)) {
      const name = f.name && f.name !== "image.png" ? f.name : `imagen pegada ${new Date().toLocaleTimeString("es-CO").replace(/:/g, ".")}.png`;
      let data;
      try { data = await readUrl(f); } catch (_) { errs.push(name); continue; }
      const r = await new Promise((ok) => socket.emit("attach", { files: [{ name, data }] }, ok));
      if (r && r.ok) { ids.push(...r.ids); urls[r.ids[0]] = /^image\//.test(f.type) ? data : ""; last = r; }
      else errs.push(`${name}: ${(r && r.error) || "no se pudo"}`);
    }
    if (errs.length || bad) setPreview([...errs, bad ? `${bad} archivo(s) de un tipo que no leo` : ""].filter(Boolean).join(" · "), "dim");
    else if (ids.length) setPreview("Listo. Pregúntale algo o elige qué hacer con " + (ids.length > 1 ? "los archivos." : "el archivo."), "dim");
    if (!ids.length) return;
    const card = ids.length === 1 ? last : await new Promise((ok) => socket.emit("attach_card", { ids }, ok));
    if (card && card.ok) addAttachCard(card, urls);
  }
  el.clip = $("#btn-clip"); el.fileIn = $("#file-in");
  el.clip.addEventListener("click", () => el.fileIn.click());
  el.fileIn.addEventListener("change", () => { sendFiles([...el.fileIn.files]); el.fileIn.value = ""; });
  el.input.addEventListener("paste", (e) => {                                    // pegar una captura (Ctrl+V)
    const fs = [...(e.clipboardData?.files || [])];
    if (fs.length) { e.preventDefault(); sendFiles(fs); }
  });
  function addAttachCard(c, urls) {
    $(".empty", el.chat)?.remove();
    hasMessages = true;
    const m = mk("div", "msg user file");
    const b = mk("div", "msg-body fcard acard");
    if (c.preview) { const im = mk("img", "fthumb"); im.src = c.preview; im.alt = c.nombres[0]; b.append(im); }
    else { const ext = (c.nombres[0].split(".").pop() || "").toUpperCase().slice(0, 4); b.append(mk("div", "aico", c.nombres.length > 1 ? `×${c.nombres.length}` : ext)); }
    const info = mk("div", "finfo");
    info.append(mk("b", "", c.nombres.length > 1 ? `${c.nombres.length} archivos` : c.nombres[0]), mk("span", "dmeta", c.desc));
    const stat = mk("span", "astat");
    const act = (a, label, extra) => {
      if (a === "revisar") { reviewAttach(c.ids); return; }
      if (a === "editar") {                                                      // 11.7: editar la foto con la IA
        if (!extra) { q.dataset.mode = "editar"; qi.placeholder = "¿Qué le cambio? (ej.: ponle un fondo de tablero verde)"; qb.textContent = "Editar"; qi.focus(); return; }
        stat.textContent = "Editando la imagen…";
        socket.emit("studio_action", { attach: c.ids[0], action: "editar", texto: extra }, (r) => { if (r && !r.ok) stat.textContent = r.error || "No se pudo."; });
        return;
      }
      stat.textContent = `${label}…`;
      socket.emit("attach_action", { ids: c.ids, action: a, pregunta: extra || "" }, (r) => { if (r && !r.ok) stat.textContent = r.error || "No se pudo."; });
    };
    const btns = mk("div", "dbtns");
    (c.acciones || []).forEach((x) => {
      const bt = mk("button", "mini" + (x.a.startsWith("conv:") ? " conv" : x === c.acciones[0] ? " ok" : ""), x.t); bt.type = "button";
      bt.addEventListener("click", () => act(x.a, x.t.replace(/^→ /, "Convirtiendo a ")));
      btns.append(bt);
    });
    const q = mk("form", "aq"), qi = mk("input", "rv-in"), qb = mk("button", "mini ok", "Preguntar");
    qi.placeholder = c.nombres.length > 1 ? "Pregúntale algo a estos archivos…" : "Pregúntale algo a este archivo…"; qb.type = "submit";
    q.addEventListener("submit", (e) => { e.preventDefault(); const v = qi.value.trim(); if (!v) return; act(q.dataset.mode === "editar" ? "editar" : "pregunta", "Leyendo", v); qi.value = ""; });
    q.append(qi, qb);
    info.append(btns, q, stat); b.append(info);
    m.append(mk("div", "msg-meta", "TÚ · ARCHIVO" + (c.nombres.length > 1 ? "S" : "")), b);
    el.chat.appendChild(m);
    el.viewChat.scrollTop = el.viewChat.scrollHeight;
    $('.xtab[data-view="chat"]').click();
  }
  /* 12.3: tarjeta para revisar un trabajo: de quién (de la lista del curso), qué actividad, la clave y el resultado aquí mismo */
  let reviewCard = null;
  function addReviewCard(preview, pages, info0) {
    $(".empty", el.chat)?.remove();
    const m = mk("div", "msg jarvis file rvcard");
    const b = mk("div", "msg-body fcard");
    if (preview) { const im = mk("img", "fthumb"); im.src = preview; im.alt = "Trabajo para revisar"; b.append(im); }
    const info = mk("div", "finfo");
    info.append(mk("b", "", pages > 1 ? `Taller de ${pages} páginas listo para revisar` : "Trabajo listo para revisar"));
    const curso = mk("select", "rv-in");
    curso.append(new Option("Curso: el de ahora", ""));
    const who = mk("input", "rv-in"); who.placeholder = "¿De quién es? (escribe y escoge de la lista)";
    const dl = mk("datalist"); dl.id = "rv-dl-" + Date.now(); who.setAttribute("list", dl.id);
    const what = mk("input", "rv-in"); what.placeholder = "¿Qué actividad? (ej.: Taller 3 de fracciones)";
    const key = mk("textarea", "rv-in rv-key"); key.rows = 2;
    key.placeholder = "Respuestas correctas (opcional, mejora la nota): 1) 3/4  2) x = 5  3) b …";
    const subj = mk("select", "rv-in");                                          // 10.4: área o asignatura
    subj.append(new Option("Asignatura: automática", ""));
    socket.emit("subjects_info", {}, (r) => (r && r.choices || []).forEach((c) => subj.append(new Option(c, c))));
    let lists = {};
    const fillNames = () => {
      dl.textContent = "";
      (lists[curso.value || curso.dataset.activo] || []).forEach((n) => dl.append(new Option(n, n)));
    };
    const useInfo = (r) => {
      lists = (r && r.cursos) || {};
      Object.keys(lists).sort().forEach((c) => curso.append(new Option(c, c)));
      curso.dataset.activo = (r && r.activo) || "";
      if (curso.dataset.activo) curso.options[0].textContent = `Curso: ${curso.dataset.activo} (el de ahora)`;
      fillNames();
    };
    if (info0 && info0.cursos) useInfo(info0); else socket.emit("review_info", {}, useInfo);
    curso.addEventListener("change", fillNames);
    const res = mk("div", "rv-res");
    const go = mk("button", "mini ok", "Revisar"); go.type = "button";
    go.addEventListener("click", () => {
      const c = curso.value || curso.dataset.activo || "";
      const name = who.value.trim();
      if (name && c && (lists[c] || []).length && !(lists[c] || []).some((n) => n.toLowerCase() === name.toLowerCase())) {
        const near = (lists[c] || []).filter((n) => n.toLowerCase().includes(name.toLowerCase()));
        if (near.length === 1) who.value = near[0];
        else { res.textContent = near.length ? `¿Cuál? ${near.slice(0, 4).join(" · ")}` : `«${name}» no está en la lista de ${c}: escoge el nombre de la lista (o déjalo vacío).`; res.className = "rv-res err"; return; }
      }
      go.disabled = true; go.textContent = "Revisando…"; res.className = "rv-res"; res.textContent = pages > 1 ? `Leyendo las ${pages} páginas…` : "Leyendo el trabajo…";
      reviewCard = { go, res };
      socket.emit("review_run", { estudiante: who.value.trim(), que: what.value.trim(), clave: key.value.trim(), asignatura: subj.value, curso: c }, (r) => {
        if (r && !r.ok) { go.disabled = false; go.textContent = "Revisar"; res.textContent = r.error || "No pude revisarlo."; res.className = "rv-res err"; }
      });
    });
    info.append(curso, who, dl, what, key, subj, go, res); b.append(info);
    m.append(mk("div", "msg-meta", "JARVIS · REVISAR TRABAJO"), b);
    el.chat.appendChild(m);
    el.viewChat.scrollTop = el.viewChat.scrollHeight;
    $('.xtab[data-view="chat"]').click();
    who.focus();
  }
  socket.on("review_result", (d) => {                                            // 12.3: el resultado llega a la tarjeta
    const rc = reviewCard;
    if (!rc || !d) return;
    if (d.status === "working") return;
    rc.go.disabled = false; rc.go.textContent = "Revisar otra vez";
    rc.res.textContent = "";
    if (d.status === "error") { rc.res.className = "rv-res err"; rc.res.textContent = d.error || "No pude revisarlo."; return; }
    const r = d.result || {};
    rc.res.className = "rv-res ok";
    if (!r.legible) { rc.res.textContent = "No se lee bien: toma la foto más de cerca, derecha y con buena luz."; return; }
    if (r.nota != null) rc.res.append(mk("b", "rv-nota", `Nota sugerida: ${String(r.nota).replace(".", ",")}`));
    rc.res.append(mk("span", "", ` · ${(r.aciertos || []).length} aciertos · ${(r.errores || []).length} errores${d.estudiante ? " · " + d.estudiante : ""}`));
    (r.errores || []).slice(0, 4).forEach((e) => rc.res.append(mk("div", "rv-err", "✗ " + (typeof e === "string" ? e : [e.donde ? e.donde + ":" : "", e.que_esta_mal, e.correccion ? "→ " + e.correccion : ""].filter(Boolean).join(" ")))));
    if (d.estudiante && d.curso && r.nota != null) rc.res.append(mk("div", "dmeta", "La nota quedó en la bandeja para que la apruebes."));
    reviewCard = null;
  });

  /* 10.5: calificar hojas de respuesta (QR para el celular y avance en vivo) */
  const grading = { open: false, card: null };
  function renderGrading(d) {
    grading.open = !!(d && d.open);
    if (!d) return;
    if (!grading.card || !grading.card.isConnected) {
      $(".empty", el.chat)?.remove();
      grading.card = mk("div", "msg jarvis file");
      el.chat.appendChild(grading.card);
    }
    const m = grading.card; m.textContent = "";
    const b = mk("div", "msg-body fcard");
    if (d.url && d.open) { const im = mk("img", "fthumb qr"); im.src = `/calificar-qr.png?t=${Date.now()}`; im.alt = "Escanéame con tu celular"; b.append(im); }
    const info = mk("div", "finfo");
    info.append(mk("b", "", `${d.titulo} · ${String(d.curso || "").replace(" · ", ", ")}`),
      mk("span", "dmeta", d.open ? `${d.n}${d.esperados ? " de " + d.esperados : ""} hojas calificadas` + (d.url ? " · escanea el código con tu celular o arrastra fotos aquí" : " · arrastra las fotos aquí")
        : `Terminado: ${d.n} hojas`));
    (d.ultimos || []).slice().reverse().forEach((x) => info.append(mk("span", "dmeta", `${x.nombre}: ${String(Number(x.nota).toFixed(1)).replace(".", ",")}`)));
    if (d.open) {
      const btns = mk("div", "dbtns"), done = mk("button", "mini ok", "Terminé de calificar"); done.type = "button";
      done.addEventListener("click", () => run("terminé de calificar")); btns.append(done); info.append(btns);
    }
    b.append(info);
    m.append(mk("div", "msg-meta", "JARVIS · CALIFICAR HOJAS"), b);
    el.viewChat.scrollTop = el.viewChat.scrollHeight;
  }
  socket.on("grading", (d) => { renderGrading(d); poke(); });
  socket.on("connect", () => socket.emit("grading_state", {}, (r) => { grading.open = !!(r && r.open); }));

  /* 9.0: atajos de teclado */
  document.addEventListener("keydown", (e) => {
    if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
    const k = e.key.toLowerCase();
    const tabs = { "1": "chat", "2": "hoy", "3": "log" };
    if (tabs[k]) {
      e.preventDefault();
      if (k === "2" && body.classList.contains("wide")) { dashHidden = false; applyDashHidden(); return; }
      $(`.xtab[data-view="${tabs[k]}"]`)?.click();
    } else if (k === "l") { e.preventDefault(); el.input.focus(); el.input.select(); }
  });

  function addFileCard(c) {
    $(".empty", el.chat)?.remove();
    hasMessages = true;
    const m = mk("div", "msg jarvis file");
    const meta = mk("div", "msg-meta", "JARVIS · ARCHIVO");
    const b = mk("div", "msg-body fcard");
    let im = null;
    if (c.image && c.id >= 0) { im = mk("img", "fthumb"); im.src = `/archivo/${c.id}?t=${Date.now()}`; im.alt = c.name; b.append(im); }
    const info = mk("div", "finfo");
    info.append(mk("b", "", c.name), mk("span", "dmeta", `${c.kind} · ${c.folder}`));
    const btns = mk("div", "dbtns");
    const o = mk("button", "mini ok", "Abrir"), f = mk("button", "mini", "Carpeta");
    o.type = f.type = "button";
    o.addEventListener("click", () => socket.emit("file_open", { path: c.path }));
    f.addEventListener("click", () => socket.emit("file_open", { path: c.path, folder: true }));
    btns.append(o, f); info.append(btns); b.append(info);
    if (c.image) {                                                               // 11.8: la imagen al proyector con un clic
      const pj = mk("button", "mini", "▣ Proyectar"); pj.type = "button";
      pj.addEventListener("click", () => socket.emit("project_show", { path: c.path, title: c.estudio ? c.estudio.tema : c.name }, (r) => setPreview(r && r.ok ? "Listo, en el proyector." : (r && r.error) || "No se pudo.", "dim")));
      btns.append(pj);
    }
    if (c.estudio) {                                                             // 11.7: imagen creada por Jarvis → seguir trabajándola
      b.classList.add("studio");
      info.firstChild.textContent = c.estudio.tema || c.name;
      info.children[1].textContent = ["Imagen", c.estudio.estilo, c.estudio.formato].filter(Boolean).join(" · ");
      const sa = (action, texto) => socket.emit("studio_action", { path: c.path, action, texto: texto || "" }, (r) => { if (r && !r.ok) setPreview(r.error || "No se pudo.", "dim"); });
      const mkb = (t, fn) => { const x = mk("button", "mini", t); x.type = "button"; x.addEventListener("click", fn); btns.append(x); };
      mkb("Otra versión", () => sa("otra"));
      mkb(c.estudio.formato === "horizontal" ? "Vertical" : "Horizontal", () => sa("formato", c.estudio.formato === "horizontal" ? "vertical" : "horizontal"));
      mkb("Imprimir", () => sa("carta"));
      const ef = mk("form", "aq"), ei = mk("input", "rv-in"), eb = mk("button", "mini ok", "Cambiar");
      ei.placeholder = "Cámbiale algo… (ej.: fondo azul, quítale el texto)"; eb.type = "submit";
      ef.addEventListener("submit", (e) => { e.preventDefault(); const v = ei.value.trim(); if (!v) return; sa("editar", v); ei.value = ""; setPreview("Edito la imagen…", "dim"); });
      ef.append(ei, eb); info.append(ef);
      if (im) im.addEventListener("click", o.click.bind(o));
    }
    m.append(meta, b);
    const stick = nearBottom(el.viewChat);
    el.chat.appendChild(m);
    if (stick) el.viewChat.scrollTop = el.viewChat.scrollHeight;
  }

  /* 9.7: ficha del estudiante (notas con minigráfica, fallas, observador, alertas) */
  function sparkline(vals) {
    const NS = "http://www.w3.org/2000/svg", W = 520, H = 46, n = vals.length;
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("class", "spark");
    const y = (v) => H - 4 - ((v - 1) / 4) * (H - 8), x = (i) => n < 2 ? W / 2 : 4 + i * ((W - 8) / (n - 1));
    const base = document.createElementNS(NS, "line");
    base.setAttribute("x1", 0); base.setAttribute("x2", W); base.setAttribute("y1", y(3)); base.setAttribute("y2", y(3));
    base.setAttribute("class", "spark-base"); svg.append(base);
    const pl = document.createElementNS(NS, "polyline");
    pl.setAttribute("points", vals.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" "));
    pl.setAttribute("class", "spark-line"); svg.append(pl);
    vals.forEach((v, i) => {
      const c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", x(i)); c.setAttribute("cy", y(v)); c.setAttribute("r", 2.6);
      c.setAttribute("class", v < 3 ? "spark-dot low" : "spark-dot"); svg.append(c);
    });
    return svg;
  }
  function addStudentCard(c) {
    $(".empty", el.chat)?.remove();
    hasMessages = true;
    const m = mk("div", "msg jarvis student");
    const meta = mk("div", "msg-meta", `JARVIS · FICHA · ${c.curso}`);
    const b = mk("div", "msg-body scard");
    const head = mk("div", "shead");
    const avg = c.promedio == null ? "—" : String(c.promedio).replace(".", ",");
    head.append(mk("b", "", c.nombre), mk("span", "sbadge" + (c.riesgo ? " risk" : ""), `${avg}${c.desempeno ? " · " + c.desempeno : ""}`));
    b.append(head);
    if ((c.notas || []).length) {
      b.append(sparkline(c.notas.map((x) => x.n)));
      const last = c.notas.slice(-3).reverse().map((x) => `${x.a}: ${String(x.n).replace(".", ",")}`).join(" · ");
      b.append(mk("div", "dmeta", "Últimas: " + last));
    } else b.append(mk("div", "dmeta", "Sin notas registradas."));
    b.append(mk("div", "dmeta", `${c.fallas} falla${c.fallas === 1 ? "" : "s"}` + ((c.ultimas_fallas || []).length ? ` (última ${c.ultimas_fallas.slice(-1)[0]})` : "")));
    const y = c.anio || {};                                                     // 10.2: acumulado del año (VF) y lo que falta (VRA)
    if (y.vf != null) {
      const f = (x) => String(x).replace(".", ",");
      b.append(mk("div", y.pierde ? "salert" : "dmeta", y.aprobo ? `Año: lleva ${f(y.vf)}, ya aprobó ✓` :
        `Año: lleva ${f(y.vf)} · necesita ${f(y.vra)} en lo que queda` + (y.pierde ? " — puede perder el año" : "")));
    }
    (c.alertas || []).forEach((a) => b.append(mk("div", "salert", "⚠ " + a)));
    (c.observador || []).slice(-3).reverse().forEach((o) => b.append(mk("div", "sobs " + (o.t === "positiva" ? "pos" : ""), `${o.f} · ${o.x}`)));
    (c.compromisos || []).forEach((x) => b.append(mk("div", "dmeta", "Compromiso: " + x)));
    const btns = mk("div", "dbtns");
    [["Observador", `genera el observador de ${c.nombre} de ${c.curso}`], ["Informe padres", `haz el informe para los padres de ${c.nombre} de ${c.curso}`]].forEach(([l, cmd]) => {
      const bt = mk("button", "mini", l); bt.type = "button";
      bt.addEventListener("click", () => run(cmd));
      btns.append(bt);
    });
    b.append(btns);
    m.append(meta, b);
    const stick = nearBottom(el.viewChat);
    el.chat.appendChild(m);
    if (stick) el.viewChat.scrollTop = el.viewChat.scrollHeight;
  }

  /* Paleta de órdenes */
  const pal = { box: $("#pal"), q: $("#pal-q"), list: $("#pal-list"), items: [], sel: 0 };
  const plain = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  function openPal() {
    if (body.dataset.size !== "expandido") setSize("expandido");
    pal.box.hidden = false; body.classList.add("palopen"); pal.q.value = el.input.value || ""; pal.sel = 0;
    socket.emit("palette", {}, (r) => {
      pal.items = (r.smart || []).concat((r.recent || []).map((t) => ({ t, g: "Reciente" })), r.examples || []);   // 11.8: lo de ahora primero
      drawPal();
    });
    setTimeout(() => pal.q.focus(), 30);
  }
  function closePal() { pal.box.hidden = true; body.classList.remove("palopen"); el.input.focus(); }
  function palMatches() {
    const w = plain(pal.q.value).split(/\s+/).filter(Boolean);
    const seen = new Set();
    return pal.items.filter((x) => { const k = plain(x.t); if (seen.has(k)) return false; seen.add(k); const lab = plain(x.label || ""); return w.every((y) => k.includes(y) || lab.includes(y) || plain(x.g).includes(y)); }).slice(0, 40);
  }
  function drawPal() {
    const list = palMatches();
    pal.sel = Math.min(pal.sel, Math.max(0, list.length - 1));
    pal.list.innerHTML = "";
    if (pal.q.value.trim()) list.unshift({ t: pal.q.value.trim(), g: "Enviar tal cual" });
    list.forEach((x, i) => {
      const r = mk("div", "pal-item" + (i === pal.sel ? " sel" : ""));
      const star = mk("button", "pal-star" + (favs.includes(x.t.trim()) ? " on" : ""), favs.includes(x.t.trim()) ? "★" : "☆");
      star.type = "button"; star.title = "Favorito: aparece como botón en el HUD";
      star.addEventListener("mousedown", (e) => { e.preventDefault(); e.stopPropagation(); toggleFav(x.t.trim(), drawPal); });
      const pl = mk("span", "pl");
      const shown = x.label || x.t.replace(/\s{2,}/g, " … ").replace(/\s+$/, "");
      pl.append(shown);
      if (/\s{2}|\s$/.test(x.t) && !x.label) pl.append(mk("span", "gap", " …"));
      if (x.label && x.label !== x.t) pl.append(mk("small", "", x.t));
      r.append(pl, mk("span", "pal-g", x.g), star);
      r.addEventListener("mousedown", (e) => { e.preventDefault(); choose(x); });
      pal.list.append(r);
    });
    pal.shown = list;
  }
  function choose(x) {
    closePal();
    if (/\s{2}|\s$/.test(x.t) && x.g !== "Enviar tal cual") fill(x.t.replace(/\s+$/, " ")); else run(x.t);
  }
  pal.q.addEventListener("input", () => { pal.sel = 0; drawPal(); });
  pal.q.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); closePal(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); pal.sel = Math.min(pal.sel + 1, (pal.shown || []).length - 1); drawPal(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); pal.sel = Math.max(0, pal.sel - 1); drawPal(); }
    else if (e.key === "Enter") { e.preventDefault(); const x = (pal.shown || [])[pal.sel]; if (x) choose(x); }
  });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); pal.box.hidden ? openPal() : closePal(); }
  });
  $("#btn-pal").addEventListener("click", () => (pal.box.hidden ? openPal() : closePal()));

  /* Subtítulos: lo que dice Jarvis, palabra por palabra mientras habla */
  let subTimer = null, lastJarvis = "";
  function startSubs() {
    clearInterval(subTimer);
    const words = lastJarvis.split(/\s+/).filter(Boolean);
    if (words.length < 4 || !current.hud_subtitles) return;
    const wps = 2.6 * (1 + (Number(current.tts_rate) || 0) / 100);
    let i = 0;
    el.preview.classList.add("subs");
    subTimer = setInterval(() => {
      i = Math.min(words.length, i + 1);
      el.preview.textContent = "";
      const from = Math.max(0, i - 16);
      el.preview.append(words.slice(from, i - 1).join(" ") + " ");
      el.preview.append(mk("b", "", words[i - 1] || ""));
      if (i >= words.length) clearInterval(subTimer);
    }, 1000 / Math.max(1.2, wps));
  }
  function stopSubs() { clearInterval(subTimer); subTimer = null; if (el.preview.classList.contains("subs")) { el.preview.classList.remove("subs"); if (lastJarvis) setPreview(lastJarvis); } }

  socket.on("connect", () => { poke(); refreshDash(); placeDash(); placePreview(); });
  socket.on("dashboard", renderDash);
  socket.on("tutor", (d) => { tutorOn = !!(d && d.on); applyState({}); });
  socket.on("connect", () => socket.emit("tutor_state", {}, (d) => { tutorOn = !!(d && d.on); applyState({}); }));
  socket.on("file_card", (c) => { addFileCard(c); poke(); });
  /* 12.1: respuestas interactivas. Las fórmulas se leen con un analizador propio (igual que panel.py): nunca eval. */
  function panelEval(expr, env) {
    const toks = []; const rx = /\s*(?:(\d+(?:[.,]\d+)?)|([A-Za-z_]\w*)|(\*\*|[-+*/^(),]))/y; let pos = 0; const s = String(expr || "");
    while (pos < s.length) { if (/\s/.test(s[pos])) { pos++; continue; } rx.lastIndex = pos; const m = rx.exec(s); if (!m) throw new Error("símbolo");
      toks.push(m[1] ? ["n", parseFloat(m[1].replace(",", "."))] : m[2] ? ["v", m[2]] : ["o", m[3] === "**" ? "^" : m[3]]); pos = rx.lastIndex; }
    const F = { min: Math.min, max: Math.max, round: (x, n) => { const k = 10 ** (n || 0); return Math.round(x * k) / k; }, abs: Math.abs, sqrt: Math.sqrt };
    let i = 0; const peek = () => toks[i] || ["e", ""], is = (o) => peek()[0] === "o" && peek()[1] === o, take = () => toks[i++] || ["e", ""];
    function ex() { let v = te(); while (is("+") || is("-")) { const o = take()[1]; const r = te(); v = o === "+" ? v + r : v - r; } return v; }
    function te() { let v = po(); while (is("*") || is("/")) { const o = take()[1]; const r = po(); v = o === "*" ? v * r : (r ? v / r : Infinity); } return v; }
    function po() { const v = un(); if (is("^")) { take(); return v ** po(); } return v; }
    function un() { if (is("-")) { take(); return -un(); } if (is("+")) { take(); return un(); } return at(); }
    function at() { const [k, v] = take();
      if (k === "n") return v;
      if (k === "v") { if (is("(")) { if (!Object.prototype.hasOwnProperty.call(F, v)) throw new Error("función"); take(); const a = [ex()]; while (is(",")) { take(); a.push(ex()); } if (!is(")")) throw new Error(")"); take(); return F[v](...a); }
        if (!Object.prototype.hasOwnProperty.call(env, v)) throw new Error("variable"); return Number(env[v]); }
      if (k === "o" && v === "(") { const r = ex(); if (!is(")")) throw new Error(")"); take(); return r; }
      throw new Error("fórmula"); }
    const r = ex(); if (i !== toks.length) throw new Error("sobra"); return r;
  }
  function addPanelCard(p) {
    $(".empty", el.chat)?.remove();
    hasMessages = true;
    const m = mk("div", "msg jarvis panelcard");
    m.append(mk("div", "msg-meta", "JARVIS · PANEL"));
    const b = mk("div", "msg-body pcard");
    b.append(mk("b", "ptitle", p.titulo || "Panel"));
    const env = {}; (p.constantes || []).forEach((c) => (env[c.id] = c.valor));
    const fmt = (v, d) => (Number.isFinite(v) ? v.toLocaleString("es-CO", { minimumFractionDigits: d, maximumFractionDigits: d }) : "—");
    const outs = [];
    (p.controles || []).forEach((c) => {
      env[c.id] = c.valor;
      const row = mk("label", "prow"); const val = mk("output", "", fmt(c.valor, String(c.paso).includes(".") ? String(c.paso).split(".")[1].length : 0));
      const inp = document.createElement("input"); inp.type = "range"; inp.min = c.min; inp.max = c.max; inp.step = c.paso; inp.value = c.valor;
      inp.addEventListener("input", () => { env[c.id] = Number(inp.value); val.textContent = fmt(Number(inp.value), String(c.paso).includes(".") ? String(c.paso).split(".")[1].length : 0); recalc(); });
      row.append(mk("span", "", c.etiqueta), inp, val); b.append(row);
    });
    (p.resultados || []).forEach((r) => { const row = mk("div", "pres"); const v = mk("b", ""); row.append(mk("span", "", r.etiqueta), v); b.append(row); outs.push([r, v, row]); });
    function recalc() { outs.forEach(([r, v, row]) => { let x; try { x = panelEval(r.formula, env); } catch (e) { x = NaN; }
      v.textContent = fmt(x, r.decimales ?? 1); if (r.meta != null) { row.classList.toggle("ok", x >= r.meta); row.classList.toggle("bad", x < r.meta); } }); }
    recalc();
    if (p.tabla) {
      const t = mk("table", "ptab"); const hr = mk("tr"); let rows = p.tabla.filas.slice(), dir = 1;
      p.tabla.columnas.forEach((c, k) => { const th = mk("th", "", c); th.title = "Ordenar"; th.addEventListener("click", () => {
        const num = (x) => parseFloat(String(x).replace(/\./g, "").replace(",", "."));
        rows.sort((a, z) => { const A = num(a[k]), Z = num(z[k]); return (Number.isFinite(A) && Number.isFinite(Z) ? A - Z : String(a[k]).localeCompare(String(z[k]))) * dir; });
        dir = -dir; fill(); }); hr.append(th); });
      const body = mk("tbody"); t.append(mk("thead"), body); t.firstChild.append(hr);
      function fill() { body.textContent = ""; rows.forEach((r) => { const tr = mk("tr"); r.forEach((x) => tr.append(mk("td", "", x))); body.append(tr); }); }
      fill(); b.append(t);
    }
    if ((p.botones || []).length) { const bt = mk("div", "dbtns"); p.botones.forEach((x) => { const k = mk("button", "mini", x.texto); k.type = "button"; k.addEventListener("click", () => run(x.orden)); bt.append(k); }); b.append(bt); }
    m.append(b); el.chat.append(m); el.chat.scrollTop = el.chat.scrollHeight;
  }
  socket.on("panel", (p) => { addPanelCard(p); poke(); });
  socket.on("student_card", (c) => { addStudentCard(c); poke(); });
  /* 9.9: color del día del reactor y personalidad del momento */
  let persona = "";
  function setMood(d) {
    if (!d) return;
    const r = $("#reactor");
    if (d.mood) { if (d.mood === "tranquilo") delete r.dataset.mood; else r.dataset.mood = d.mood; }
    if (d.persona !== undefined) persona = d.persona;
    $("#orb").title = (d.label ? d.label.charAt(0).toUpperCase() + d.label.slice(1) + (d.why ? `: ${d.why}` : "") : "") +
      (persona ? ` · modo ${persona}` : "") + " · arrastra para mover · doble clic para cambiar de tamaño";
  }
  socket.on("day_mood", setMood);
  socket.on("persona", (d) => { persona = (d && d.label) || ""; });
  socket.on("connect", () => socket.emit("day_mood", {}, setMood));
  socket.on("disconnect", () => { setPreview("Sin enlace con el motor de Jarvis…", "dim"); led("#led-ai", "err"); });
  socket.on("bootstrap", (data) => {
    native = !!data.native;
    body.classList.toggle("browser", !native);
    if (!native) $("#btn-hide").hidden = true;
    if (native && data.size) { body.dataset.size = data.size; updateSizeButton(); placeDash(); placePreview(); }
    emptyChat();
    el.log.innerHTML = "";
    (data.logs || []).forEach(addLog);
    (data.chat || []).forEach((c) => addChat(c, false));
    dictating = !!data.dictation;
    body.classList.toggle("dictating", dictating);
    setTimers(data.timers || []);
    applySettings(data.settings);
    applyState(data.state || {});
    const last = (data.chat || []).slice(-1)[0];
    if (last) setPreview(last.role === "user" ? `› ${last.text}` : last.text, last.role === "user" ? "user" : "");
    el.viewChat.scrollTop = el.viewChat.scrollHeight;
  });
  socket.on("terminal_log", ({ data }) => addLog(data));
  socket.on("chat", (item) => { if (item.role !== "user") { lastJarvis = item.text; if (face) face.say(item.text, current.tts_rate); } addChat(item); poke(); });
  socket.on("state", (s) => { const was = st.mode; applyState(s); showTyping(st.mode === "thinking"); if (st.mode === "speaking" && was !== "speaking") startSubs(); else if (st.mode !== "speaking" && was === "speaking") stopSubs(); });
  socket.on("mic_level", ({ v }) => { if (st.mode !== "speaking") setLevel(v); });
  socket.on("heard", ({ text }) => { if (st.mode === "idle" || st.mode === "awaiting") setPreview(`«${text}»`, "dim"); });
  socket.on("settings_updated", applySettings);
  socket.on("hud_size", ({ size }) => { body.dataset.size = size; updateSizeButton(); placeDash(); placePreview(); poke(); });
  socket.on("timers", ({ timers }) => { setTimers(timers || []); });
  socket.on("card", (c) => showCard(c));
  socket.on("focus_input", () => setTimeout(() => { try { window.focus(); el.input.focus(); } catch (e) {} }, 200));
  socket.on("dictation", ({ on }) => {
    dictating = on;
    body.classList.toggle("dictating", on);
    applyState({});
    if (on) setPreview("Dictado activo · di «terminar dictado» para parar", "");
    poke();
  });

  /* ---------------- Controles ---------------- */
  function setSize(size) {
    if (native) socket.emit("hud_set_size", { size });
    else { body.dataset.size = size; updateSizeButton(); placeDash(); placePreview(); }
  }
  el.btnSize.addEventListener("click", () => setSize(body.dataset.size === "expandido" ? "compacto" : "expandido"));
  $("#btn-orb").addEventListener("click", () => setSize("orbe"));
  el.orb.addEventListener("dblclick", () => {
    const next = { orbe: "compacto", compacto: "expandido", expandido: "compacto" }[body.dataset.size];
    setSize(next);
  });
  $("#btn-hide").addEventListener("click", () => socket.emit("hud_hide"));
  // Salir con confirmación de dos clics (window.confirm no es fiable dentro de la ventana del HUD).
  let quitArmed = 0;
  const btnQuit = $("#btn-quit");
  btnQuit.addEventListener("click", () => {
    const now = Date.now();
    if (now - quitArmed < 4000) {        // segundo clic: salir de verdad
      quitArmed = 0;
      btnQuit.classList.remove("armed");
      setPreview("Cerrando Jarvis…", "");
      socket.emit("shutdown");
      setTimeout(() => { try { window.close(); } catch (e) {} }, 600);
      return;
    }
    quitArmed = now;                     // primer clic: pedir confirmación
    btnQuit.classList.add("armed");
    btnQuit.title = "Pulsa otra vez para salir";
    setPreview("¿Seguro? Pulsa salir otra vez para cerrar Jarvis.", "");
    setTimeout(() => { if (Date.now() - quitArmed >= 4000) { btnQuit.classList.remove("armed"); btnQuit.title = "Salir de Jarvis"; } }, 4200);
  });
  $("#btn-settings").addEventListener("click", () => {
    if (native) socket.emit("open_settings");
    else window.open("/ajustes", "_blank");
  });
  // 12.13.2: en la píldora (o mientras la ventana cambia de tamaño) el botón del micrófono quedaba justo
  // bajo el ratón y un clic lo pausaba sin querer. Ahora solo responde con el HUD abierto y quieto.
  let lastResize = 0, seenW = window.innerWidth, seenH = window.innerHeight;
  const sizeCheck = () => { if (window.innerWidth !== seenW || window.innerHeight !== seenH) { seenW = window.innerWidth; seenH = window.innerHeight; lastResize = Date.now(); } };
  window.addEventListener("resize", sizeCheck);
  el.btnMic.addEventListener("click", (e) => {
    sizeCheck();                                   // el aviso de «cambió el tamaño» puede llegar después del clic
    if (window.innerWidth < 200 || window.innerHeight < 80 || body.classList.contains("pill-mode") || Date.now() - lastResize < 900) {
      e.preventDefault(); return;
    }
    socket.emit("toggle_mic");
  });
  $("#btn-stop").addEventListener("click", () => socket.emit("stop_voice"));
  $("#btn-clear").addEventListener("click", () => socket.emit("clear_history", () => emptyChat()));

  el.bar.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = el.input.value.trim();
    if (!text) return;
    socket.emit("manual_command", { command: text });
    remember(text);
    el.input.value = "";
  });
  el.input.addEventListener("keydown", (e) => { if (e.key === "Escape") el.input.blur(); });

  $$(".xtab").forEach((tab) => tab.addEventListener("click", () => {
    $$(".xtab").forEach((t) => t.classList.toggle("active", t === tab));
    el.viewChat.hidden = tab.dataset.view !== "chat";
    el.viewLog.hidden = tab.dataset.view !== "log";
    viewHoy.hidden = tab.dataset.view !== "hoy";
    body.classList.toggle("logview", tab.dataset.view === "log");
    if (tab.dataset.view === "hoy") refreshDash();
    const v = tab.dataset.view === "chat" ? el.viewChat : el.viewLog;
    v.scrollTop = v.scrollHeight;
  }));

  /* ---------------- Mover el HUD arrastrando el reactor o el título ----------------
     Arrastre propio: la página solo informa de la posición del ratón y Jarvis mueve la
     ventana con la función nativa de Windows. (El arrastre de pywebview 6 falla en la
     ventana transparente: Windows rechaza moverla dentro del evento de ratón.)
     Solo empieza tras 4 px de movimiento, así el doble clic en el reactor sigue igual. */
  let drag = null, dragRaf = 0, dragLast = null, dragSeq = 0;
  const dragSend = (phase, e) => socket.emit("hud_drag", {
    phase, x: e.screenX, y: e.screenY, dpr: window.devicePixelRatio || 1, n: ++dragSeq });
  document.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || !native) return;
    const zone = e.target.closest(".drag-zone");
    if (!zone || e.target.closest("button, input, textarea, select, a")) return;
    drag = { id: e.pointerId, sx: e.screenX, sy: e.screenY, moving: false, el: zone };
  });
  document.addEventListener("pointermove", (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    if (!drag.moving) {
      if (Math.abs(e.screenX - drag.sx) + Math.abs(e.screenY - drag.sy) < 4) return;
      drag.moving = true;
      try { drag.el.setPointerCapture(e.pointerId); } catch (_) { /* sin captura: sigue igual */ }
      body.classList.add("dragging");
      dragSend("start", { screenX: drag.sx, screenY: drag.sy });
    }
    dragLast = e;
    if (!dragRaf) dragRaf = requestAnimationFrame(() => {
      dragRaf = 0;
      if (drag && dragLast) dragSend("move", dragLast);
    });
  });
  const dragEnd = (e) => {
    if (!drag) return;
    if (drag.moving) { dragSend("end", e); body.classList.remove("dragging"); }
    drag = null;
  };
  document.addEventListener("pointerup", dragEnd);
  document.addEventListener("pointercancel", dragEnd);
})();
