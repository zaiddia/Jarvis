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
    el.preview.textContent = text;
    void el.preview.offsetWidth;
    el.preview.classList.add("flash");
  }

  function setLevel(v) { el.reactor.style.setProperty("--lvl", v); }

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
    el.mode.textContent = (st.resting ? "· DESCANSANDO · " : st.viewing ? (st.viewing === "camara" ? "◉ VIENDO CÁMARA · " : "◉ VIENDO PANTALLA · ")
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

  function addChat(item, live = true) {
    $(".empty", el.chat)?.remove();
    hasMessages = true;
    const m = document.createElement("div");
    const isUser = item.role === "user";
    m.className = `msg ${isUser ? "user" : "jarvis"}${item.source === "PC" ? " pc" : ""}`;
    if (!live) m.style.animation = "none";
    const meta = document.createElement("div");
    meta.className = "msg-meta";
    meta.textContent = isUser ? (item.source === "voz" ? "TÚ · VOZ" : "TÚ") : "JARVIS";
    const t = document.createElement("span");
    t.className = "t";
    t.textContent = item.time || "";
    meta.append(t);
    const b = document.createElement("div");
    b.className = "msg-body";
    b.textContent = item.text;
    m.append(meta, b);
    const stick = nearBottom(el.viewChat);
    el.chat.appendChild(m);
    while (el.chat.children.length > 160) el.chat.firstChild.remove();
    if (stick || isUser) el.viewChat.scrollTop = el.viewChat.scrollHeight;
    if (live) setPreview(isUser ? `› ${item.text}` : item.text, isUser ? "user" : "");
  }

  function emptyChat() {
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
    el.log.appendChild(d);
    while (el.log.children.length > 400) el.log.firstChild.remove();
    if (stick) el.viewLog.scrollTop = el.viewLog.scrollHeight;
  }

  /* ---------------- Socket ---------------- */
  if (typeof io === "undefined") { setPreview("No se pudo cargar Socket.IO.", "dim"); return; }
  const socket = io();

  socket.on("connect", () => poke());
  socket.on("disconnect", () => { setPreview("Sin enlace con el motor de Jarvis…", "dim"); led("#led-ai", "err"); });
  socket.on("bootstrap", (data) => {
    native = !!data.native;
    body.classList.toggle("browser", !native);
    if (!native) $("#btn-hide").hidden = true;
    if (native && data.size) { body.dataset.size = data.size; updateSizeButton(); }
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
  socket.on("chat", (item) => { addChat(item); poke(); });
  socket.on("state", applyState);
  socket.on("mic_level", ({ v }) => { if (st.mode !== "speaking") setLevel(v); });
  socket.on("heard", ({ text }) => { if (st.mode === "idle" || st.mode === "awaiting") setPreview(`«${text}»`, "dim"); });
  socket.on("settings_updated", applySettings);
  socket.on("hud_size", ({ size }) => { body.dataset.size = size; updateSizeButton(); poke(); });
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
    else { body.dataset.size = size; updateSizeButton(); }
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
    el.input.value = "";
  });
  el.input.addEventListener("keydown", (e) => { if (e.key === "Escape") el.input.blur(); });

  $$(".xtab").forEach((tab) => tab.addEventListener("click", () => {
    $$(".xtab").forEach((t) => t.classList.toggle("active", t === tab));
    el.viewChat.hidden = tab.dataset.view !== "chat";
    el.viewLog.hidden = tab.dataset.view !== "log";
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
