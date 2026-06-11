/* Sense 2 Companion dashboard — dependency-free SVG charts. */

const ZONE_COLORS = { calm: "var(--calm)", mild: "var(--mild)", moderate: "var(--moderate)", high: "var(--high)" };
const STAGE_COLORS = { deep: "#3b5bdb", light: "#4da3ff", rem: "#9775fa", wake: "#5c6a85" };

const qs = (id) => document.getElementById(id);
const fmtMin = (m) => `${Math.floor(m / 60)}h ${m % 60}m`;

function svgEl(tag, attrs) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}

function gauge(svg, score) {
  svg.innerHTML = "";
  const color = score >= 80 ? ZONE_COLORS.calm : score >= 60 ? "var(--accent)" : score >= 40 ? ZONE_COLORS.mild : ZONE_COLORS.high;
  const r = 50, c = 2 * Math.PI * r;
  svg.appendChild(svgEl("circle", { cx: 60, cy: 60, r, fill: "none", stroke: "#242f44", "stroke-width": 10 }));
  svg.appendChild(svgEl("circle", {
    cx: 60, cy: 60, r, fill: "none", stroke: color, "stroke-width": 10, "stroke-linecap": "round",
    "stroke-dasharray": `${(score / 100) * c} ${c}`, transform: "rotate(-90 60 60)",
  }));
  const text = svgEl("text", { x: 60, y: 68, "text-anchor": "middle", fill: "currentColor", "font-size": 28, "font-weight": 700 });
  text.textContent = score;
  svg.appendChild(text);
}

function zoneBar(el, parts, colors) {
  el.innerHTML = "";
  const total = Object.values(parts).reduce((a, b) => a + b, 0) || 1;
  for (const [name, value] of Object.entries(parts)) {
    const seg = document.createElement("div");
    seg.style.width = `${(value / total) * 100}%`;
    seg.style.background = colors[name] || "#444";
    seg.title = `${name}: ${value} min`;
    el.appendChild(seg);
  }
}

/* Intraday chart: HR line + stress area + activity bands. */
function intradayChart(svg, heart, stress, restingHr) {
  svg.innerHTML = "";
  const W = 960, H = 260, PAD = 30;
  const n = heart.length || 1;
  const x = (i) => PAD + (i / (n - 1)) * (W - 2 * PAD);
  const hrVals = heart.map((s) => s[1]);
  const hrMin = Math.min(...hrVals) - 5, hrMax = Math.max(...hrVals) + 5;
  const yHr = (v) => H - PAD - ((v - hrMin) / (hrMax - hrMin)) * (H - 2 * PAD);
  const yStress = (v) => H - PAD - (v / 100) * (H - 2 * PAD);

  // activity bands
  let bandStart = null;
  stress.forEach((s, i) => {
    const active = s[2];
    if (active && bandStart === null) bandStart = i;
    if ((!active || i === stress.length - 1) && bandStart !== null) {
      svg.appendChild(svgEl("rect", { x: x(bandStart), y: PAD, width: Math.max(x(i) - x(bandStart), 1), height: H - 2 * PAD, fill: "#5c6a85", opacity: 0.18 }));
      bandStart = null;
    }
  });

  // stress area
  let area = `M ${x(0)} ${yStress(0)}`;
  stress.forEach((s, i) => { area += ` L ${x(i)} ${yStress(s[2] ? 0 : s[1])}`; });
  area += ` L ${x(stress.length - 1)} ${yStress(0)} Z`;
  svg.appendChild(svgEl("path", { d: area, fill: "var(--moderate)", opacity: 0.35 }));

  // resting HR reference line
  if (restingHr) {
    svg.appendChild(svgEl("line", { x1: PAD, x2: W - PAD, y1: yHr(restingHr), y2: yHr(restingHr), stroke: "#3ecf8e", "stroke-dasharray": "4 4", opacity: 0.6 }));
  }

  // HR line
  let line = "";
  heart.forEach((s, i) => { line += `${i ? "L" : "M"} ${x(i)} ${yHr(s[1])} `; });
  svg.appendChild(svgEl("path", { d: line, fill: "none", stroke: "var(--accent)", "stroke-width": 1.5 }));

  // hour labels every 4h
  for (let h = 0; h <= 24; h += 4) {
    const i = Math.min(Math.round((h / 24) * (n - 1)), n - 1);
    const t = svgEl("text", { x: x(i), y: H - 8, "text-anchor": "middle", fill: "#8b96ab", "font-size": 11 });
    t.textContent = `${String(h).padStart(2, "0")}:00`;
    svg.appendChild(t);
  }
}

function sparkline(values, labels, color) {
  const W = 300, H = 80, PAD = 6;
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" });
  if (!values.length) return svg;
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const x = (i) => PAD + (i / Math.max(values.length - 1, 1)) * (W - 2 * PAD);
  const y = (v) => H - PAD - ((v - min) / span) * (H - 2 * PAD);
  let d = "";
  values.forEach((v, i) => { d += `${i ? "L" : "M"} ${x(i)} ${y(v)} `; });
  svg.appendChild(svgEl("path", { d, fill: "none", stroke: color, "stroke-width": 2 }));
  const last = svgEl("circle", { cx: x(values.length - 1), cy: y(values.at(-1)), r: 3, fill: color });
  last.appendChild(svgEl("title", {})).textContent = `${labels.at(-1)}: ${values.at(-1)}`;
  svg.appendChild(last);
  return svg;
}

