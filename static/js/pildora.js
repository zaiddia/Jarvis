/* J.A.R.V.I.S. 12.13 — el HUD como píldora en el borde derecho.
   Se esconde tras unos segundos sin usarlo y se abre al pasar el ratón por la píldora.
   No se esconde con el ratón encima, mientras escribes, mientras Jarvis te escucha, piensa o
   habla, durante el dictado ni mientras arrastras el HUD. */
(() => {
  "use strict";
  const H = window.JarvisHUD;
  if (!H) return;
  const body = document.body, pillEl = document.getElementById("pill");
  const badge = pillEl.querySelector(".pill-badge");
  const socket = H.socket;
  const HOVER_MS = 160;                 // pasar de largo por el borde no la abre
  let docked = false, dockedAt = 0, waiting = false, hover = false, last = Date.now(), unread = 0, enterT = 0;

  const enabled = () => H.native() && H.settings().hud_auto_hide !== false;
  const delay = () => Math.max(2, Number(H.settings().hud_hide_secs) || 5) * 1000;
  const touch = () => { last = Date.now(); };

  function keepOpen() {
    if (hover || H.dragging() || H.dictating()) return true;
    if (H.mode() !== "idle") return true;                                  // escuchando, pensando o hablando
    const a = document.activeElement;
    if (a && a.matches && a.matches("input, textarea, select") && String(a.value || "").trim()) return true;   // a medio escribir
    if (document.querySelector("#pal:not([hidden]), #ntc:not([hidden]), #dock:not([hidden]), #aipick:not([hidden]), #vid:not([hidden])")) return true;                  // paleta de órdenes
    return false;
  }

  function setDocked(on) {
    docked = on; waiting = false; if (on) dockedAt = Date.now();
    body.classList.toggle("pill-mode", on);
    pillEl.hidden = !on;
    hover = false; touch();
    if (!on) { unread = 0; H.poke(); }                 // 12.21: recién abierto se ve a plena luz
    drawBadge();
  }

  function drawBadge() {
    const n = H.pending() || 0;
    pillEl.classList.toggle("attn", n > 0);
    badge.hidden = !(docked && unread > 0);
    pillEl.dataset.state = H.mode();
    const mic = H.mic();                                                   // 12.13.1: si no te puede oír, la píldora lo muestra
    const paused = H.settings().mic_enabled === false;
    pillEl.dataset.mic = mic === "on" ? "on" : mic === "error" ? "err" : paused ? "off" : "wait";
    pillEl.title = mic === "on" ? "Jarvis te escucha · pasa el ratón para abrir" : mic === "error" ? "El micrófono falló · pasa el ratón para ver"
      : paused ? "Micrófono en pausa · ábreme y pulsa el botón del micrófono" : "Activando el micrófono…";
  }

  function open() { if ((docked || window.innerWidth < 80) && !waiting && Date.now() - dockedAt > 700) {   // recién escondida: el ratón ya no está ahí
    waiting = true; socket.emit("hud_dock", { on: false }); setTimeout(() => { waiting = false; }, 3000); } }

  // Ratón: sobre la página = sobre la ventana del HUD (o de la píldora).
  document.addEventListener("pointermove", () => { hover = true; touch(); }, { passive: true });
  document.addEventListener("pointerdown", () => { hover = true; touch(); if (docked || window.innerWidth < 80) open(); });
  document.addEventListener("keydown", touch);
  document.addEventListener("wheel", touch, { passive: true });
  document.documentElement.addEventListener("mouseleave", () => { hover = false; clearTimeout(enterT); touch(); });
  document.documentElement.addEventListener("mouseenter", () => {
    hover = true; touch();
    if (docked) { clearTimeout(enterT); enterT = setTimeout(() => { if (hover) open(); }, HOVER_MS); }
  });
  pillEl.addEventListener("pointerenter", () => { if (docked || window.innerWidth < 80) { clearTimeout(enterT); enterT = setTimeout(open, HOVER_MS); } });

  socket.on("hud_pill", (d) => {
    if (d && d.refused) { waiting = false; touch(); return; }   // el ratón sigue encima: espera otro rato
    setDocked(!!(d && d.on));
  });
  socket.on("connect", () => socket.emit("hud_pill_state", {}, (d) => { if (d) setDocked(!!d.on); }));
  socket.on("state", (s) => {
    if (s && s.mode && s.mode !== "idle") touch();          // 12.13.1: al decir «Jarvis» la abre Jarvis mismo (no depende de esta página)
    drawBadge();
  });
  socket.on("chat", (item) => { touch(); if (docked && item && item.role !== "user") { unread++; drawBadge(); } });
  socket.on("focus_input", open);
  socket.on("settings_updated", () => { touch(); drawBadge(); });

  setInterval(() => {
    drawBadge();
    if (docked || waiting || !enabled() || keepOpen()) { if (!docked && keepOpen()) touch(); return; }
    if (Date.now() - last >= delay()) { waiting = true; socket.emit("hud_dock", { on: true }); setTimeout(() => { waiting = false; }, 3000); }
  }, 250);
})();
