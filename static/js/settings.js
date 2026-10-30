/* J.A.R.V.I.S. — ventana de ajustes */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const form = $("#form");

  let meta = null;
  let saved = {};
  let dirty = false;
  const clears = new Set();          // claves de API que se borrarán al guardar

  function toast(msg, kind = "info", ms = 3800) {
    const t = document.createElement("div");
    t.className = `toast ${kind}`;
    t.textContent = msg;
    $("#toasts").appendChild(t);
    setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 320); }, ms);
  }
  function setTheme(name) { document.documentElement.dataset.theme = name || "cyan"; }
  function setDirty(v) { dirty = v; $("#dirty").textContent = v ? "● Cambios sin guardar" : ""; }

  const fields = () => $$("[data-key]", form);

  function syncRange(input) {
    const out = input.parentElement.querySelector("output");
    if (!out) return;
    const v = Number(input.value);
    const unit = input.dataset.unit || "";
    if (input.dataset.signed) out.textContent = `${v > 0 ? "+" : ""}${v}${unit}`;
    else if (input.step && input.step.includes(".")) out.textContent = v.toFixed(1);
    else out.textContent = `${v}${unit}`;
  }
  function ensureOption(select, value, label) {
    if (![...select.options].some((o) => o.value === String(value))) select.add(new Option(label || String(value), value));
  }

  function fillVoices(list, selected) {
    const sel = $("#f-voice");
    sel.innerHTML = "";
    list.forEach(([id, label]) => sel.add(new Option(label, id)));
    ensureOption(sel, selected, selected);
    sel.value = selected;
  }
  function fillSwatches(themes, selected) {
    const colors = { cyan: "#2ee6ff", ambar: "#ffb547", rojo: "#ff4d5e", verde: "#3dff9a", violeta: "#b48cff" };
    const box = $("#swatches");
    box.innerHTML = "";
    themes.forEach(([id, label]) => {
      const lab = document.createElement("label");
      lab.className = "swatch";
      lab.innerHTML = `<input type="radio" name="theme" value="${id}" data-key="theme"><b></b><span></span>`;
      $("b", lab).style.background = `linear-gradient(135deg, ${colors[id] || "#888"}, #03060c 140%)`;
      $("span", lab).textContent = label;
      $("input", lab).checked = id === selected;
      box.appendChild(lab);
    });
  }
  function fillPositions(list) {
    const sel = $("#f-position");
    sel.innerHTML = "";
    list.forEach(([id, label]) => sel.add(new Option(label, id)));
  }
  function fillSkills(list) {
    const ul = $("#skills-list");
    ul.innerHTML = "";
    list.forEach((s) => {
      const li = document.createElement("li");
      const b = document.createElement("b");
      b.textContent = (s.dangerous ? "⚠ " : "") + s.name.replace(/_/g, " ");
      const sp = document.createElement("span");
      sp.textContent = s.desc;
      li.append(b, sp);
      ul.appendChild(li);
    });
  }

  function showProvider(p) {
    $$("[data-provider]").forEach((n) => { n.hidden = n.dataset.provider !== p; });
    $("#ai-status").textContent = "Sin comprobar.";
    $("#ai-status").className = "status";
    $("#models-list").innerHTML = "";
  }

  function populate(s) {
    fields().forEach((f) => {
      const k = f.dataset.key;
      if (!(k in s)) return;
      if (f.type === "checkbox") f.checked = !!s[k];
      else if (f.type === "radio") f.checked = f.value === s[k];
      else if (f.hasAttribute("data-secret")) f.value = "";
      else if (f.tagName === "SELECT") { ensureOption(f, s[k]); f.value = String(s[k]); }
      else f.value = s[k];
      if (f.type === "range") syncRange(f);
    });
    $$("[data-secret]").forEach((f) => {
      f.placeholder = s[`${f.dataset.key}_set`] ? "•••••••• guardada (escribe para cambiarla)" : (f.dataset.hint || "");
    });
    showProvider(s.ai_provider);
    showTtsBackend(s.tts_backend);
    showSttBackend(s.stt_backend);
    setTheme(s.theme);
    setDirty(false);
    clears.clear();
  }

  function showSttBackend(bk) {
    $$("[data-stt]").forEach((n) => { n.hidden = n.dataset.stt !== bk; });
    if (meta) {
      const rs = $("#refine-status");
      const m = meta.stt_refine_mode;
      rs.className = "status" + (m === "off" ? "" : " ok");
      rs.textContent = m === "gemini" ? "Ahora: Gemini transcribe las frases dirigidas a Jarvis."
        : m === "whisper" ? "Ahora: Whisper (en tu equipo) transcribe las frases dirigidas a Jarvis."
        : "Ahora: sin 2ª etapa. Para activarla, guarda tu clave de Gemini en la sección IA o instala Whisper.";
      const st = $("#whisper-status");
      st.className = "status" + (meta.whisper_installed ? " ok" : " err");
      st.textContent = meta.whisper_installed
        ? "Whisper listo. La primera vez descarga el modelo (necesita internet esa vez)."
        : "Whisper no está instalado. En instalar.bat se incluye; o: pip install faster-whisper.";
    }
  }

  function renderUpdate(u, msg, ok) {
    if (!u) return;
    const st = $("#update-status"), notes = $("#update-notes");
    const info = u.info;
    let text = `Tienes la versión ${u.version}.`;
    if (u.frozen) text += " Esta copia es el .exe compilado: para actualizar, actualiza la carpeta del código y vuelve a compilar.";
    else if (info && info.newer) text += ` Hay una nueva: la ${info.version}${info.date ? " (" + info.date + ")" : ""}.`;
    else if (info) text += " Es la última publicada.";
    else if (!u.repo) text += " Escribe arriba el repositorio y guarda para poder buscar versiones nuevas.";
    if (msg) text = msg;
    st.textContent = text;
    st.className = "status" + (ok === false ? " err" : (info && info.newer) || ok ? " ok" : "");
    notes.hidden = !(info && info.newer && info.notes);
    if (info && info.notes) notes.textContent = `Novedades de la ${info.version}:\n${info.notes}`;
    $("#btn-update-apply").hidden = !(info && info.newer) || u.frozen || u.busy;
    $("#btn-update-apply").textContent = info && info.newer ? `Actualizar a la ${info.version}` : "Actualizar ahora";
    const rb = $("#btn-update-rollback");
    rb.hidden = !u.backup;
    if (u.backup) rb.textContent = `Deshacer la última actualización (volver a la ${u.backup.from})`;
  }

  function showLiveProvider(p) {
    $$("[data-livep]").forEach((n) => { n.hidden = n.dataset.livep !== p; });
    const L = (meta && meta.live_info) || {};
    const st = $("#oa-live-status");
    if (st) {
      const k = L.keys && L.keys.openai;
      st.className = "status" + (k ? " ok" : " err");
      st.textContent = k ? "Usa tu clave de ChatGPT guardada en la sección IA." : "Falta la clave de ChatGPT: guárdala en la sección IA (proveedor ChatGPT).";
    }
  }

  function renderTelegram(msg, ok) {
    const T = (meta && meta.tg_info) || {};
    const st = $("#tg-status");
    if (!st) return;
    let text, cls = "";
    if (msg) { text = msg; cls = ok ? " ok" : " err"; }
    else if (!T.token) { text = "Pega el token del bot y guarda para empezar."; }
    else if (!T.remote) { text = "Activa «Controlar Jarvis desde el celular» para que obedezca tus mensajes."; }
    else if (T.ok) { text = "Conectado: escríbele a tu bot desde el celular."; cls = " ok"; }
    else if (T.error) { text = "Revisando la conexión… " + T.error; cls = " err"; }
    else { text = "Activado. Si no responde, pulsa Probar."; }
    st.textContent = text; st.className = "status" + cls;
  }

  function renderLive(msg, ok) {
    const L = (meta && meta.live_info) || {};
    const st = $("#live-status");
    let text, cls;
    if (msg) { text = msg; cls = ok ? " ok" : " err"; }
    else if (L.mode === "vivo") { text = "Ahora: conversación en vivo" + (L.model ? ` (${L.model}).` : "."); cls = " ok"; }
    else if (!L.key) { text = "Ahora: clásico. Para conversar en vivo guarda tu clave de Gemini en la sección IA."; cls = ""; }
    else if (!L.ws) { text = "Ahora: clásico. Falta un componente: actualiza Jarvis o ejecuta instalar.bat."; cls = " err"; }
    else { text = "Ahora: clásico" + (L.why ? ` (${L.why}).` : "."); cls = ""; }
    st.textContent = text; st.className = "status" + cls;
  }

  function renderOffline() {
    const o = (meta && meta.offline_info) || {};
    const st = $("#offline-status");
    st.className = "status" + (o.local_model ? " ok" : " err");
    st.textContent = (o.offline ? "Ahora mismo: SIN INTERNET. " : "")
      + (o.local_model ? `IA local lista: ${o.local_model}.`
        : "No encontré una IA local: instala Ollama (ollama.com) y un modelo. Sin ella, sin internet solo funcionan las órdenes del PC.")
      + (o.piper ? " Voz sin internet: lista." : " Voz sin internet: falta Piper (ejecuta descargar_voz.py).");
  }

  function showTtsBackend(bk) {
    $$("[data-ttsbk]").forEach((n) => { n.hidden = n.dataset.ttsbk !== bk; });
    if (meta) {
      const gs = $("#gemini-tts-status");
      gs.className = "status" + (meta.gemini_key_set ? " ok" : " err");
      gs.textContent = meta.gemini_key_set ? "Usa tu clave de Gemini guardada. Pulsa «Probar voz» para escucharla."
        : "Falta tu clave de Gemini: guárdala en la sección IA (elige Gemini como proveedor).";
      const st = $("#piper-status");
      if (meta.piper_installed) st.textContent = meta.piper_found ? `Voz lista: ${meta.piper_found}` : "Piper instalado, pero falta la voz. Ejecuta descargar_voz.py.";
      else st.textContent = "Piper no está instalado. En instalar.bat se incluye; o: pip install piper-tts.";
      st.className = "status" + (meta.piper_installed && meta.piper_found ? " ok" : meta.piper_installed ? " err" : " err");
    }
  }

  function collect() {
    const out = {};
    fields().forEach((f) => {
      const k = f.dataset.key;
      if (f.type === "radio") { if (f.checked) out[k] = f.value; return; }
      if (f.type === "checkbox") { out[k] = f.checked; return; }
      if (f.hasAttribute("data-secret")) { if (f.value.trim()) out[k] = f.value.trim(); return; }
      if (f.type === "range" || f.dataset.type === "number") { out[k] = Number(f.value); return; }
      out[k] = f.value;
    });
    clears.forEach((k) => { out[`${k}_clear`] = true; });
    return out;
  }

  function renderCaps() {
    const box = $("#caps");
    if (!box) return;
    box.innerHTML = "";
    (meta.capabilities || []).forEach(([cat, examples]) => {
      const card = document.createElement("div");
      card.className = "cap";
      const h = document.createElement("b");
      h.textContent = cat;
      const ul = document.createElement("ul");
      examples.forEach((ex) => {
        const li = document.createElement("li");
        li.textContent = "«" + ex + "»";
        ul.appendChild(li);
      });
      card.append(h, ul);
      box.appendChild(card);
    });
  }

  function renderAbout() {
    const rows = [
      ["Versión", meta.version],
      ["Ajustes", meta.config_path],
      ["Registro", meta.log_path],
      ["Modo", meta.portable ? "Portable (USB): todo se guarda en la memoria" : "Instalado en este equipo"],
      ["Archivo .env", meta.env_path ? `${meta.env_path} (${saved.env_keys.join(", ")})` : "No se usa"],
      ["Autoinicio", meta.autostart_supported ? "Disponible" : (meta.portable ? "Desactivado en modo USB" : "Solo en Windows")],
    ];
    const dl = $("#about");
    dl.innerHTML = "";
    rows.forEach(([k, v]) => {
      const dt = document.createElement("dt"); dt.textContent = k;
      const dd = document.createElement("dd"); dd.textContent = v;
      dl.append(dt, dd);
    });
  }

  /* ---------------- Socket ---------------- */
  const socket = io();
  socket.on("connect", () => {
    socket.emit("get_settings", (res) => {
      meta = res;
      saved = res.settings;
      fillSwatches(res.themes, res.settings.theme);
      fillVoices(res.voices, res.settings.tts_voice);
      fillPositions(res.positions);
      fillSkills(res.skills);
      const wm = $("#f-whisper-model");
      wm.innerHTML = "";
      (res.whisper_models || []).forEach(([id, desc]) => wm.add(new Option(`${id} — ${desc}`, id)));
      ensureOption(wm, res.settings.whisper_model);
      wm.value = res.settings.whisper_model;
      const ov = $("#f-oa-voice"), dv = $("#f-dg-voice"), LI = res.live_info || {};
      ov.innerHTML = ""; dv.innerHTML = "";
      (LI.openai_voices || []).forEach(([id, d]) => ov.add(new Option(`${id} — ${d}`, id)));
      (LI.deepgram_voices || []).forEach(([id, d]) => dv.add(new Option(d, id)));
      const gv = $("#f-gvoice"), gm = $("#f-gmodel");
      gv.innerHTML = ""; gm.innerHTML = "";
      (res.gemini_tts_voices || []).forEach(([id, desc]) => gv.add(new Option(`${id} — ${desc}`, id)));
      (res.gemini_tts_models || []).forEach(([id, desc]) => gm.add(new Option(desc, id)));
      populate(res.settings);
      $("#f-autostart").disabled = !res.autostart_supported;
      if (!res.autostart_supported) $("#autostart-help").textContent = res.portable
        ? "Desactivado en modo USB, para no modificar el equipo donde lo uses."
        : "Disponible solo en Windows.";
      $("#alarm-status").textContent = res.alarm_found ? `Se usará: ${res.alarm_found}` : "Sin sonido: solo se oirá la voz.";
      $("#apps-status").textContent = res.app_count
        ? `${res.app_count} aplicaciones del menú Inicio listas para abrir por voz.`
        : res.apps_ready ? "No se encontraron aplicaciones (solo funciona en Windows)." : "Buscando aplicaciones del menú Inicio…";
      renderAbout();
      renderCaps();
      renderOffline();
      renderUpdate(res.update);
      renderLive();
      showLiveProvider(res.settings.live_provider);
      renderTelegram();
      renderProfile(res.profile);
      if (meta && meta.email_info) { const e=$("#email-status"); if (e && !meta.email_info.sender_ok) { e.textContent="Pon tu correo y una contraseña de aplicación para enviar correos por voz."; e.className="status"; } }
      loadBackups();
      loadMics(res.settings.mic_device);
      loadModels(false);
    });
  });
  socket.on("disconnect", () => toast("Se perdió el enlace con Jarvis.", "err"));

  /* ---------------- Interacción ---------------- */
  $$(".tab").forEach((t) => t.addEventListener("click", () => {
    $$(".tab").forEach((x) => x.classList.toggle("active", x === t));
    $$(".pane").forEach((p) => p.classList.toggle("active", p.dataset.pane === t.dataset.tab));
    form.scrollTop = 0;
  }));

  form.addEventListener("input", (e) => {
    const f = e.target;
    if (f.type === "range") syncRange(f);
    if (f.dataset.key === "theme") setTheme(f.value);
    if (f.dataset.key === "ai_provider") { showProvider(f.value); loadModels(false); }
    if (f.dataset.key === "tts_backend") showTtsBackend(f.value);
    if (f.dataset.key === "live_provider") showLiveProvider(f.value);
    if (f.dataset.key === "stt_backend") showSttBackend(f.value);
    if (f.dataset.key) setDirty(true);
  });
  form.addEventListener("change", (e) => { if (e.target.dataset.key) setDirty(true); });

  $("#btn-save").addEventListener("click", () => {
    const btn = $("#btn-save");
    btn.disabled = true;
    socket.emit("save_settings", collect(), (res) => {
      btn.disabled = false;
      saved = res.settings;
      if (res.ok) { toast("Ajustes guardados.", "ok"); setDirty(false); }
      setTimeout(() => { socket.emit("mobile_info", {}, renderMobile); socket.emit("mcp_info", {}, renderMcp); }, 800);
      if (meta && meta.update) { meta.update.repo = saved.update_repo; renderUpdate(meta.update); }
      else { toast(`Algunos ajustes no se guardaron: ${res.errors.join(" · ")}`, "err", 7000); populate(res.settings); }
    });
  });

  function closeWindow() {
    if (dirty && !confirm("Hay cambios sin guardar. ¿Cerrar de todos modos?")) return;
    setTheme(saved.theme);
    socket.emit("close_settings");
    setTimeout(() => window.close(), 150);
  }
  $("#btn-close").addEventListener("click", closeWindow);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeWindow(); });

  let quitArmed2 = 0;
  $("#btn-quit").addEventListener("click", (e) => {
    const btn = e.currentTarget;
    if (Date.now() - quitArmed2 < 4000) { socket.emit("shutdown"); setTimeout(() => { try { window.close(); } catch (x) {} }, 600); return; }
    quitArmed2 = Date.now();
    btn.textContent = "Pulsa otra vez para salir";
    toast("¿Seguro? Pulsa «Salir» otra vez para cerrar Jarvis.", "err", 4000);
    setTimeout(() => { if (Date.now() - quitArmed2 >= 4000) { btn.innerHTML = '<svg class="i"><use href="#i-power"/></svg>Salir'; } }, 4200);
  });

  /* Voz */
  $("#btn-load-voices").addEventListener("click", () => {
    const btn = $("#btn-load-voices");
    btn.disabled = true;
    socket.emit("list_voices", (res) => {
      btn.disabled = false;
      fillVoices(res.voices, $("#f-voice").value);
      toast(res.ok ? `${res.voices.length} voces en español disponibles.` : res.error, res.ok ? "ok" : "err");
    });
  });
  $("#btn-preview").addEventListener("click", () => {
    socket.emit("preview_voice", {
      backend: $("[name=tts_backend]:checked")?.value,
      voice: $("#f-voice").value,
      tts_rate: Number($("#f-rate").value),
      tts_volume: Number($("#f-volume").value),
      tts_pitch: Number($("#f-pitch").value),
      gemini_tts_voice: $("#f-gvoice").value,
      gemini_tts_model: $("#f-gmodel").value,
      gemini_tts_style: $("#f-gstyle").value,
    }, (res) => { if (!res.ok) toast(res.error, "err"); });
  });

  /* Conversación en vivo */
  $("#btn-tg-test") && $("#btn-tg-test").addEventListener("click", () => {
    const btn = $("#btn-tg-test");
    btn.disabled = true;
    renderTelegram("Probando el bot…", true);
    socket.emit("telegram_test", (res) => { btn.disabled = false; renderTelegram(res.msg, res.ok); });
  });
  $("#btn-quake-test") && $("#btn-quake-test").addEventListener("click", () => {
    const st = $("#quake-status"); st.textContent = "Comprobando…"; st.className = "status";
    socket.emit("quake_test", (res) => { st.textContent = res.msg; st.className = "status" + (res.ok ? " ok" : " err"); });
  });
  $("#btn-email-test") && $("#btn-email-test").addEventListener("click", () => {
    const btn = $("#btn-email-test"), st = $("#email-status");
    btn.disabled = true; st.textContent = "Probando la conexión…"; st.className = "status";
    socket.emit("email_test", (res) => { btn.disabled = false; st.textContent = res.msg; st.className = "status" + (res.ok ? " ok" : " err"); });
  });
  $("#btn-weather-test") && $("#btn-weather-test").addEventListener("click", () => {
    const btn = $("#btn-weather-test"), st = $("#weather-status");
    btn.disabled = true;
    st.textContent = "Consultando el clima…"; st.className = "status";
    socket.emit("weather_preview", { city: $("#f-weather-city").value }, (res) => {
      btn.disabled = false;
      st.textContent = res.msg; st.className = "status" + (res.ok ? " ok" : " err");
    });
  });
  $("#btn-live-test").addEventListener("click", () => {
    const btn = $("#btn-live-test");
    btn.disabled = true;
    renderLive("Conectando con Gemini Live…", true);
    socket.emit("live_test", (res) => { btn.disabled = false; renderLive(res.msg, res.ok); });
  });

  /* Copias de seguridad */
  const PART_NAMES = { ajustes: "Ajustes", notas: "Notas", aula: "Cursos y asistencia", rutinas: "Rutinas", memoria: "Memoria",
                       perfil: "Lo que sé de ti", habilidades: "Habilidades", diario: "Diario",
                       tareas: "Tareas programadas", aprendizaje: "Costumbres", historial: "Historial",
                       guias: "Habilidades de la comunidad", seguimiento: "Notas de estudiantes", banco: "Banco de preguntas" };
  function bakStatus(text, cls) { const st = $("#backup-status"); st.textContent = text || ""; st.className = "status" + (cls ? " " + cls : ""); }
  function fmtDate(iso) {
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString("es-CO", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
  }
  function renderBackups(res, openName) {
    const box = $("#backup-list");
    box.innerHTML = "";
    const items = (res && res.items) || [];
    if (!items.length) { box.innerHTML = '<p class="note">Aún no hay copias en esta carpeta.</p>'; return; }
    items.forEach((b) => {
      const row = document.createElement("div");
      row.className = "bak-row";
      const kind = { auto: "automática", antes: "antes de restaurar", manual: "" }[b.kind] || "";
      const what = b.parts.map((p) => PART_NAMES[p.part] + (p.count != null && p.part !== "memoria" ? ` (${p.count})` : "")).join(" · ");
      row.innerHTML = '<div class="bak-main"><b></b><span class="bak-tag"></span><small></small></div><button class="btn btn-ghost" type="button">Restaurar…</button>';
      row.querySelector("b").textContent = fmtDate(b.date);
      row.querySelector(".bak-tag").textContent = [kind, b.with_secrets ? "con claves" : "", b.computer ? `de ${b.computer}` : ""].filter(Boolean).join(" · ");
      row.querySelector("small").textContent = `${what} · v${b.version || "?"} · ${b.size_kb} KB`;
      row.querySelector("button").addEventListener("click", () => openRestore(row, b));
      box.append(row);
      if (openName && b.name === openName) openRestore(row, b);
    });
  }
  function openRestore(row, b) {
    $$(".bak-restore").forEach((n) => n.remove());
    const panel = document.createElement("div");
    panel.className = "bak-restore";
    panel.innerHTML = '<p>¿Qué quieres recuperar de esta copia? Lo que elijas <b>reemplaza</b> lo que tienes ahora (antes se guarda una copia de cómo está todo, por si te arrepientes).</p><div class="bak-parts"></div><div class="row wrap"><button class="btn btn-primary" type="button">Restaurar lo elegido</button><button class="btn btn-ghost" type="button">Cancelar</button></div>';
    const parts = panel.querySelector(".bak-parts");
    b.parts.forEach((p) => {
      const l = document.createElement("label");
      l.innerHTML = '<input type="checkbox" checked> <span></span>';
      l.querySelector("input").value = p.part;
      l.querySelector("span").textContent = p.desc + (p.count != null && p.part !== "memoria" ? ` (${p.count})` : "");
      parts.append(l);
    });
    const [go, cancel] = panel.querySelectorAll("button");
    cancel.addEventListener("click", () => panel.remove());
    go.addEventListener("click", () => {
      const sel = [...parts.querySelectorAll("input:checked")].map((i) => i.value);
      if (!sel.length) { toast("Elige al menos una parte.", "err"); return; }
      go.disabled = true;
      bakStatus("Restaurando…");
      socket.emit("backup_restore", { name: b.name, parts: sel }, (res) => {
        go.disabled = false;
        if (!res.ok) { bakStatus(res.error, "err"); toast(res.error, "err", 7000); return; }
        let msg = `Listo: restauré ${res.parts.map((p) => PART_NAMES[p].toLowerCase()).join(", ")}.`;
        if (res.secrets_missing) msg += " La copia no traía claves de API: si te faltan, pégalas en la sección IA.";
        if (res.skipped && res.skipped.length) msg += " Dejé como estaban el micrófono y las carpetas de este equipo.";
        bakStatus(msg, "ok");
        toast("Copia restaurada.", "ok");
        renderBackups(res);
        socket.emit("get_settings", (r) => { meta = r; saved = r.settings; populate(r.settings); renderUpdate(r.update); renderOffline(); });
      });
    });
    row.after(panel);
  }
  function loadBackups() { socket.emit("backup_list", (res) => renderBackups(res)); }
  $("#btn-backup-now").addEventListener("click", () => {
    if (dirty) { toast("Guarda primero los cambios para que entren en la copia.", "err"); return; }
    const btn = $("#btn-backup-now");
    btn.disabled = true;
    socket.emit("backup_create", (res) => {
      btn.disabled = false;
      if (!res.ok) { bakStatus(res.error, "err"); return; }
      bakStatus(`Copia guardada: ${res.summary}.` + (res.with_secrets ? " Incluye tus claves: no la compartas." : ""), "ok");
      renderBackups(res);
    });
  });
  $("#btn-backup-folder").addEventListener("click", () => socket.emit("backup_open_folder"));
  $("#f-backup-file").addEventListener("change", (e) => {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    if (f.size > 20 * 1024 * 1024) { toast("Ese archivo es demasiado grande para ser una copia de Jarvis.", "err"); return; }
    const rd = new FileReader();
    rd.onload = () => {
      const b64 = String(rd.result).split(",")[1] || "";
      bakStatus("Revisando el archivo…");
      socket.emit("backup_import", { b64 }, (res) => {
        if (!res.ok) { bakStatus(res.error, "err"); return; }
        bakStatus(`Copia del ${fmtDate(res.info.date)}${res.info.computer ? " (equipo " + res.info.computer + ")" : ""} lista: elige qué restaurar.`, "ok");
        renderBackups(res, res.info.name);
      });
    };
    rd.readAsDataURL(f);
  });

  /* Actualizaciones */
  $("#btn-update-check").addEventListener("click", () => {
    if (dirty && $("#f-update-repo").value !== (saved.update_repo || "")) { toast("Guarda primero el repositorio.", "err"); return; }
    const btn = $("#btn-update-check");
    btn.disabled = true;
    $("#update-status").textContent = "Consultando GitHub…";
    socket.emit("update_check", (res) => {
      btn.disabled = false;
      renderUpdate(res.status, res.ok ? null : res.error, res.ok ? undefined : false);
    });
  });
  $("#btn-update-apply").addEventListener("click", () => {
    if (!confirm("Jarvis descargará la versión nueva, guardará una copia de seguridad y se reiniciará. ¿Seguir?")) return;
    $("#btn-update-apply").disabled = true;
    $("#btn-update-check").disabled = true;
    socket.emit("update_apply", (res) => { if (!res.ok) { toast(res.error, "err"); $("#btn-update-apply").disabled = false; $("#btn-update-check").disabled = false; } });
  });
  $("#btn-update-rollback").addEventListener("click", () => {
    if (!confirm("Se restaurarán los archivos de antes de la última actualización y Jarvis se reiniciará. ¿Seguir?")) return;
    socket.emit("update_rollback", (res) => {
      if (res.ok) { toast(`Volviendo a la versión ${res.version}. Jarvis se reinicia…`, "ok", 6000); }
      else toast(res.error, "err", 7000);
    });
  });
  socket.on("update_progress", (p) => {
    const bar = $("#update-bar"), st = $("#update-status");
    st.textContent = p.step;
    st.className = "status" + (p.ok === false ? " err" : p.done ? " ok" : "");
    bar.hidden = p.done || p.pct == null;
    if (p.pct != null) bar.firstElementChild.style.width = `${p.pct}%`;
    if (p.done) { $("#btn-update-check").disabled = false; $("#btn-update-apply").disabled = false; }
    if (p.done && p.ok !== false && /Reiniciando/.test(p.step)) toast(p.step, "ok", 8000);
  });

  /* Micrófono */
  function loadMics(selected) {
    socket.emit("list_mics", (res) => {
      const sel = $("#f-mic");
      const keep = selected ?? Number(sel.value);
      sel.innerHTML = "";
      sel.add(new Option("Predeterminado del sistema", "-1"));
      (res.devices || []).forEach((d) => sel.add(new Option(d.name, d.index)));
      ensureOption(sel, keep, `Dispositivo #${keep} (no encontrado)`);
      sel.value = String(keep);
    });
  }
  $("#btn-load-mics").addEventListener("click", () => loadMics());

  /* IA */
  function loadModels(explicit) {
    const provider = $("#f-provider").value || "ollama";
    const block = $(`[data-provider="${provider}"]`);
    const status = $("#ai-status");
    status.className = "status";
    status.textContent = explicit ? "Probando una respuesta real…" : "Conectando…";
    const payload = { ai_provider: provider, test: !!explicit };
    if (block) $$("[data-key]", block).forEach((f) => { payload[f.dataset.key] = f.value; });
    socket.emit("list_models", payload, (res) => {
      if (($("#f-provider").value || "ollama") !== provider) return;   // cambió mientras tanto
      const dl = $("#models-list");
      dl.innerHTML = "";
      (res.models || []).forEach((m) => dl.appendChild(new Option(m, m)));
      const input = block && $("[data-model]", block);
      if (!res.ok) {
        status.className = "status err";
        status.textContent = `✕ ${res.error}`;
        if (explicit) toast("No se pudo conectar con la IA.", "err");
        return;
      }
      const pick = res.suggest || (input && !input.value ? res.recommended : "");
      if (input && pick && input.value !== pick) { input.value = pick; setDirty(true); }
      const n = (res.models || []).length;
      const lista = n ? `${n} modelo(s) en tu cuenta` : "sin lista de modelos";
      if (explicit) {
        const ok = res.test_ok || !!res.suggest;
        status.className = "status " + (ok ? "ok" : "err");
        status.textContent = `${ok ? "✓" : "✕"} ${lista}; ${res.test_msg || ""}`
          + (ok && (pick || dirty) ? " ⚠ Pulsa «Guardar» para que Jarvis la use: probar no guarda." : "");
        toast(ok ? "La IA responde correctamente." : "La IA no responde: mira el motivo.", ok ? "ok" : "err");
      } else {
        status.className = "status ok";
        status.textContent = `✓ Conectado · ${lista}. Pulsa «Probar» para comprobar que responde.`;
      }
    });
  }
  $("#btn-test-ai").addEventListener("click", () => loadModels(true));
  $$("[data-clear]").forEach((b) => b.addEventListener("click", () => {
    const k = b.dataset.clear;
    clears.add(k);
    const f = $(`[data-key="${k}"]`);
    f.value = "";
    f.placeholder = "La clave se borrará al guardar";
    setDirty(true);
  }));
  $$("[data-open]").forEach((a) => a.addEventListener("click", (e) => {
    e.preventDefault();
    socket.emit("open_url", { url: a.dataset.open });
  }));
  /* Calendario */
  $("#btn-cal-test").addEventListener("click", () => {
    const st = $("#cal-status");
    st.className = "status";
    st.textContent = "Leyendo el calendario…";
    socket.emit("calendar_test", { calendar_urls: $("#f-cal").value }, (r) => {
      if (!r || !r.ok) {
        st.className = "status err";
        st.textContent = "✕ " + ((r && (r.error || (r.errors || []).join(" · "))) || "No se pudo leer.");
        return;
      }
      st.className = "status ok";
      st.textContent = `✓ ${r.count} eventos en el próximo mes · hoy: ${r.today}` +
        (r.next ? ` · lo próximo: ${r.next}` : "") +
        ((r.errors || []).length ? ` · avisos: ${r.errors.join(" · ")}` : "") +
        ($("#f-cal").value.trim() ? " · Pulsa «Guardar cambios»." : "");
    });
  });

  /* Prueba completa */
  let checkReport = "";
  function renderCheck(res) {
    const ul = $("#check-list");
    ul.innerHTML = "";
    if (!res || !res.items) return;
    let group = "";
    const marks = { ok: "✓", aviso: "!", fallo: "✗", info: "•" };
    res.items.forEach((it) => {
      if (it.grupo !== group) {
        group = it.grupo;
        const h = document.createElement("li"); h.className = "chk-group"; h.textContent = group; ul.appendChild(h);
      }
      const li = document.createElement("li");
      li.className = "chk-" + it.estado;
      const m = document.createElement("b"); m.textContent = marks[it.estado] || "•";
      const t = document.createElement("span"); t.textContent = it.texto;
      li.append(m, t);
      if (it.arreglo && /^ms-settings:/.test(it.arreglo)) {
        const b = document.createElement("button");
        b.type = "button"; b.className = "text-btn"; b.textContent = "Arreglar";
        b.addEventListener("click", () => socket.emit("open_fix", { url: it.arreglo }));
        li.appendChild(b);
      } else if (it.arreglo && it.arreglo.startsWith("ajustes:")) {
        const b = document.createElement("button");
        b.type = "button"; b.className = "text-btn"; b.textContent = "Ir al ajuste";
        const tab = { ia: "ia", integraciones: "integra" }[it.arreglo.split(":")[1]];
        b.addEventListener("click", () => { const el = document.querySelector(`.tab[data-tab="${tab}"]`); if (el) el.click(); });
        li.appendChild(b);
      } else if (it.arreglo === "actualizar") {
        const b = document.createElement("button");
        b.type = "button"; b.className = "text-btn"; b.textContent = "Buscar actualización";
        b.addEventListener("click", () => $("#btn-update-check").click());
        li.appendChild(b);
      }
      ul.appendChild(li);
    });
    const bad = res.items.filter((i) => i.estado === "fallo").length, warn = res.items.filter((i) => i.estado === "aviso").length;
    const st = $("#check-status");
    st.className = "status " + (bad ? "err" : "ok");
    st.textContent = (bad || warn ? `${bad} problema${bad === 1 ? "" : "s"} y ${warn} aviso${warn === 1 ? "" : "s"}` : "Todo en orden") + (res.at ? ` · ${res.at}` : "");
    checkReport = res.report || "";
    $("#btn-check-copy").hidden = !checkReport;
  }
  $("#btn-welcome").addEventListener("click", () => socket.emit("open_welcome"));
  $("#btn-check").addEventListener("click", () => {
    const btn = $("#btn-check");
    btn.disabled = true;
    $("#check-status").className = "status";
    $("#check-status").textContent = "Comprobando… (tarda unos segundos)";
    socket.emit("system_check", {}, (res) => { btn.disabled = false; renderCheck(res); });
  });
  $("#btn-check-copy").addEventListener("click", () => {
    navigator.clipboard.writeText(checkReport).then(() => toast("Informe copiado.", "ok"), () => toast("No pude copiarlo.", "err"));
  });
  socket.on("system_check", (res) => { if (res && res.items) renderCheck(Object.assign({ report: checkReport }, res)); });
  socket.on("rutinas_updated", (list) => renderRoutines(list));

  /* Rutinas */
  let rts = [], rtSel = null;
  function renderRoutines(list) {
    rts = list || rts;
    const ul = $("#rt-list");
    ul.innerHTML = "";
    if (!rts.length) ul.innerHTML = '<li class="empty">No hay rutinas. Crea una o recupera las de ejemplo.</li>';
    rts.forEach((r) => {
      const li = document.createElement("li");
      li.className = r.nombre === rtSel ? "sel" : "";
      const body = document.createElement("div");
      body.className = "r-body";
      const n = document.createElement("span"); n.className = "r-name"; n.textContent = r.nombre;
      const m = document.createElement("span"); m.className = "r-meta";
      m.textContent = `«${r.frases.slice(0, 3).join("», «")}» · ${r.pasos.length} pasos` + (r.cuando ? ` · ⏰ ${r.cuando}` : "");
      body.append(n, m);
      const play = document.createElement("button");
      play.type = "button"; play.className = "r-play"; play.title = "Ejecutar ahora";
      play.innerHTML = '<svg class="i"><use href="#i-play"/></svg>';
      play.addEventListener("click", (e) => { e.stopPropagation(); runRoutine(r.nombre); });
      li.append(body, play);
      li.addEventListener("click", () => editRoutine(r.nombre));
      ul.appendChild(li);
    });
  }
  function editRoutine(nombre) {
    rtSel = nombre;
    const r = rts.find((x) => x.nombre === nombre) || { nombre: "", frases: [], pasos: [], cuando: "" };
    $("#rt-editor").hidden = false;
    $("#rt-name").value = r.nombre;
    $("#rt-phrases").value = r.frases.filter((f) => f !== r.nombre).join(", ");
    $("#rt-steps").value = r.pasos.join("\n");
    $("#rt-when").value = r.cuando || "";
    $("#rt-del").hidden = !nombre;
    $("#rt-run").hidden = !nombre;
    $("#rt-status").textContent = "";
    renderRoutines();
    if (!nombre) $("#rt-name").focus();
  }
  function runRoutine(nombre) {
    socket.emit("rutinas_run", { nombre }, (r) => {
      toast(r && r.ok ? `Ejecutando «${nombre}»…` : (r && r.error) || "No se pudo.", r && r.ok ? "ok" : "err");
    });
  }
  $("#rt-new").addEventListener("click", () => editRoutine(""));
  $("#rt-defaults").addEventListener("click", () => socket.emit("rutinas_defaults", {}, (r) => { renderRoutines(r.rutinas); toast("Rutinas de ejemplo recuperadas.", "ok"); }));
  $("#rt-save").addEventListener("click", () => {
    const nombre = $("#rt-name").value.trim();
    socket.emit("rutinas_save", { nombre, frases: $("#rt-phrases").value, pasos: $("#rt-steps").value, cuando: $("#rt-when").value, old: rtSel || null }, (r) => {
      const st = $("#rt-status");
      if (!r || r.ok === false) { st.className = "status err"; st.textContent = (r && r.error) || "No se pudo guardar."; return; }
      rtSel = nombre;
      renderRoutines(r.rutinas);
      editRoutine(nombre);
      st.className = "status ok";
      const saved = (r.rutinas || []).find((x) => x.nombre === nombre);
      st.textContent = `Guardada. Di «Jarvis, ${nombre.toLowerCase()}» para lanzarla` + (saved && saved.cuando ? `; además se lanzará sola (${saved.cuando}).` : ".");
    });
  });
  $("#rt-run").addEventListener("click", () => { if (rtSel) runRoutine(rtSel); });
  $("#rt-del").addEventListener("click", (e) => {
    const b = e.currentTarget;
    if (!b.classList.contains("armed")) {
      b.classList.add("armed"); b.textContent = "¿Seguro? Pulsa otra vez";
      setTimeout(() => { b.classList.remove("armed"); b.textContent = "Eliminar"; }, 3500);
      return;
    }
    socket.emit("rutinas_delete", { nombre: rtSel }, (r) => { rtSel = null; $("#rt-editor").hidden = true; renderRoutines(r.rutinas); });
  });
  socket.on("connect", () => socket.emit("rutinas_get", {}, (r) => renderRoutines(r && r.rutinas)));

  /* Memoria: notas y pendientes */
  function renderProfile(list) {
    const ul = $("#profile-list");
    if (!ul) return;
    ul.innerHTML = "";
    if (!list || !list.length) {
      ul.innerHTML = '<li class="empty">Aún no ha aprendido nada. Cuéntale algo tuyo: «trabajo en el colegio San José».</li>';
      return;
    }
    list.forEach((f) => {
      const li = document.createElement("li");
      const body = document.createElement("div"); body.className = "n-body";
      const q = document.createElement("span"); q.className = "n-que"; q.textContent = f.texto;
      q.style.cursor = "text"; q.title = "Toca para corregir";
      q.addEventListener("click", () => {
        const nuevo = prompt("Corrige el dato:", f.texto);
        if (nuevo && nuevo.trim() && nuevo.trim() !== f.texto) socket.emit("profile_edit", { id: f.id, texto: nuevo.trim() }, (r) => renderProfile(r.facts));
      });
      body.appendChild(q);
      const del = document.createElement("button");
      del.type = "button"; del.className = "n-del"; del.title = "Olvidar";
      del.innerHTML = '<svg class="i"><use href="#i-trash"/></svg>';
      del.addEventListener("click", () => socket.emit("delete_fact", { id: f.id }, (r) => renderProfile(r.facts)));
      li.append(body, del);
      ul.appendChild(li);
    });
  }
  $("#btn-profile-clear") && $("#btn-profile-clear").addEventListener("click", () => {
    if (confirm("¿Borrar todo lo que Jarvis ha aprendido de ti?")) socket.emit("clear_profile", {}, (r) => renderProfile(r.facts));
  });
  socket.on("profile_updated", renderProfile);
  $("#btn-profile-add").addEventListener("click", () => {
    const t = $("#profile-new").value.trim();
    if (t) socket.emit("profile_edit", { texto: t }, (r) => { renderProfile(r.facts); $("#profile-new").value = ""; });
  });
  /* 7.8: historial, costumbres y Classroom */
  function histSearch() {
    const q = $("#hist-q").value.trim();
    if (!q) return;
    socket.emit("history_search", { q }, (r) => {
      const ul = $("#hist-results"); ul.innerHTML = "";
      if (!r.items.length) { ul.innerHTML = "<li><b>·</b><span>No encontré nada.</span></li>"; return; }
      r.items.forEach((it) => {
        const li = document.createElement("li");
        const b = document.createElement("b"); b.textContent = it.r === "u" ? "Tú" : "J";
        const s = document.createElement("span"); s.textContent = `${it.cuando}: ${it.x}`;
        const del = document.createElement("button"); del.type = "button"; del.className = "text-btn"; del.textContent = "Borrar";
        del.addEventListener("click", () => socket.emit("history_delete", { ts: it.ts, x: it.x }, () => li.remove()));
        li.append(b, s, del); ul.appendChild(li);
      });
    });
  }
  $("#btn-hist-search").addEventListener("click", histSearch);
  $("#hist-q").addEventListener("keydown", (e) => { if (e.key === "Enter") histSearch(); });
  function renderHabits(r) {
    if (r) $("#habits-status").textContent = `Me he fijado en ${r.acciones} órdenes; guardaste ${r.hechas} propuestas y rechazaste ${r.rechazadas}. Banco: ${r.banco} preguntas. Notas de estudiantes: ${r.seguimiento}.`;
  }
  $("#btn-habits-unreject").addEventListener("click", () => socket.emit("habits_info", { unreject: true }, (r) => { renderHabits(r); toast("Listo: puede volver a proponértelo.", "ok"); }));
  $("#btn-habits-forget").addEventListener("click", () => { if (confirm("¿Olvidar todas tus costumbres?")) socket.emit("habits_info", { forget: true }, renderHabits); });
  socket.on("connect", () => socket.emit("habits_info", {}, renderHabits));
  function renderCr(r) {
    const st = $("#cr-status");
    if (!r.connected) { st.className = "status"; st.textContent = "No conectado."; return; }
    st.className = "status " + (r.error ? "err" : "ok");
    st.textContent = r.error ? r.error : `Conectado · ${r.courses.length} clase(s): ${r.courses.slice(0, 6).join(", ")}`;
  }
  $("#btn-cr-connect").addEventListener("click", () => { $("#cr-status").textContent = "Se abrió Google en tu navegador: autoriza a Jarvis…"; socket.emit("classroom_connect", {}); });
  $("#btn-cr-disconnect").addEventListener("click", () => socket.emit("classroom_disconnect", {}, renderCr));
  socket.on("classroom_done", (d) => { toast(d.msg, "info", 6000); socket.emit("classroom_status", {}, renderCr); });
  socket.on("connect", () => socket.emit("classroom_status", {}, renderCr));

  function renderNotes(list) {
    const ul = $("#notes-list");
    ul.innerHTML = "";
    if (!list || !list.length) {
      ul.innerHTML = '<li class="empty">Aún no hay notas. Prueba a decir: «Jarvis, recuerda que…».</li>';
      return;
    }
    list.forEach((n) => {
      const li = document.createElement("li");
      li.className = n.hecho ? "done" : "";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = n.hecho;
      cb.title = n.hecho ? "Marcar como pendiente" : "Marcar como hecha";
      cb.addEventListener("change", () => socket.emit("notes_done", { id: n.id, done: cb.checked }, (r) => renderNotes(r.notes)));
      const body = document.createElement("div");
      body.className = "n-body";
      const q = document.createElement("span");
      q.className = "n-que";
      q.textContent = n.que;
      q.title = n.texto;
      body.appendChild(q);
      if (n.cuando) {
        const c = document.createElement("span");
        c.className = "n-cuando";
        c.textContent = n.cuando;
        body.appendChild(c);
      }
      const del = document.createElement("button");
      del.type = "button";
      del.className = "n-del";
      del.title = "Borrar";
      del.innerHTML = '<svg class="i"><use href="#i-trash"/></svg>';
      del.addEventListener("click", () => socket.emit("notes_delete", { id: n.id }, (r) => renderNotes(r.notes)));
      li.append(cb, body, del);
      ul.appendChild(li);
    });
  }
  function addNote() {
    const inp = $("#note-new");
    if (!inp.value.trim()) return;
    socket.emit("notes_add", { texto: inp.value }, (r) => {
      if (r && r.ok === false) { toast(r.error, "err"); return; }
      inp.value = "";
      renderNotes(r.notes);
    });
  }
  $("#btn-note-add").addEventListener("click", addNote);
  $("#note-new").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); addNote(); } });
  $("#btn-notes-clear").addEventListener("click", () => socket.emit("notes_clear_done", {}, (r) => renderNotes(r.notes)));
  socket.on("notes_updated", renderNotes);
  socket.on("connect", () => socket.emit("notes_get", {}, (r) => renderNotes(r && r.notes)));

  $("#btn-reset-prompt").addEventListener("click", () => { $("#f-prompt").value = meta?.default_system_prompt || ""; setDirty(true); });

  /* Control del PC */
  $("#btn-reindex").addEventListener("click", () => {
    const btn = $("#btn-reindex");
    btn.disabled = true;
    $("#apps-status").textContent = "Buscando aplicaciones…";
    socket.emit("reindex_apps", (res) => {
      btn.disabled = false;
      $("#apps-status").textContent = res.ok
        ? `${res.count} aplicaciones del menú Inicio listas para abrir por voz.`
        : `No se pudo actualizar: ${res.error}`;
    });
  });

  /* Alarma */
  $("#btn-test-alarm").addEventListener("click", () => {
    socket.emit("test_alarm", { path: $("#f-alarm").value }, (res) => {
      const st = $("#alarm-status");
      st.className = `status ${res.ok ? "ok" : "err"}`;
      st.textContent = res.ok ? `Sonando: ${res.path}` : res.error;
    });
  });

  /* Sistema */
  $("#btn-open-folder").addEventListener("click", () => {
    socket.emit("open_output", (res) => { if (!res.ok) toast(res.error, "info", 6000); });
  });

  /* 7.0: habilidades */
  function renderSkills(res) {
    const ul = $("#hb-list");
    ul.innerHTML = "";
    const list = (res && res.habilidades) || [];
    if (!list.length) ul.innerHTML = '<li class="empty">No hay habilidades instaladas.</li>';
    list.forEach((h) => {
      const li = document.createElement("li");
      const b = document.createElement("div"); b.className = "r-body";
      const n = document.createElement("span"); n.className = "r-name"; n.textContent = h.nombre;
      const m = document.createElement("span"); m.className = "r-meta";
      m.textContent = `«${h.frases[0]}» · ${h.accion}` + (h.autor ? ` · ${h.autor}` : "") + (h.descripcion ? ` — ${h.descripcion}` : "");
      b.append(n, m);
      const exp = document.createElement("button"); exp.type = "button"; exp.className = "text-btn"; exp.textContent = "Compartir";
      exp.addEventListener("click", () => socket.emit("habilidades_export", { nombre: h.nombre }, (r) => {
        const blob = new Blob([r.texto || ""], { type: "application/json" });
        const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = (h.archivo || h.nombre + ".json");
        document.body.appendChild(a); a.click(); a.remove();
      }));
      const del = document.createElement("button"); del.type = "button"; del.className = "text-btn"; del.textContent = "Quitar";
      del.addEventListener("click", () => { if (confirm(`¿Quitar la habilidad «${h.nombre}»?`)) socket.emit("habilidades_delete", { nombre: h.nombre }, renderSkills); });
      li.append(b, exp, del);
      ul.appendChild(li);
    });
    const st = $("#hb-status");
    st.className = "status" + (res && res.errores && res.errores.length ? " err" : "");
    st.textContent = res && res.errores && res.errores.length ? "No se pudieron leer: " + res.errores.join(" · ") : "";
  }
  $("#hb-file").addEventListener("change", (e) => {
    const f = e.target.files[0];
    if (!f) return;
    f.text().then((texto) => socket.emit("habilidades_install", { texto }, (r) => {
      renderSkills(r);
      const st = $("#hb-status");
      st.className = "status " + (r.ok ? "ok" : "err");
      st.textContent = r.ok ? `Instalada: «${r.nombre}».` : r.error;
    }));
    e.target.value = "";
  });
  $("#hb-folder").addEventListener("click", () => socket.emit("habilidades_folder"));

  /* 7.5: habilidades de la comunidad (SKILL.md) e investigaciones */
  const RISK = { bajo: ["ok", "Riesgo bajo"], medio: ["warn", "Riesgo medio"], alto: ["err", "Riesgo ALTO"] };
  function renderGuides(res) {
    const ul = $("#gd-list");
    ul.innerHTML = "";
    const list = (res && res.guias) || [];
    if (!list.length) ul.innerHTML = '<li class="empty">No hay habilidades de la comunidad.</li>';
    list.forEach((g) => {
      const li = document.createElement("li");
      const b = document.createElement("div"); b.className = "r-body";
      const n = document.createElement("span"); n.className = "r-name"; n.textContent = g.nombre;
      const m = document.createElement("span"); m.className = "r-meta";
      const rk = RISK[(g.revision || {}).nivel] || RISK.bajo;
      m.textContent = `${rk[1]} · ${g.descripcion}`;
      m.title = g.descripcion + (g.origen ? `\nOrigen: ${g.origen}` : "");
      b.append(n, m);
      const del = document.createElement("button"); del.type = "button"; del.className = "text-btn"; del.textContent = "Quitar";
      del.addEventListener("click", () => { if (confirm(`¿Quitar «${g.nombre}»?`)) socket.emit("guias_delete", { slug: g.slug }, renderGuides); });
      li.append(b, del);
      ul.appendChild(li);
    });
  }
  let gdCode = "";
  function showReview(r) {
    const st = $("#gd-status");
    if (!r.ok) { st.className = "status err"; st.textContent = r.error; $("#gd-review").hidden = true; return; }
    st.textContent = "";
    gdCode = r.code;
    const rv = r.revision || { nivel: "bajo", avisos: [] };
    const rk = RISK[rv.nivel] || RISK.bajo;
    $("#gd-review-head").innerHTML = "";
    const h = document.createElement("div");
    const nm = document.createElement("b"); nm.textContent = r.nombre;
    const lv = document.createElement("span"); lv.className = "status " + rk[0]; lv.textContent = "  " + rk[1] + (r.reemplaza ? " · reemplaza la que ya tienes" : "");
    const d = document.createElement("p"); d.className = "note"; d.textContent = r.descripcion;
    h.append(nm, lv, d);
    $("#gd-review-head").appendChild(h);
    const ul = $("#gd-review-list"); ul.innerHTML = "";
    (rv.avisos.length ? rv.avisos : ["El revisor no encontró nada raro."]).forEach((a) => {
      const li = document.createElement("li"); const i = document.createElement("b"); i.textContent = rv.avisos.length ? "!" : "✓";
      const s = document.createElement("span"); s.textContent = a; li.append(i, s); ul.appendChild(li);
    });
    $("#gd-install").disabled = rv.nivel === "alto";
    $("#gd-install").textContent = rv.nivel === "alto" ? "No se puede instalar" : (rv.nivel === "medio" ? "Instalar de todos modos" : "Instalar");
    $("#gd-review").hidden = false;
  }
  $("#gd-check").addEventListener("click", () => {
    const url = $("#gd-url").value.trim();
    if (!url) { toast("Pega el enlace de la habilidad.", "err"); return; }
    $("#gd-status").className = "status"; $("#gd-status").textContent = "Descargando y revisando…";
    socket.emit("guias_preview", { url }, showReview);
  });
  $("#gd-file").addEventListener("change", (e) => {
    const f = e.target.files[0];
    if (!f) return;
    const rd = new FileReader();
    rd.onload = () => socket.emit("guias_preview", { b64: rd.result, name: f.name }, showReview);
    rd.readAsDataURL(f);
    e.target.value = "";
  });
  $("#gd-install").addEventListener("click", () => socket.emit("guias_install", { code: gdCode }, (r) => {
    $("#gd-review").hidden = true;
    const st = $("#gd-status");
    st.className = "status " + (r.ok ? "ok" : "err");
    st.textContent = r.ok ? "Instalada. Jarvis la usará cuando lo que pidas encaje con ella." : r.error;
    if (r.ok) { renderGuides(r); $("#gd-url").value = ""; }
  }));
  $("#gd-cancel").addEventListener("click", () => { $("#gd-review").hidden = true; gdCode = ""; });
  $("#btn-research-folder").addEventListener("click", () => socket.emit("research_folder"));
  socket.on("connect", () => socket.emit("guias_list", {}, renderGuides));
  socket.on("connect", () => socket.emit("habilidades_get", {}, renderSkills));

  /* 7.0: conectores MCP */
  function renderMcp(info) {
    const ul = $("#mcp-status");
    ul.innerHTML = "";
    const st = (info && info.status) || info || [];
    if (!st.length) ul.innerHTML = '<li class="chk-info"><b>•</b><span>Ningún conector configurado.</span></li>';
    st.forEach((c) => {
      const li = document.createElement("li");
      li.className = c.ok ? "chk-ok" : "chk-fallo";
      const b = document.createElement("b"); b.textContent = c.ok ? "✓" : "✗";
      const t = document.createElement("span");
      t.textContent = c.ok ? `${c.nombre}: ${c.herramientas.length} herramientas (${c.herramientas.slice(0, 5).join(", ")}${c.herramientas.length > 5 ? "…" : ""})` : `${c.nombre}: ${c.error}`;
      li.append(b, t); ul.appendChild(li);
    });
    if (info && info.claude_config !== undefined) {
      $("#mcp-claude").textContent = info.claude_config;
      $("#mcp-claude-box").hidden = !info.server;
    }
  }
  $("#btn-mcp-reload").addEventListener("click", () => socket.emit("mcp_reload", {}, () => toast("Reconectando los conectores…", "info")));
  socket.on("mcp_status", renderMcp);
  socket.on("connect", () => socket.emit("mcp_info", {}, renderMcp));

  /* 7.0: panel del celular */
  function renderMobile(m) {
    $("#mobile-box").hidden = !(m && m.enabled && m.url);
    if (!m || !m.url) return;
    $("#mobile-url").textContent = m.url.split("?")[0] + (m.running ? "  · en marcha" : "  · guardando…");
    const img = $("#mobile-qr");
    img.hidden = !m.qr;
    if (m.qr) img.src = m.qr;
    $("#btn-mobile-copy").onclick = () => navigator.clipboard.writeText(m.url).then(() => toast("Enlace copiado. Es secreto: no lo compartas.", "ok"));
  }
  $("#btn-mobile-new").addEventListener("click", () => {
    if (confirm("El enlace actual dejará de funcionar y tendrás que escanear el nuevo. ¿Seguir?")) socket.emit("mobile_info", { new_token: true }, renderMobile);
  });
  socket.on("connect", () => socket.emit("mobile_info", {}, renderMobile));

  /* 7.4: tareas programadas y memoria */
  function renderTasks(res) {
    const ul = $("#tk-list");
    ul.innerHTML = "";
    const list = (res && res.tasks) || [];
    if (!list.length) ul.innerHTML = '<li class="empty">No hay tareas programadas.</li>';
    const dest = { voz: "en voz alta", celular: "al celular", ambos: "voz y celular" };
    list.forEach((t) => {
      const li = document.createElement("li");
      const b = document.createElement("div"); b.className = "r-body";
      const n = document.createElement("span"); n.className = "r-name"; n.textContent = t.orden;
      const m = document.createElement("span"); m.className = "r-meta";
      m.textContent = `${t.cuando} · ${dest[t.entrega] || t.entrega}` + (t.activa === false ? " · en pausa" : "") + (t.ultima ? ` · última: ${t.ultima}` : "");
      b.append(n, m);
      const run = document.createElement("button"); run.type = "button"; run.className = "text-btn"; run.textContent = "Probar";
      run.addEventListener("click", () => socket.emit("tasks_run", { id: t.id }, () => toast("Haciendo la tarea ahora…", "info")));
      const tog = document.createElement("button"); tog.type = "button"; tog.className = "text-btn"; tog.textContent = t.activa === false ? "Reanudar" : "Pausar";
      tog.addEventListener("click", () => socket.emit("tasks_toggle", { id: t.id, on: t.activa === false }, renderTasks));
      const del = document.createElement("button"); del.type = "button"; del.className = "text-btn"; del.textContent = "Borrar";
      del.addEventListener("click", () => { if (confirm(`¿Borrar la tarea «${t.orden}»?`)) socket.emit("tasks_remove", { id: t.id }, renderTasks); });
      li.append(b, run, tog, del);
      ul.appendChild(li);
    });
    if (res && "telegram" in res) {
      $("#tk-status").textContent = res.telegram ? "" : "Telegram no está conectado: lo que vaya «al celular» te lo diré en voz alta.";
    }
  }
  $("#tk-add").addEventListener("click", () => {
    socket.emit("tasks_add", { orden: $("#tk-orden").value, cuando: $("#tk-cuando").value, entrega: $("#tk-entrega").value }, (r) => {
      if (!r.ok) { toast(r.error, "err", 6000); return; }
      $("#tk-orden").value = ""; $("#tk-cuando").value = "";
      toast("Tarea programada: " + r.spoken, "ok", 5000);
      renderTasks(r);
    });
  });
  $("#btn-hist-clear").addEventListener("click", () => {
    if (confirm("¿Borrar todo el historial de conversaciones? No se puede deshacer.")) socket.emit("history_clear", {}, () => toast("Historial borrado.", "ok"));
  });
  socket.on("connect", () => socket.emit("tasks_list", {}, renderTasks));

  /* 7.7: galería de conectores y bandeja */
  let galData = null, galSel = null;
  function renderGallery(r) {
    if (!r) return;
    galData = r;
    const box = $("#gal"); box.innerHTML = "";
    const NAMES = { homeassistant: "casa", github: "github", notion: "notion", todoist: "todoist", hora: "hora", web: "web" };
    r.presets.forEach((p) => {
      const c = document.createElement("div"); c.className = "gal-card";
      const i = document.createElement("span"); i.className = "gi"; i.textContent = p.icono;
      const b = document.createElement("b"); b.textContent = p.nombre;
      const s = document.createElement("small"); s.textContent = p.descripcion;
      c.append(i, b, s);
      const inst = r.installed.includes(NAMES[p.id]);
      if (inst) { const o = document.createElement("span"); o.className = "on"; o.textContent = "● Conectado · clic para quitarlo"; c.appendChild(o); }
      else if (p.falta) { const w = document.createElement("span"); w.className = "warn"; w.textContent = `Necesita ${p.falta === "npx" ? "Node.js" : "uv"} instalado`; c.appendChild(w); }
      c.addEventListener("click", () => {
        if (inst) { if (confirm(`¿Quitar el conector «${p.nombre}»?`)) socket.emit("gallery_remove", { name: NAMES[p.id] }, renderGallery); return; }
        galSel = p;
        $("#gal-title").textContent = p.nombre; $("#gal-desc").textContent = p.descripcion;
        const f = $("#gal-fields"); f.innerHTML = "";
        p.campos.forEach((c2) => {
          const w = document.createElement("div"); w.className = "field stack";
          const ft = document.createElement("div"); ft.className = "ft";
          const l = document.createElement("label"); l.textContent = c2.label; ft.appendChild(l);
          if (c2.ayuda) { const h = document.createElement("p"); h.textContent = c2.ayuda; ft.appendChild(h); }
          const inp = document.createElement("input"); inp.className = "inp"; inp.type = c2.secret ? "password" : "text"; inp.dataset.k = c2.key; inp.placeholder = c2.placeholder || "";
          w.append(ft, inp); f.appendChild(w);
        });
        $("#gal-trust").checked = !!p.confianza;
        $("#gal-status").textContent = p.falta ? `Este conector necesita ${p.falta === "npx" ? "Node.js (nodejs.org)" : "uv (docs.astral.sh/uv)"} instalado en el equipo.` : "";
        $("#gal-form").hidden = false;
      });
      box.appendChild(c);
    });
  }
  $("#gal-save").addEventListener("click", () => {
    if (!galSel) return;
    const values = {};
    document.querySelectorAll("#gal-fields input").forEach((i) => { values[i.dataset.k] = i.value; });
    socket.emit("gallery_add", { id: galSel.id, values, trusted: $("#gal-trust").checked }, (r) => {
      if (!r.ok) { $("#gal-status").className = "status err"; $("#gal-status").textContent = r.error; return; }
      $("#gal-form").hidden = true; toast(`Conectado: ${galSel.nombre}. Tarda unos segundos en estar listo.`, "ok", 5000);
      renderGallery(r);
    });
  });
  $("#gal-cancel").addEventListener("click", () => { $("#gal-form").hidden = true; });
  socket.on("connect", () => socket.emit("gallery_list", {}, renderGallery));
  socket.on("mcp_status", () => socket.emit("gallery_list", {}, renderGallery));
  $("#btn-mail-test").addEventListener("click", () => {
    $("#mail-status").className = "status"; $("#mail-status").textContent = "Revisando…";
    socket.emit("mail_test", {}, (r) => {
      $("#mail-status").className = "status " + (r.ok ? "ok" : "err");
      $("#mail-status").textContent = r.ok ? `Funciona: ${r.n} correos recientes, ${r.importantes} que no son publicidad.` : r.error;
    });
  });

  /* 7.6: agente (aprobaciones, proyectos y registro) */
  function renderAgent(r) {
    if (!r) return;
    const ap = $("#ap-list"); ap.innerHTML = "";
    if (!r.pending.length) ap.innerHTML = '<li class="empty">Nada pendiente de aprobar.</li>';
    r.pending.forEach((a) => {
      const li = document.createElement("li");
      const b = document.createElement("div"); b.className = "r-body";
      const n = document.createElement("span"); n.className = "r-name"; n.textContent = `${a.id}. ${a.titulo}`;
      const m = document.createElement("span"); m.className = "r-meta"; m.textContent = a.detalle; m.title = a.detalle;
      b.append(n, m);
      const yes = document.createElement("button"); yes.type = "button"; yes.className = "btn btn-primary"; yes.textContent = "Aprobar";
      const no = document.createElement("button"); no.type = "button"; no.className = "text-btn"; no.textContent = "Rechazar";
      yes.addEventListener("click", () => socket.emit("approval_resolve", { id: a.id, ok: true }, renderAgent));
      no.addEventListener("click", () => socket.emit("approval_resolve", { id: a.id, ok: false }, renderAgent));
      li.append(b, yes, no); ap.appendChild(li);
    });
    const pj = $("#pj-list"); pj.innerHTML = "";
    if (!r.projects.length) pj.innerHTML = '<li class="empty">Aún no hay proyectos.</li>';
    r.projects.forEach((p) => {
      const li = document.createElement("li");
      const b = document.createElement("div"); b.className = "r-body";
      const n = document.createElement("span"); n.className = "r-name"; n.textContent = p.nombre;
      const m = document.createElement("span"); m.className = "r-meta";
      m.textContent = `${p.estado} · ${p.hechos} de ${p.total} pasos · ${new Date(p.creado * 1000).toLocaleString()}`;
      b.append(n, m); li.append(b);
      const btn = (txt, action) => { const x = document.createElement("button"); x.type = "button"; x.className = "text-btn"; x.textContent = txt;
        x.addEventListener("click", () => socket.emit("project_action", { id: p.id, action }, renderAgent)); li.appendChild(x); };
      btn("Abrir carpeta", "open");
      if (r.running === p.id) btn("Cancelar", "cancel");
      else if (p.estado === "interrumpido" || p.estado === "cancelado") btn("Continuar", "resume");
      pj.appendChild(li);
    });
    const h = $("#ag-hist"); h.innerHTML = "";
    const LBL = { pedida: "?", aprobada: "✓", rechazada: "✗", caducada: "…", hecha: "◆" };
    (r.history || []).slice().reverse().slice(0, 25).forEach((e) => {
      const li = document.createElement("li"); const i = document.createElement("b"); i.textContent = LBL[e.evento] || "·";
      const s = document.createElement("span"); s.textContent = `${e.ts.slice(5, 16).replace("T", " ")} · ${e.titulo || e.texto || ""}` + (e.por ? ` (${e.por})` : "");
      li.append(i, s); h.appendChild(li);
    });
    if (!(r.history || []).length) h.innerHTML = '<li><b>·</b><span>Nada todavía.</span></li>';
  }
  socket.on("connect", () => socket.emit("agent_info", {}, renderAgent));
  socket.on("approvals", () => socket.emit("agent_info", {}, renderAgent));
  document.querySelector('[data-tab="agente"]').addEventListener("click", () => socket.emit("agent_info", {}, renderAgent));

  /* 7.2: Jarvis dentro de Windows y el orbe de Windhawk */
  let orbCode = "";
  function renderWindows(w) {
    if (!w) return;
    orbCode = w.mod_code || "";
    $("#win-status").textContent = !w.supported ? "Solo en Windows (y no en modo USB)."
      : (w.msg || (w.installed ? "Activo: prueba el clic derecho en el escritorio o Win+R › jarvis." : "Apagado."));
    $("#orb-status").textContent = w.orb_connected ? "● El orbe está conectado." : "El orbe no está conectado (o Windhawk no está abierto).";
  }
  $("#btn-orb-copy").addEventListener("click", () => {
    if (!orbCode) { toast("No encuentro el archivo del mod (carpeta windhawk).", "err"); return; }
    navigator.clipboard.writeText(orbCode).then(() => toast("Código copiado. Pégalo en un mod nuevo de Windhawk.", "ok"));
  });
  $("#btn-orb-folder").addEventListener("click", () => socket.emit("open_windhawk_folder"));
  socket.on("connect", () => socket.emit("windows_info", {}, renderWindows));
  socket.on("settings_updated", () => setTimeout(() => socket.emit("windows_info", {}, renderWindows), 1500));
})();
