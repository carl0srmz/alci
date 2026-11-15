const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function api(path, body, method) {
  const r = await fetch("/api" + path, body === undefined ? {} : {
    method: method || "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || "Error " + r.status);
  return j;
}

function ago(ts, now = Date.now() / 1000) {
  const s = Math.max(0, now - ts);
  if (s < 90) return "hace un momento";
  if (s < 5400) return `hace ${Math.round(s / 60)} min`;
  if (s < 129600) return `hace ${Math.round(s / 3600)} h`;
  return `hace ${Math.round(s / 86400)} días`;
}
const dayfmt = ts => new Date(ts * 1000).toLocaleString("es-MX", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

// Plain-language reading of each parameter: [word, tone] where tone is good|ok|bad
const words = {
  ph: v => v == null ? ["Sin dato", "ok"] : v < 6.5 ? ["Ácida", "bad"] : v <= 8.5 ? ["En su punto", "good"] : ["Alcalina", "bad"],
  ntu: v => v == null ? ["Sin dato", "ok"] : v <= 1 ? ["Cristalina", "good"] : v <= 5 ? ["Clara", "good"] : v <= 20 ? ["Turbia", "ok"] : ["Muy turbia", "bad"],
  temp: v => v == null ? ["Sin dato", "ok"] : v < 25 ? ["Fresca", "good"] : v < 30 ? ["Tibia", "ok"] : ["Caliente", "bad"],
};
const tier = s => s >= 85 ? ["Agua radiante", 2] : s >= 70 ? ["Agua en buen estado", 1] : s >= 50 ? ["Agua regular", 0] : s >= 30 ? ["Agua preocupante", -1] : ["Agua en mal estado", -2];

// Universal-indicator colours by pH 1..13
const PH_STOPS = ["#d7261e", "#e8561f", "#f08a24", "#f5b92a", "#f2dd32", "#b9d93a", "#5bb85b", "#2aa88a", "#2b9bb0", "#3a78c2", "#4a55b8", "#6a3fa8", "#7d2f96"];
const phStrip = ph => {
  const pos = ph == null ? null : Math.max(0, Math.min(14, ph)) / 14 * 100;
  return `<div class="phstrip" role="img" aria-label="Escala de pH${ph == null ? "" : ", lectura " + ph.toFixed(1)}" style="background:linear-gradient(90deg,${PH_STOPS.join(",")})">
    ${pos == null ? "" : `<i style="left:${pos}%"><b>${ph.toFixed(1)}</b></i>`}</div>
    <div class="phticks"><span>0 ácida</span><span>7 neutra</span><span>14 alcalina</span></div>`;
};

const lerp = (a, b, t) => a + (b - a) * t;
function dropColor(s) {
  // clear aqua -> teal -> slate -> dusty violet: murky water reads as dull violet, never as khaki
  const st = [[0, [107, 91, 123]], [35, [140, 122, 164]], [58, [120, 150, 180]], [80, [62, 184, 198]], [100, [36, 168, 214]]];
  for (let i = 1; i < st.length; i++) if (s <= st[i][0]) {
    const [x0, c0] = st[i - 1], [x1, c1] = st[i], t = (s - x0) / (x1 - x0);
    return `rgb(${c0.map((c, k) => Math.round(lerp(c, c1[k], t))).join(",")})`;
  }
  return "rgb(36,168,214)";
}

// Mascot "Gota": the water inside the drop rises to the score; face and colour follow the state.
let dropN = 0;
function drop(score, size = 220) {
  const m = tier(score)[1], c = dropColor(score), id = "dp" + (++dropN), INK = "#10283A";
  const PATH = "M100 8C100 8 28 96 28 152a72 72 0 0 0 144 0C172 96 100 8 100 8z";
  const y = 224 - 216 * Math.max(3, score) / 100;
  const eyes = m === 2
    ? `<path d="M64 150q14-16 28 0M108 150q14-16 28 0" fill="none" stroke="${INK}" stroke-width="5" stroke-linecap="round"/>`
    : `<circle cx="78" cy="152" r="9" fill="${INK}"/><circle cx="122" cy="152" r="9" fill="${INK}"/><circle cx="81" cy="148" r="3" fill="#fff"/><circle cx="125" cy="148" r="3" fill="#fff"/>`;
  const brows = m <= -1 ? `<path d="M62 142l26-9M138 142l-26-9" stroke="${INK}" stroke-width="4" stroke-linecap="round"/>` : "";
  const tear = m === -2 ? `<path class="tear" d="M70 168q-6 10 0 14q6-4 0-14z" fill="#fff"/>` : "";
  const cheeks = m >= 1 ? `<ellipse cx="58" cy="176" rx="11" ry="7" fill="#ff8fa3" opacity=".6"/><ellipse cx="142" cy="176" rx="11" ry="7" fill="#ff8fa3" opacity=".6"/>` : "";
  return `<svg class="gota" viewBox="0 0 200 240" width="${size}" height="${size * 1.2}" role="img" aria-label="Gota llena al ${score} %, ${tier(score)[0].toLowerCase()}">
    <style>.liq{animation:rise 1.6s cubic-bezier(.2,.8,.2,1) both}.tear{animation:tear 3s ease-in infinite}@keyframes rise{from{transform:translateY(216px)}}@keyframes tear{0%{transform:translateY(0);opacity:1}70%,100%{transform:translateY(26px);opacity:0}}@media(prefers-reduced-motion:reduce){.liq,.tear{animation:none}}</style>
    <defs><clipPath id="${id}"><path d="${PATH}"/></clipPath></defs>
    <ellipse cx="100" cy="230" rx="50" ry="6" fill="${INK}" opacity=".12"/>
    <path d="${PATH}" fill="#fff" fill-opacity=".62"/>
    <g clip-path="url(#${id})"><path class="liq" fill="${c}" d="M10 ${y}q22.5-10 45 0t45 0t45 0t45 0t45 0V250H10z"/></g>
    <path d="${PATH}" fill="none" stroke="${c}" stroke-width="4"/>
    <path d="M58 112c-10 16-14 30-14 42" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" opacity=".55"/>
    ${cheeks}${eyes}${brows}${tear}
    <path d="M80 ${m < 0 ? 188 : 182}Q100 ${184 + m * 12} 120 ${m < 0 ? 188 : 182}" fill="none" stroke="${INK}" stroke-width="5" stroke-linecap="round"/></svg>`;
}

// Tiny trend line for a reading row
function spark(rows, key, { min, max, w = 120, h = 34 }) {
  const pts = rows.filter(r => r[key] != null);
  if (pts.length < 2) return `<svg class="spark" viewBox="0 0 ${w} ${h}" aria-hidden="true"><path d="M2 ${h / 2}H${w - 2}" class="sl dash"/></svg>`;
  const t0 = pts[0].ts, t1 = pts[pts.length - 1].ts, l = pts[pts.length - 1];
  const x = t => 3 + (t - t0) / (t1 - t0 || 1) * (w - 6);
  const y = v => 4 + (1 - (Math.min(max, Math.max(min, v)) - min) / (max - min)) * (h - 8);
  const d = pts.map((r, i) => `${i ? "L" : "M"}${x(r.ts).toFixed(1)} ${y(r[key]).toFixed(1)}`).join("");
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" aria-hidden="true"><path d="${d}" class="sl"/><circle cx="${x(l.ts).toFixed(1)}" cy="${y(l[key]).toFixed(1)}" r="3" class="sd"/></svg>`;
}
const SPARK = { ph: { min: 4, max: 10 }, ntu: { min: 0, max: 50 }, temp: { min: 10, max: 35 } };

// Line chart with the ideal range shaded; rows from /api/history
function chart(rows, key, { min, max, ideal, unit = "", digits = 1 }) {
  const pts = rows.filter(r => r[key] != null);
  if (pts.length < 2) return `<p class="muted">Aún no hay suficientes mediciones para dibujar esta gráfica.</p>`;
  const W = 640, H = 170, P = { l: 38, r: 10, t: 10, b: 24 };
  const t0 = pts[0].ts, t1 = pts[pts.length - 1].ts;
  const x = t => P.l + (t - t0) / (t1 - t0 || 1) * (W - P.l - P.r);
  const y = v => P.t + (1 - (Math.min(max, Math.max(min, v)) - min) / (max - min)) * (H - P.t - P.b);
  const band = ideal ? `<rect x="${P.l}" y="${y(ideal[1])}" width="${W - P.l - P.r}" height="${y(ideal[0]) - y(ideal[1])}" class="band"/>` : "";
  const d = pts.map((r, i) => `${i ? "L" : "M"}${x(r.ts).toFixed(1)} ${y(r[key]).toFixed(1)}`).join("");
  const last = pts[pts.length - 1];
  const ticks = [min, (min + max) / 2, max].map(v => `<text x="${P.l - 6}" y="${y(v) + 4}" text-anchor="end">${+v.toFixed(0)}</text>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="Evolución, última lectura ${last[key].toFixed(digits)}${unit}">${band}${ticks}
    <path d="${d}" fill="none" class="line" stroke-width="2.5" stroke-linejoin="round"/>
    <circle cx="${x(last.ts)}" cy="${y(last[key])}" r="4.5" class="dot"/>
    <text x="${P.l}" y="${H - 6}">${new Date(t0 * 1000).toLocaleDateString("es-MX", { day: "numeric", month: "short" })}</text>
    <text x="${W - P.r}" y="${H - 6}" text-anchor="end">${new Date(t1 * 1000).toLocaleDateString("es-MX", { day: "numeric", month: "short" })}</text></svg>`;
}
const CHARTS = [
  ["ph", "Acidez (pH)", { min: 0, max: 14, ideal: [6.5, 8.5] }],
  ["ntu", "Turbidez (NTU)", { min: 0, max: 50, ideal: [0, 5], unit: " NTU" }],
  ["temp", "Temperatura (°C)", { min: 10, max: 40, ideal: [10, 25], unit: " °C" }],
  ["score", "Puntaje", { min: 0, max: 100, ideal: [70, 100], digits: 0 }],
];

const actionsList = a => (a || []).map(x => `<li><strong>${esc(x.what)}</strong>${x.product ? `<br>${esc(x.product)}` : ""}${x.dose ? `<br><span class="muted">${esc(x.dose)}</span>` : ""}</li>`).join("");
const sourcesList = s => (s || []).filter(u => /^https?:\/\//.test(u)).map(u => `<li><a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(new URL(u).hostname)}</a></li>`).join("");