async function load(dateStr) {
  const q = dateStr ? `?date=${dateStr}` : "";
  const [overview, intraday, trends] = await Promise.all([
    fetch(`/api/overview${q}`).then((r) => r.json()),
    fetch(`/api/intraday${q}`).then((r) => r.json()),
    fetch(`/api/trends${q ? q + "&" : "?"}days=30`).then((r) => r.json()),
  ]);

  qs("datePicker").value = overview.date;
  qs("who").textContent = overview.profile.name || "";

  // health banner
  const banner = qs("alertBanner");
  banner.className = "banner " + (overview.health.level === "ok" ? "hidden" : overview.health.level);
  if (overview.health.level !== "ok") {
    banner.innerHTML = `<b>${overview.health.level.toUpperCase()}</b> — ${overview.health.summary}<br>` +
      overview.health.signals.map((s) => `• ${s.message}`).join("<br>");
  }

  // readiness
  gauge(qs("readinessGauge"), overview.readiness.score);
  qs("readinessLabel").textContent = overview.readiness.label;
  qs("readinessRec").textContent = overview.readiness.recommendation;
  qs("readinessParts").innerHTML =
    `<div>HRV<b>${overview.readiness.hrv_score}</b></div>` +
    `<div>Rest HR<b>${overview.readiness.rhr_score}</b></div>` +
    `<div>Sleep<b>${overview.readiness.sleep_score}</b></div>`;

  // stress
  qs("stressAvg").textContent = overview.stress.daily_avg;
  qs("stressPeak").textContent = overview.stress.peak;
  zoneBar(qs("stressZones"), overview.stress.zone_minutes, ZONE_COLORS);
  qs("stressEpisodes").innerHTML = overview.stress.episodes.length
    ? "<p class='muted'>Stress episodes:</p>" + overview.stress.episodes
        .map((e) => `<div class="episode">⚡ ${e.start}–${e.end} · avg ${e.avg}, peak ${e.peak}</div>`).join("")
    : "<p class='muted'>No sustained stress episodes detected.</p>";

  // vitals
  const v = overview;
  qs("vitalsTable").innerHTML = [
    ["Resting HR", v.resting_hr ? `${v.resting_hr} bpm` : "–"],
    ["HRV (RMSSD)", v.hrv ? `${v.hrv.rmssd} ms` : "–"],
    ["Breathing rate", v.breathing_rate ? `${v.breathing_rate.rate} br/min` : "–"],
    ["SpO₂ avg", v.spo2 ? `${v.spo2.avg}%` : "–"],
    ["Skin temp (rel.)", v.skin_temp ? `${v.skin_temp.nightly_relative > 0 ? "+" : ""}${v.skin_temp.nightly_relative}°C` : "–"],
  ].map(([k, val]) => `<tr><td>${k}</td><td>${val}</td></tr>`).join("");

  // sleep
  if (v.sleep) {
    qs("sleepDuration").textContent = fmtMin(v.sleep.minutes_asleep);
    qs("sleepEff").textContent = `${v.sleep.efficiency}%`;
    zoneBar(qs("sleepStages"), v.sleep.stages, STAGE_COLORS);
    qs("sleepStageLegend").textContent = Object.entries(v.sleep.stages)
      .map(([k, m]) => `${k} ${fmtMin(m)}`).join(" · ");
  }

  // intraday + trends
  intradayChart(qs("intradayChart"), intraday.heart, intraday.stress, intraday.resting_hr);

  const grid = qs("trendGrid");
  grid.innerHTML = "";
  const series = [
    ["Resting HR (bpm)", trends.resting_hr.map((d) => d.resting_hr), trends.resting_hr.map((d) => d.date), "var(--accent)"],
    ["HRV RMSSD (ms)", trends.hrv.map((d) => d.rmssd), trends.hrv.map((d) => d.date), "var(--calm)"],
    ["Breathing rate", trends.breathing_rate.map((d) => d.rate), trends.breathing_rate.map((d) => d.date), "var(--mild)"],
    ["Skin temp deviation (°C)", trends.skin_temp.map((d) => d.nightly_relative), trends.skin_temp.map((d) => d.date), "var(--high)"],
    ["Sleep (min)", trends.sleep.map((d) => d.minutes_asleep), trends.sleep.map((d) => d.date), "#9775fa"],
  ];
  for (const [title, values, labels, color] of series) {
    const fig = document.createElement("figure");
    const cap = document.createElement("figcaption");
    cap.textContent = title;
    fig.appendChild(cap);
    fig.appendChild(sparkline(values, labels, color));
    grid.appendChild(fig);
  }
}

qs("datePicker").addEventListener("change", (e) => load(e.target.value));
load();
