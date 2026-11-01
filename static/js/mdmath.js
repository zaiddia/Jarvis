/* 11.8: formato de las respuestas de Jarvis (HUD y proyector): negritas, listas, tablas y fórmulas $…$ con KaTeX.
   Todo el texto se escapa antes; solo se inserta el HTML que genera KaTeX (con trust: false). */
(() => {
  "use strict";
  const SEG = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|(?<![\\\w$])\$(?!\s)([^$\n]{1,400}?)(?<!\s)\$(?![\w$])/g;
  function esc(s) { return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
  function tex(src, display) {
    if (window.katex) {
      try { return window.katex.renderToString(src, { throwOnError: false, displayMode: !!display, trust: false, strict: "ignore", output: "html" }); }
      catch (e) { /* cae al texto */ }
    }
    return `<code class="mathraw">${esc(src)}</code>`;
  }
  function inline(s) {
    return s.replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
      .replace(/(^|[\s(«])\*([^*\n]+)\*(?=[\s.,;:!?)»]|$)/g, "$1<i>$2</i>").replace(/(^|[\s(«])_([^_\n]+)_(?=[\s.,;:!?)»]|$)/g, "$1<i>$2</i>")
      .replace(/(\b[a-zA-Z0-9)])\^(\d{1,2}|n)\b/g, "$1<sup>$2</sup>")                 // x^2 sin $…$: igual se ve bien
      .replace(/\bsqrt\(/g, "√(");
  }
  function md(text) {
    const maths = [];
    let src = String(text || "").replace(SEG, (m, a, b, c, d) => {
      const f = a ?? b ?? c ?? d, display = a != null || b != null;
      maths.push(tex(f.trim(), display));
      return `\u0000${maths.length - 1}\u0000`;
    });
    const lines = esc(src).split("\n");
    let out = "", list = "", i = 0;
    const close = () => { if (list) { out += `</${list}>`; list = ""; } };
    const isRow = (ln) => /^\s*\|.*\|\s*$/.test(ln);
    while (i < lines.length) {
      const ln = lines[i];
      let m;
      if (isRow(ln) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {      // tabla
        close();
        const cells = (r) => r.trim().replace(/^\||\|$/g, "").split("|").map((c) => inline(c.trim()));
        out += "<div class=\"mdt\"><table><thead><tr>" + cells(ln).map((c) => `<th>${c}</th>`).join("") + "</tr></thead><tbody>";
        i += 2;
        while (i < lines.length && isRow(lines[i])) { out += "<tr>" + cells(lines[i]).map((c) => `<td>${c}</td>`).join("") + "</tr>"; i++; }
        out += "</tbody></table></div>";
        continue;
      }
      if ((m = ln.match(/^\s*(?:[-•*]|·)\s+(.*)$/))) { if (list !== "ul") { close(); out += "<ul>"; list = "ul"; } out += `<li>${inline(m[1])}</li>`; }
      else if ((m = ln.match(/^\s*\d+[.)]\s+(.*)$/))) { if (list !== "ol") { close(); out += "<ol>"; list = "ol"; } out += `<li>${inline(m[1])}</li>`; }
      else if ((m = ln.match(/^\s*#{1,4}\s+(.*)$/))) { close(); out += `<p class="mdh">${inline(m[1])}</p>`; }
      else { close(); out += ln.trim() ? `<p>${inline(ln)}</p>` : ""; }
      i++;
    }
    close();
    return out.replace(/\u0000(\d+)\u0000/g, (m, k) => maths[Number(k)] || "");
  }
  function plain(text) { return String(text || "").replace(SEG, (m, a, b, c, d) => (a ?? b ?? c ?? d)); }
  function graphable(text) {
    const t = plain(text).replace(/\\cdot/g, "*").replace(/[{}\\]/g, "");
    const m = t.match(/\b(?:y|f\s*\(\s*x\s*\))\s*=\s*([0-9x+\-*/^().,²³√ ]*x[0-9x+\-*/^().,²³√ ]*)/);
    return m && m[1].trim().length >= 2 ? "y = " + m[1].trim().replace(/[.,]$/, "") : "";
  }
  window.JMD = { md, esc, plain, graphable, hasMath: (t) => { SEG.lastIndex = 0; return SEG.test(String(t || "")); } };
})();
