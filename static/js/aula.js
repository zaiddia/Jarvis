/* J.A.R.V.I.S. — tablero del aula */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const body = document.body;
  let A = { cursos: {}, activo: "", ausentes: [] };   // estado que manda Jarvis
  let editing = null;                                 // curso que se edita en «Cursos»
  const files = [];

  function toast(msg, kind = "info", action = null, ms = 5000) {
    const t = document.createElement("div");
    t.className = `toast ${kind}`;
    const sp = document.createElement("span");
    sp.textContent = msg;
    t.appendChild(sp);
    if (action) {
      const b = document.createElement("button");
      b.textContent = action.label;
      b.addEventListener("click", action.fn);
      t.appendChild(b);
    }
    $("#toasts").appendChild(t);
    setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 320); }, ms);
  }

  /* ---------------- Vistas ---------------- */
  function show(view) {
    if (!$(`.view[data-view="${view}"]`)) return;
    body.dataset.view = view;
    $$(".view").forEach((v) => { v.hidden = v.dataset.view !== view; });
    $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === view));
    if (view === "asistencia") renderAttendance();
    if (view === "cursos") renderCourses();
  }
  $$(".tab").forEach((t) => {
    t.title = t.textContent.trim();             // por si solo se ve el icono
    t.setAttribute("aria-label", t.title);
    t.addEventListener("click", () => show(t.dataset.tab));
  });

  /* ---------------- Curso activo ---------------- */
  function names() { return A.cursos[A.activo] || []; }

  function renderCourseSelect() {
    const sel = $("#course");
    sel.innerHTML = "";
    const keys = Object.keys(A.cursos);
    if (!keys.length) sel.appendChild(new Option("Sin cursos", ""));
    keys.forEach((k) => sel.appendChild(new Option(`${k} · ${A.cursos[k].length}`, k)));
    sel.value = A.activo || "";
  }
  $("#course").addEventListener("change", (e) => {
    socket.emit("aula_set_active", { name: e.target.value }, apply);
  });

  function apply(res) {
    if (!res) return;
    if (res.ok === false && res.error) toast(res.error, "err");
    A = { ...A, ...res };
    renderCourseSelect();
    renderStudentSelect();
    if (body.dataset.view === "asistencia") renderAttendance();
    if (body.dataset.view === "cursos") renderCourses();
    updatePickMeta();
  }

  /* ---------------- Ruleta ---------------- */
  let spinTimer = null;
  function updatePickMeta(quedan, total) {
    const n = names().length;
    if (!n) {
      $("#pick-meta").textContent = "Primero crea un curso en la pestaña Cursos.";
      return;
    }
    if (quedan !== undefined) {
      $("#pick-meta").textContent = quedan
        ? `${A.activo} · quedan ${quedan} de ${total} por pasar en esta ronda`
        : `${A.activo} · ronda completa: la próxima vez empiezan todos de nuevo`;
    }
  }

  function spinTo(name, quedan, total) {
    const el = $("#pick-name");
    const pool = names().length ? names() : [name];
    clearTimeout(spinTimer);
    el.classList.remove("landed");
    el.classList.add("spinning");
    $("#pick-kicker").textContent = "Sorteando…";
    let delay = 45, elapsed = 0;
    const step = () => {
      el.textContent = pool[Math.floor(Math.random() * pool.length)];
      elapsed += delay;
      delay *= 1.12;                                   // se va frenando, como una ruleta
      if (elapsed < 1500) { spinTimer = setTimeout(step, delay); return; }
      el.textContent = name;
      el.classList.remove("spinning");
      el.classList.add("landed");
      $("#pick-kicker").textContent = "Le toca a";
      updatePickMeta(quedan, total);
    };
    step();
  }

  $("#btn-pick").addEventListener("click", () => socket.emit("aula_pick", {}, (r) => { if (r && r.ok === false) toast(r.error, "err"); }));
  $("#btn-reset-pick").addEventListener("click", () => socket.emit("aula_reset_pick", {}, (r) => {
    apply(r);
    toast("Nueva ronda: todos vuelven a participar.", "ok");
  }));
  document.addEventListener("keydown", (e) => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || "");
    if (e.code === "Space" && !typing && body.dataset.view === "ruleta") { e.preventDefault(); $("#btn-pick").click(); }
    if (e.key === "F11") { e.preventDefault(); fullscreen(); }
  });

  /* ---------------- Grupos ---------------- */
  function renderGroups(groups) {
    const box = $("#groups");
    box.innerHTML = "";
    groups.forEach((g, i) => {
      const card = document.createElement("div");
      card.className = "group";
      card.style.animationDelay = `${i * 40}ms`;
      const h = document.createElement("h3");
      h.textContent = `GRUPO ${i + 1}`;
      const ul = document.createElement("ul");
      g.forEach((n) => { const li = document.createElement("li"); li.textContent = n; ul.appendChild(li); });
      card.append(h, ul);
      box.appendChild(card);
    });
  }
  $("#g-count").addEventListener("input", () => { if ($("#g-count").value) $("#g-size").value = ""; });
  $("#g-size").addEventListener("input", () => { if ($("#g-size").value) $("#g-count").value = ""; });
  $("#btn-groups").addEventListener("click", () => {
    socket.emit("aula_groups", { size: $("#g-size").value, count: $("#g-count").value },
      (r) => { if (r && r.ok === false) toast(r.error, "err"); });
  });

  /* ---------------- Asistencia ---------------- */
  function renderAttendance() {
    const box = $("#att-list");
    box.innerHTML = "";
    const list = names();
    const aus = new Set(A.ausentes || []);
    if (!list.length) {
      box.innerHTML = '<p class="empty">Crea un curso en la pestaña Cursos para tomar asistencia.</p>';
      $("#att-count").textContent = "—";
      return;
    }
    list.forEach((n) => {
      const b = document.createElement("button");
      b.className = "chip" + (aus.has(n) ? " absent" : "");
      b.textContent = n;
      b.title = aus.has(n) ? "Ausente · toca para marcar presente" : "Presente · toca para marcar ausente";
      b.addEventListener("click", () => {
        socket.emit("aula_mark", { name: n, present: aus.has(n) }, apply);
      });
      box.appendChild(b);
    });
    const hoy = new Date().toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "long" });
    $("#att-count").textContent = `${A.activo} · presentes ${list.length - aus.size} de ${list.length} · ${hoy}`;
  }
  $("#btn-export").addEventListener("click", () => socket.emit("aula_export", {}, (r) => {
    if (r && r.ok === false) toast(r.error, "err");
  }));

  /* ---------------- Semáforo de ruido ---------------- */
  const store = {
    get: (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* sin almacenamiento */ } },
  };
  const tol = $("#tol");
  tol.value = store.get("aula_tol", "0.22");
  let level = 0, shown = "g", since = Date.now(), lastLevelAt = 0, micState = "";
  function marks() {
    const y = Number(tol.value), r = Math.min(1, y * 1.8);
    $("#mark-y").style.left = `${y * 100}%`;
    $("#mark-r").style.left = `${r * 100}%`;
    return { y, r };
  }
  marks();
  tol.addEventListener("input", () => { store.set("aula_tol", tol.value); marks(); });
  function onLevel(v) {
    lastLevelAt = Date.now();
    level = level * 0.82 + v * 0.18;                    // suaviza: reacciona al ruido sostenido, no a un golpe
    if (body.dataset.view !== "semaforo") return;
    $("#meter-fill").style.width = `${Math.min(100, level * 100)}%`;
    const { y, r } = marks();
    const want = level >= r ? "r" : level >= y ? "y" : "g";
    const rank = { g: 0, y: 1, r: 2 };
    // sube de inmediato; para bajar espera 1,5 s (evita parpadeos)
    if (rank[want] > rank[shown] || (want !== shown && Date.now() - since > 1500)) {
      shown = want;
      since = Date.now();
      paintLight(shown);
    } else if (want === shown) {
      since = Date.now();
    }
  }
  function paintLight(lv) {
    const L = $("#light");
    L.dataset.level = lv;
    $("#light-label").textContent = { g: "Bien", y: "Un poco de ruido", r: "¡Silencio, por favor!", off: "Activa el micrófono de Jarvis" }[lv];
  }
  setInterval(() => {                                    // sin datos del micrófono
    if (body.dataset.view === "semaforo" && (Date.now() - lastLevelAt > 2500 || micState === "off")) paintLight("off");
  }, 1000);

  /* ---------------- Material ---------------- */
  const CANT = { quiz: "Preguntas", taller: "Ejercicios", rubrica: "Criterios", plan: "" };
  function kind() { return $("[name=kind]:checked").value; }
  function syncKind() {
    const k = kind();
    $("#m-cant-wrap").hidden = !CANT[k];
    $("#m-cant-label").textContent = CANT[k];
    $("#m-cant").placeholder = { quiz: "10", taller: "8", rubrica: "4" }[k] || "";
  }
  $$("[name=kind]").forEach((r) => r.addEventListener("change", syncKind));
  syncKind();
  $("#mat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    socket.emit("aula_material", {
      kind: kind(), tema: $("#m-tema").value, grado: $("#m-grado").value,
      cantidad: $("#m-cant").value, extra: $("#m-extra").value,
    }, (r) => { if (r && r.ok === false) toast(r.error, "err"); });
  });
  function setMatStatus(text, cls) {
    const st = $("#mat-status");
    st.className = "status " + (cls || "");
    st.textContent = text;
    $("#btn-mat").disabled = cls === "work";
  }
  function addFile(name, path) {
    files.unshift({ name, path });
    const ul = $("#files");
    ul.innerHTML = "";
    files.forEach((f) => {
      const li = document.createElement("li");
      const sp = document.createElement("span");
      sp.textContent = f.name;
      sp.title = f.path;
      const b = document.createElement("button");
      b.className = "text-btn";
      b.textContent = "Abrir";
      b.addEventListener("click", () => socket.emit("aula_open", { path: f.path }));
      li.append(sp, b);
      ul.appendChild(li);
    });
  }
  $("#btn-folder").addEventListener("click", () => socket.emit("aula_open_folder", {}));
  function saveTeacher() {
    socket.emit("aula_teacher", {
      aula_docente: $("#t-docente").value, aula_institucion: $("#t-inst").value,
      aula_open_docs: $("#t-open").checked,
    }, (r) => { if (r && r.ok) toast("Datos del encabezado guardados.", "ok", null, 2200); });
  }
  ["#t-docente", "#t-inst"].forEach((s) => $(s).addEventListener("change", saveTeacher));
  $("#t-open").addEventListener("change", saveTeacher);

  /* ---------------- Revisar trabajos ---------------- */
  function renderStudentSelect() {
    const sel = $("#rv-student");
    const keep = sel.value;
    sel.innerHTML = "";
    sel.appendChild(new Option("— Sin indicar —", ""));
    names().forEach((n) => sel.appendChild(new Option(n, n)));
    if ([...sel.options].some((o) => o.value === keep)) sel.value = keep;
  }
  function setRvStatus(text, cls) {
    const st = $("#rv-status");
    st.className = "status " + (cls || "");
    st.textContent = text;
    $("#rv-run").disabled = cls === "work";
  }
  function showPreview(src) {
    const box = $("#rv-preview");
    box.innerHTML = "";
    const img = new Image();
    img.src = src;
    img.alt = "Trabajo a revisar";
    box.appendChild(img);
  }
  function captured(r) {
    if (!r || r.ok === false) { setRvStatus(r ? r.error : "No se pudo capturar.", "err"); return; }
    showPreview(r.preview);
    $("#rv-result").hidden = true;
    setRvStatus("Imagen lista. Revisa que se lea bien y pulsa «Revisar con IA».", "ok");
  }
  $("#rv-cam").addEventListener("click", () => {
    setRvStatus("Tomando la foto… mantén la hoja quieta.", "work");
    socket.emit("aula_teacher", { camera_index: Number($("#rv-camidx").value) || 0 }, () =>
      socket.emit("review_capture", { source: "camara" }, captured));
  });
  $("#rv-screen").addEventListener("click", () => {
    setRvStatus("Capturando la pantalla…", "work");
    socket.emit("review_capture", { source: "pantalla" }, captured);
  });
  $("#rv-file").addEventListener("change", (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    if (f.size > 15 * 1024 * 1024) { setRvStatus("La imagen es muy grande (máximo 15 MB).", "err"); return; }
    const rd = new FileReader();
    rd.onload = () => { setRvStatus("Cargando la imagen…", "work"); socket.emit("review_upload", { data: rd.result }, captured); };
    rd.readAsDataURL(f);
    e.target.value = "";
  });
  $("#rv-run").addEventListener("click", () => {
    socket.emit("review_run", {
      estudiante: $("#rv-student").value, que: $("#rv-que").value,
      grado: $("#rv-grado").value, clave: $("#rv-clave").value, asignatura: $("#rv-subj").value,
    }, (r) => { if (r && r.ok === false) setRvStatus(r.error, "err"); });
  });
  let reviewDoc = "";
  $("#rv-open").addEventListener("click", () => { if (reviewDoc) socket.emit("aula_open", { path: reviewDoc }); });
  function renderReview(ev) {
    const r = ev.result;
    $("#rv-result").hidden = false;
    const g = $("#rv-grade");
    g.textContent = r.nota == null ? "—" : String(r.nota.toFixed(1)).replace(".", ",");
    g.className = "grade " + (r.nota == null ? "" : r.nota < 3 ? "low" : r.nota < 4 ? "mid" : "high");
    $("#rv-who").textContent = [ev.estudiante || r.estudiante_en_hoja, r.que_es].filter(Boolean).join(" · ");
    $("#rv-resumen").textContent = r.legible ? r.resumen : `No se lee bien: ${r.resumen || "acerca la hoja o usa una foto."}`;
    $("#rv-just").textContent = r.justificacion_nota || "";
    const ok = $("#rv-ok"), er = $("#rv-err");
    ok.innerHTML = ""; er.innerHTML = "";
    (r.aciertos || []).forEach((a) => { const li = document.createElement("li"); li.textContent = a; ok.appendChild(li); });
    if (!(r.aciertos || []).length) ok.innerHTML = '<li class="empty">—</li>';
    (r.errores || []).forEach((e) => {
      const li = document.createElement("li");
      const b = document.createElement("b"); b.textContent = e.donde || "Error";
      const sp = document.createElement("span"); sp.textContent = e.que_esta_mal;
      li.append(b, sp);
      if (e.correccion) { const em = document.createElement("em"); em.textContent = "✓ " + e.correccion; li.appendChild(em); }
      er.appendChild(li);
    });
    if (!(r.errores || []).length) er.innerHTML = '<li class="empty">Sin errores</li>';
    $("#rv-feedback").textContent = r.retroalimentacion || "—";
    reviewDoc = ev.doc || "";
    $("#rv-open").hidden = !reviewDoc;
    setRvStatus(reviewDoc ? `Listo. Guardado: ${ev.docname}` : "Listo.", "ok");
  }

  /* ---------------- Cursos ---------------- */
  function renderCourses() {
    const ul = $("#course-list");
    ul.innerHTML = "";
    const keys = Object.keys(A.cursos);
    if (!keys.length) ul.innerHTML = '<li class="empty">Todavía no hay cursos.</li>';
    keys.forEach((k) => {
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.className = k === editing ? "sel" : "";
      b.innerHTML = "<span></span><small></small>";
      b.firstChild.textContent = k;
      b.lastChild.textContent = `${A.cursos[k].length} estudiantes`;
      b.addEventListener("click", () => editCourse(k));
      li.appendChild(b);
      ul.appendChild(li);
    });
    if (editing === null && keys.length) editCourse(A.activo || keys[0]);
  }
  function editCourse(k) {
    editing = k || "";
    $("#ed-title").textContent = k ? `Curso ${k}` : "Nuevo curso";
    $("#ed-name").value = k || "";
    $("#ed-names").value = k ? (A.cursos[k] || []).join("\n") : "";
    $("#btn-del-course").hidden = !k;
    $("#btn-del-course").classList.remove("armed");
    countNames();
    $$("#course-list button").forEach((b) => b.classList.toggle("sel", b.firstChild.textContent === k));
  }
  function countNames() {
    const n = $("#ed-names").value.split("\n").filter((l) => /[A-Za-zÁÉÍÓÚÑáéíóúñ]/.test(l)).length;
    $("#ed-count").textContent = n ? `(${n})` : "";
  }
  $("#ed-names").addEventListener("input", countNames);
  $("#btn-new-course").addEventListener("click", () => { editCourse(""); $("#ed-name").focus(); });
  $("#btn-save-course").addEventListener("click", () => {
    const name = $("#ed-name").value.trim();
    socket.emit("aula_save_course", { name, text: $("#ed-names").value, old: editing || null }, (r) => {
      apply(r);
      if (r && r.ok !== false) {
        editing = name;
        renderCourses();
        editCourse(name);
        const st = $("#ed-status");
        st.className = "status ok";
        st.textContent = `Guardado: ${(A.cursos[name] || []).length} estudiantes en ${name}.`;
      }
    });
  });
  $("#btn-del-course").addEventListener("click", (e) => {
    const b = e.currentTarget;
    if (!b.classList.contains("armed")) {               // confirmación con dos clics
      b.classList.add("armed");
      b.lastChild.textContent = "¿Seguro? Pulsa otra vez";
      setTimeout(() => { b.classList.remove("armed"); b.lastChild.textContent = "Eliminar"; }, 3500);
      return;
    }
    socket.emit("aula_delete_course", { name: editing }, (r) => { editing = null; apply(r); renderCourses(); });
  });

  /* ---------------- Pantalla completa ---------------- */
  let native = true;
  function fullscreen() {
    if (native) { socket.emit("aula_fullscreen", {}); return; }
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen?.();
  }
  $("#btn-full").addEventListener("click", fullscreen);

  /* ---------------- Enlace con Jarvis ---------------- */
  const socket = io();
  // 10.4: área o asignatura de la revisión
  socket.on("connect", () => socket.emit("subjects_info", {}, (r) => {
    if (!r) return;
    const sel = $("#rv-subj"), keep = sel.value;
    sel.innerHTML = '<option value="">Automática (la escogida o la del horario)</option>' +
      (r.choices || []).map((c) => `<option>${c.replace(/</g, "&lt;")}</option>`).join("");
    sel.value = keep;
  }));
  socket.on("connect", () => {
    socket.emit("aula_get", {}, (r) => {
      apply(r);
      native = !!r.native;                              // ventana propia de Jarvis o navegador
      document.documentElement.dataset.theme = r.theme || "cyan";
      $("#t-docente").value = r.docente || "";
      $("#t-inst").value = r.institucion || "";
      $("#t-open").checked = !!r.open_docs;
      micState = r.mic || "";
      if (r.busy) setMatStatus("Preparando material…", "work");
      $("#rv-camidx").value = r.camera_index || 0;
      if (r.review_busy) setRvStatus("Revisando con la IA…", "work");
      if (r.last && r.last.type === "groups") renderGroups(r.last.groups);
      if (r.last && r.last.type === "pick") {
        $("#pick-name").textContent = r.last.name;
        $("#pick-name").classList.add("landed");
        updatePickMeta(r.last.quedan, r.last.total);
      }
      if (!Object.keys(A.cursos).length) show("cursos");
      else show(r.view || "ruleta");
    });
  });
  socket.on("aula", (ev) => {
    if (!ev) return;
    if (ev.view) show(ev.view);
    if (ev.type === "pick") spinTo(ev.name, ev.quedan, ev.total);
    if (ev.type === "groups") renderGroups(ev.groups);
    if (ev.type === "attendance" || ev.type === "course") apply(ev);
    if (ev.type === "exported") {
      toast(`Asistencia guardada: ${ev.name}`, "ok", { label: "Abrir", fn: () => socket.emit("aula_open", { path: ev.path }) });
    }
    if (ev.type === "review") {
      if (ev.status === "working") {
        if (ev.preview) showPreview(ev.preview);
        $("#rv-result").hidden = true;
        setRvStatus("Revisando con la IA… suele tardar entre 10 y 30 segundos.", "work");
      }
      if (ev.status === "done") renderReview(ev);
      if (ev.status === "error") setRvStatus(ev.error, "err");
    }
    if (ev.type === "material") {
      if (ev.status === "working") setMatStatus(`Preparando ${ev.label.toLowerCase()}… suele tardar menos de un minuto.`, "work");
      if (ev.status === "done") {
        setMatStatus(`Listo: «${ev.title}».`, "ok");
        addFile(ev.name, ev.path);
        toast(`Listo: ${ev.name}`, "ok", { label: "Abrir", fn: () => socket.emit("aula_open", { path: ev.path }) }, 8000);
      }
      if (ev.status === "error") setMatStatus(`No salió: ${ev.error}`, "err");
    }
  });
  socket.on("mic_level", (d) => onLevel(Number(d && d.v) || 0));
  socket.on("state", (s) => { micState = (s && s.mic) || micState; });
  socket.on("settings_updated", (s) => { if (s && s.theme) document.documentElement.dataset.theme = s.theme; });
})();
