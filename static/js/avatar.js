/* 12.0 · Rostro holográfico de Jarvis: mueve la boca al ritmo de lo que dice y cambia de expresión según el momento.
   Uso: const av = JarvisFace(elemento, { big: true }); av.mode("speaking"); av.say("Hola…", tts_rate); av.mood("feliz"). */
(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  /* forma de la boca por letra: [apertura 0..1, ancho 0..1] */
  const VIS = { a: [1, .7], á: [1, .7], e: [.55, .9], é: [.55, .9], i: [.3, 1], í: [.3, 1], o: [.8, .45], ó: [.8, .45], u: [.5, .3], ú: [.5, .3],
                m: [0, .6], b: [0, .6], p: [0, .6], f: [.15, .75], v: [.15, .75], l: [.35, .65], s: [.2, .85], r: [.35, .6], " ": [.05, .6] };
  const MOODS = {
    neutral: { brow: 0, smile: .15, eye: 1 }, feliz: { brow: -2, smile: .6, eye: .85 }, preocupado: { brow: 4, smile: -.25, eye: 1 },
    curioso: { brow: -4, smile: .1, eye: 1.15 }, pensando: { brow: 2, smile: 0, eye: .9 }, atento: { brow: -3, smile: .2, eye: 1.2 },
  };
  function el(tag, attrs, parent) { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }

  function moodOf(text) {
    const t = String(text || "").toLowerCase();
    if (/no pude|error|fall[óo]|lo siento|no tengo|no encontr|cuidado|ojo:|en riesgo|alerta/.test(t)) return "preocupado";
    if (/listo|¡|genial|felicit|excelente|muy bien|lo logr|aprobad|hecho/.test(t)) return "feliz";
    if (/\?\s*$|¿/.test(t)) return "curioso";
    return "neutral";
  }

  window.JarvisFace = function (host, opts) {
    opts = opts || {};
    const svg = el("svg", { viewBox: "0 0 200 200", class: "jf" + (opts.big ? " jf-big" : ""), "aria-hidden": "true" });
    const defs = el("defs", {}, svg);
    const glow = el("filter", { id: "jfglow" + (opts.big ? "b" : "s"), x: "-50%", y: "-50%", width: "200%", height: "200%" }, defs);
    el("feGaussianBlur", { stdDeviation: opts.big ? 2.2 : 1.4, result: "b" }, glow);
    const mg = el("feMerge", {}, glow); el("feMergeNode", { in: "b" }, mg); el("feMergeNode", { in: "SourceGraphic" }, mg);
    const grad = el("radialGradient", { id: "jfg" + (opts.big ? "b" : "s"), cx: "50%", cy: "42%", r: "60%" }, defs);
    el("stop", { offset: "0", "stop-color": "currentColor", "stop-opacity": ".22" }, grad); el("stop", { offset: "1", "stop-color": "currentColor", "stop-opacity": "0" }, grad);
    const g = el("g", { filter: `url(#jfglow${opts.big ? "b" : "s"})`, fill: "none", stroke: "currentColor", "stroke-linecap": "round", "stroke-linejoin": "round" }, svg);
    const fl = el("g", {}, g);                                                  // flota
    el("ellipse", { cx: 100, cy: 98, rx: 66, ry: 80, fill: `url(#jfg${opts.big ? "b" : "s"})`, stroke: "none" }, fl);
    el("path", { d: "M100 18 C150 18 168 58 166 98 C164 140 140 176 100 178 C60 176 36 140 34 98 C32 58 50 18 100 18 Z", "stroke-width": 2.5, opacity: .9 }, fl);
    // líneas del holograma (malla)
    for (let i = 0; i < 6; i++) el("path", { d: `M${44 + i * 2} ${50 + i * 22} Q100 ${42 + i * 24} ${156 - i * 2} ${50 + i * 22}`, "stroke-width": .7, opacity: .25 }, fl);
    el("path", { d: "M100 20 Q86 98 100 176 M100 20 Q114 98 100 176", "stroke-width": .7, opacity: .2 }, fl);
    const browL = el("path", { "stroke-width": 3.2 }, fl), browR = el("path", { "stroke-width": 3.2 }, fl);
    const eyeL = el("ellipse", { cx: 74, cy: 84, rx: 11, ry: 8, "stroke-width": 2.6 }, fl), eyeR = el("ellipse", { cx: 126, cy: 84, rx: 11, ry: 8, "stroke-width": 2.6 }, fl);
    const pupL = el("circle", { cx: 74, cy: 84, r: 3.6, fill: "currentColor", stroke: "none" }, fl), pupR = el("circle", { cx: 126, cy: 84, r: 3.6, fill: "currentColor", stroke: "none" }, fl);
    el("path", { d: "M100 92 L94 118 L104 120", "stroke-width": 1.8, opacity: .7 }, fl);
    const mouth = el("path", { "stroke-width": 2.8, fill: "currentColor", "fill-opacity": .18 }, fl);
    const scan = el("rect", { x: 30, y: 0, width: 140, height: 3, fill: "currentColor", stroke: "none", opacity: .18 }, svg);
    host.appendChild(svg);

    const S = { mode: "idle", mood: "neutral", open: .05, wide: .6, tOpen: .05, tWide: .6, blink: 0, look: [0, 0], text: "", ci: 0, rate: 0, last: 0, t0: performance.now(), moodUntil: 0 };
    function draw(now) {
      const m = MOODS[S.mood] || MOODS.neutral, t = (now - S.t0) / 1000;
      fl.setAttribute("transform", `translate(0 ${Math.sin(t * 1.4) * 2.2})`);
      scan.setAttribute("y", (t * 60) % 200);
      const b = m.brow + (S.mode === "thinking" ? 2 : 0);
      browL.setAttribute("d", `M60 ${66 + b} Q74 ${58 + b * .4} 88 ${64 + b * .2}`);
      browR.setAttribute("d", `M112 ${64 + b * .2} Q126 ${58 + b * .4} 140 ${66 + b}`);
      const ey = Math.max(.08, 8 * m.eye * (1 - S.blink));
      eyeL.setAttribute("ry", ey); eyeR.setAttribute("ry", ey);
      const lx = S.look[0] * 4, ly = S.look[1] * 3;
      for (const [p, x] of [[pupL, 74], [pupR, 126]]) { p.setAttribute("cx", x + lx); p.setAttribute("cy", 84 + ly); p.setAttribute("r", S.blink > .6 ? 0 : 3.6); }
      // boca: interpola hacia la forma de la letra actual
      S.open += (S.tOpen - S.open) * .35; S.wide += (S.tWide - S.wide) * .35;
      const w = 16 + 14 * S.wide, o = 2 + 16 * S.open, sm = m.smile * 8, cy = 140;
      mouth.setAttribute("d", `M${100 - w} ${cy - sm * .3} Q100 ${cy - o * .45 + sm * .2} ${100 + w} ${cy - sm * .3} Q100 ${cy + o + sm} ${100 - w} ${cy - sm * .3} Z`);
    }
    function tick(now) {
      const dt = now - S.last; S.last = now;
      // parpadeo
      if (S.blink > 0) S.blink = Math.max(0, S.blink - dt / 90); else if (Math.random() < dt / 3800) S.blink = 1;
      // mirada
      if (S.mode === "thinking") S.look = [.4, -.8]; else if (S.mode === "awaiting") S.look = [0, 0]; else if (Math.random() < dt / 2500) S.look = [Math.random() * 1.6 - .8, Math.random() * .8 - .4];
      // hablar: recorre el texto a la velocidad de la voz
      if (S.mode === "speaking" && S.text) {
        const cps = 14 * (1 + (S.rate || 0) / 100);
        S.ci += dt / 1000 * cps;
        const ch = S.text[Math.floor(S.ci) % S.text.length] || " ";
        const v = VIS[ch] || [.4, .6];
        S.tOpen = v[0] * (.75 + Math.random() * .25); S.tWide = v[1];
      } else { S.tOpen = S.mode === "awaiting" ? .12 : .04; S.tWide = .6; }
      if (S.moodUntil && now > S.moodUntil && S.mode !== "speaking") { S.mood = S.mode === "thinking" ? "pensando" : S.mode === "awaiting" ? "atento" : "neutral"; S.moodUntil = 0; }
      draw(now);
      if (svg.isConnected) requestAnimationFrame(tick);
    }
    requestAnimationFrame((n) => { S.last = n; tick(n); });
    return {
      el: svg,
      mode(m) {
        S.mode = m || "idle";
        if (S.mode === "thinking") S.mood = "pensando"; else if (S.mode === "awaiting") S.mood = "atento";
        else if (S.mode === "speaking") S.ci = 0; else if (!S.moodUntil) S.mood = "neutral";
        svg.dataset.mode = S.mode;
      },
      say(text, rate) {
        S.text = String(text || "").toLowerCase().replace(/[^a-záéíóúñü\s]/g, " ").replace(/\s+/g, " ");
        S.rate = Number(rate) || 0; S.ci = 0; S.mood = moodOf(text); S.moodUntil = performance.now() + 9000;
      },
      mood(m) { if (MOODS[m]) { S.mood = m; S.moodUntil = performance.now() + 9000; } },
    };
  };
  window.JarvisFace.moodOf = moodOf;
})();
