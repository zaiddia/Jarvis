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
  const PART_NAMES = { ajustes: "Ajustes", notas: "Notas", aula: "Cursos y asistencia", rutinas: "Rutinas", memoria: "Memoria" };
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
})();
