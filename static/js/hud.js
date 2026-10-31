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
    if (st.mic !== "on") return "Micrófono en pausa · escribe una orden";
    if (!current.wake_word_enabled) return "Te escucho · habla o escribe una orden";
    const w = (current.wake_words || "jarvis").split(",")[0].trim();
    return `Di «${w.charAt(0).toUpperCase() + w.slice(1)}» o escribe una orden`;
  }

  function setPreview(text, cls = "") {
    el.preview.className = `preview ${cls}`;
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
  function poke() { lastActivity = Date.now(); body.classList.remove("dim"); }
  ["mousemove", "mousedown", "keydown", "wheel"].forEach((e) => document.addEventListener(e, poke, { passive: true }));
  setInterval(() => {
    const idle = st.mode === "idle" && document.activeElement !== el.input;
    body.classList.toggle("dim", !!current.hud_dim_idle && idle && Date.now() - lastActivity > 9000);
  }, 1000);

  /* ---------------- Estado ---------------- */
  function led(id, s) { $(id).dataset.s = s; }
  function applyState(s) {
    st = { ...st, ...s };
    body.dataset.state = st.mode || "idle";
    if (dictating) { el.mode.textContent = "✎ DICTANDO"; } else
    el.mode.textContent = (tutorOn ? "🎓 TUTOR · " : "") + (st.resting ? "· DESCANSANDO · " : st.viewing ? (st.viewing === "camara" ? "◉ VIENDO CÁMARA · " : "◉ VIENDO PANTALLA · ")
      : st.live && st.mode !== "speaking" ? "● EN VIVO · " : "") + (MODES[st.mode] || MODES.idle);
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

  function applySettings(s) {
    current = s || {};
    setTheme(current.theme);
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
    if (isUser) b.textContent = item.text; else b.innerHTML = md(item.text);
    m.append(meta, b);
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

  function emptyChat() {
    lastDay = "";
    el.chat.innerHTML = '<div class="empty">Canal abierto.<br>Prueba: «abre la calculadora», «volumen al 30», «busca recetas de arepas».</div>';
    hasMessages = false;
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
      if (n.kind === "aprobar") { row.classList.add("click"); row.addEventListener("click", () => { closeNotices(); if (body.classList.contains("wide")) { dashHidden = false; applyDashHidden(); } else $('.xtab[data-view="hoy"]').click(); }); }
      ntc.list.append(row);
    });
    setUnread(r ? r.unread : 0);
  }
  function openNotices() { if (body.dataset.size !== "expandido") setSize("expandido"); ntc.box.hidden = false; socket.emit("notices", { seen: true }, drawNotices); }
  function closeNotices() { ntc.box.hidden = true; }
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


  function renderDash(d) {
    if (!d) return;
    dash.innerHTML = "";
    const top = mk("div", "dtop");
    top.append(mk("span", "dclock", d.hora), mk("span", "ddate", d.fecha));
    if (d.clima) top.append(mk("span", "dweather", weatherIcon(d.clima) + "  " + d.clima));
    dash.append(top);
    renderJobs(d.trabajos || []);
    if (d.atencion && d.atencion.length) {                   // 9.3: lo que necesita tu atención
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
    if (c.ahora || c.siguiente) {
      const k = card("Clase");
      if (c.ahora) {
        const r = mk("div", "drow now"); r.append(mk("b", "", c.ahora), mk("span", "dmeta", `faltan ${c.falta} min · hasta ${c.hasta}`)); k.append(r);
        if (c.progreso != null) { const bar = mk("div", "dbar cls"); const i = mk("i"); i.style.width = `${Math.round(c.progreso * 100)}%`; bar.append(i); k.append(bar); }
      }
      if (c.siguiente) { const r = mk("div", "drow"); r.append(mk("span", "", (c.ahora ? "Luego: " : "Siguiente: ") + c.siguiente),
        mk("span", "dmeta", c.en != null ? (c.en <= 0 ? "ahora" : `en ${c.en} min`) : (c.hoy ? c.a_las : `${c.a_las} · otro día`))); k.append(r); }
      dash.append(k);
    }
    if (d.aprobar && d.aprobar.length) {
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
        row.addEventListener("click", () => run(`¿quiénes están en riesgo en ${c.curso}?`));
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
    if (dash.children.length === 1) dash.append(mk("p", "dempty", "Nada urgente. Escribe tu horario en Ajustes › Memoria para ver aquí tus clases."));
    renderChips(d.sugerencias || []);
  }
  function renderChips(list) {
    chips.innerHTML = "";
    list.forEach((s) => {
      const b = mk("button", "chip" + (s.kind === "aprobar" ? " hot" : s.kind === "fav" ? " fav" : ""), s.t); b.type = "button";
      if (s.kind === "fav") b.addEventListener("contextmenu", (e) => { e.preventDefault(); toggleFav(s.cmd); });
      b.title = s.fill ? "Completa la orden y pulsa Enter" : s.cmd;
      b.addEventListener("click", () => s.fill ? fill(s.cmd) : run(s.cmd));
      chips.append(b);
    });
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
    const f = [...(e.dataTransfer?.files || [])].find((x) => /^image\//.test(x.type));
    if (!f) { setPreview("Suelta una imagen (foto del trabajo) para revisarla.", "dim"); return; }
    if (f.size > 15 * 1024 * 1024) { setPreview("La imagen es muy grande (máximo 15 MB).", "dim"); return; }
    const rd = new FileReader();
    rd.onload = () => socket.emit("review_upload", { data: rd.result }, (r) => {
      if (!r || !r.ok) { setPreview((r && r.error) || "No pude abrir la imagen.", "dim"); return; }
      if (body.dataset.size !== "expandido") setSize("expandido");
      addReviewCard(r.preview);
    });
    rd.readAsDataURL(f);
  });
  function addReviewCard(preview) {
    $(".empty", el.chat)?.remove();
    const m = mk("div", "msg jarvis file");
    const b = mk("div", "msg-body fcard");
    if (preview) { const im = mk("img", "fthumb"); im.src = preview; im.alt = "Trabajo para revisar"; b.append(im); }
    const info = mk("div", "finfo");
    info.append(mk("b", "", "Trabajo listo para revisar"));
    const who = mk("input", "rv-in"); who.placeholder = "¿De quién es? (opcional)";
    const what = mk("input", "rv-in"); what.placeholder = "¿Qué actividad? (opcional)";
    const go = mk("button", "mini ok", "Revisar"); go.type = "button";
    go.addEventListener("click", () => {
      socket.emit("review_run", { estudiante: who.value.trim(), que: what.value.trim() }, (r) => {
        go.disabled = true; go.textContent = r && r.ok ? "Revisando…" : "Error";
        if (r && !r.ok) setPreview(r.error || "No pude revisarlo.", "dim");
      });
    });
    info.append(who, what, go); b.append(info);
    m.append(mk("div", "msg-meta", "JARVIS · REVISAR TRABAJO"), b);
    el.chat.appendChild(m);
    el.viewChat.scrollTop = el.viewChat.scrollHeight;
    $('.xtab[data-view="chat"]').click();
    who.focus();
  }

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
    if (c.image && c.id >= 0) { const im = mk("img", "fthumb"); im.src = `/archivo/${c.id}?t=${Date.now()}`; im.alt = c.name; b.append(im); }
    const info = mk("div", "finfo");
    info.append(mk("b", "", c.name), mk("span", "dmeta", `${c.kind} · ${c.folder}`));
    const btns = mk("div", "dbtns");
    const o = mk("button", "mini ok", "Abrir"), f = mk("button", "mini", "Carpeta");
    o.type = f.type = "button";
    o.addEventListener("click", () => socket.emit("file_open", { path: c.path }));
    f.addEventListener("click", () => socket.emit("file_open", { path: c.path, folder: true }));
    btns.append(o, f); info.append(btns); b.append(info);
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
    pal.box.hidden = false; pal.q.value = el.input.value || ""; pal.sel = 0;
    socket.emit("palette", {}, (r) => {
      pal.items = (r.recent || []).map((t) => ({ t, g: "Reciente" })).concat(r.examples || []);
      drawPal();
    });
    setTimeout(() => pal.q.focus(), 30);
  }
  function closePal() { pal.box.hidden = true; el.input.focus(); }
  function palMatches() {
    const w = plain(pal.q.value).split(/\s+/).filter(Boolean);
    const seen = new Set();
    return pal.items.filter((x) => { const k = plain(x.t); if (seen.has(k)) return false; seen.add(k); return w.every((y) => k.includes(y) || plain(x.g).includes(y)); }).slice(0, 40);
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
      r.append(mk("span", "", x.t), mk("span", "pal-g", x.g), star);
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
  socket.on("chat", (item) => { if (item.role !== "user") lastJarvis = item.text; addChat(item); poke(); });
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
  el.btnMic.addEventListener("click", () => socket.emit("toggle_mic"));
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
