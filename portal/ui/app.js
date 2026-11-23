/* WBI Birds portal — static data contract + ECharts + MapLibre. */
const DATA = "data/";
const state = { manifest: null, landbase: null, fits: null, frontiers: null, map: null, mapTsa: null, layer: "managed" };
const $ = (sel) => document.querySelector(sel);
const fmt = (x, d = 0) => (x === null || x === undefined || Number.isNaN(x)) ? "—" : Number(x).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });
const pct = (x, d = 1) => `${Number(x).toFixed(d)}%`;
const Mha = (x) => `${(x / 1e6).toFixed(2)} Mha`;

async function getJSON(name) {
  const res = await fetch(DATA + name, { cache: "no-store" });
  if (!res.ok) throw new Error(`${name}: ${res.status}`);
  return res.json();
}

const charts = {};
function chart(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  if (charts[id]) charts[id].dispose();
  charts[id] = echarts.init(el, null, { renderer: "canvas" });
  return charts[id];
}
const PALETTE = { aspatial: "#b5651d", spatial: "#1f6f8b", forest: "#1f5c46", moss: "#8fb3a0", sand: "#e7e0cf", clay: "#b5651d" };
const baseText = { fontFamily: "IBM Plex Sans, system-ui, sans-serif", color: "#3d4d45" };

function renderOverview() {
  const lb = state.landbase.tsas;
  const sp = state.fits.species;
  const pts = state.frontiers.points;
  metrics("overview-metrics", [
    { k: "Timber supply areas", v: lb.length, s: lb.map(t => t.name).join(" · ") },
    { k: "Bird species", v: sp.length, s: "nine-species ensemble" },
    { k: "Tradeoff points", v: pts.length, s: state.frontiers.status === "pilot" ? "pilot: TSA41 / GCKI" : state.frontiers.status },
    { k: "Anticipation models", v: 2, s: "aspatial vs spatial-local" },
  ]);
  $("#overview-caveats").innerHTML = state.manifest.caveats.map(c => `<p class="note" style="margin:8px 0">${c}</p>`).join("");

  const ratio = chart("chart-thlb-ratio");
  ratio.setOption({
    grid: { left: 92, right: 28, top: 16, bottom: 28 },
    tooltip: { trigger: "axis", valueFormatter: v => `${Number(v).toFixed(3)}×` },
    xAxis: { type: "value", max: 2.0, min: 0, axisLabel: { ...baseText }, splitLine: { lineStyle: { color: "#eee9dd" } } },
    yAxis: { type: "category", data: lb.map(t => t.name), axisLabel: { ...baseText } },
    series: [{
      type: "bar", data: lb.map(t => t.ratio_weighted_tsr), barWidth: 16,
      itemStyle: { color: p => lb[p.dataIndex].ratio_weighted_tsr > 1.1 ? PALETTE.clay : PALETTE.forest, borderRadius: [0, 6, 6, 0] },
      label: { show: true, position: "right", formatter: p => `${Number(p.value).toFixed(2)}×`, color: "#3d4d45", fontSize: 11 },
      markLine: { silent: true, symbol: "none", lineStyle: { color: "#999", type: "dashed" }, data: [{ xAxis: 1.0 }] },
    }],
  });

  const impact = state.frontiers.impact;
  const mini = chart("chart-impact-mini");
  mini.setOption({
    grid: { left: 74, right: 28, top: 16, bottom: 30 },
    tooltip: { trigger: "axis", valueFormatter: v => `${Number(v).toFixed(1)}%` },
    legend: { data: ["aspatial", "spatial"], top: 0, textStyle: { ...baseText } },
    xAxis: { type: "value", axisLabel: { ...baseText, formatter: "{value}%" }, splitLine: { lineStyle: { color: "#eee9dd" } } },
    yAxis: { type: "category", data: impact.map(r => r.species.toUpperCase()), axisLabel: { ...baseText, fontSize: 10 } },
    series: [
      { name: "aspatial", type: "bar", data: impact.map(r => r.aspatial_pct), itemStyle: { color: PALETTE.aspatial }, barWidth: 7 },
      { name: "spatial", type: "bar", data: impact.map(r => r.spatial_pct), itemStyle: { color: PALETTE.spatial }, barWidth: 7 },
    ],
  });
}

function metrics(id, items) {
  document.getElementById(id).innerHTML = items.map(m => `
    <div class="metric"><div class="k">${m.k}</div><div class="v">${m.v}</div><div class="s">${m.s || ""}</div></div>`).join("");
}

function renderLandbase() {
  const lb = state.landbase.tsas;
  $("#landbase-table").innerHTML = `<table><thead><tr>
      <th>TSA</th><th class="num">Total (ha)</th><th class="num">Managed, full (ha)</th><th class="num">Managed, weighted (ha)</th>
      <th class="num">TSR THLB (ha)</th><th class="num">Ratio</th><th class="num">Threshold</th><th class="num">AAC (m³/yr)</th></tr></thead><tbody>
      ${lb.map(t => `<tr>
        <td><b>${t.name}</b> <span class="pill">${t.tsa}</span><div style="color:var(--muted);font-size:.74rem">${t.tsr_source}</div></td>
        <td class="num">${fmt(t.total_ha)}</td><td class="num">${fmt(t.managed_full_ha)}</td>
        <td class="num">${fmt(t.managed_weighted_ha)}</td><td class="num">${fmt(t.tsr_thlb_ha)}</td>
        <td class="num"><span class="pill ${t.ratio_weighted_tsr > 1.1 ? "warn" : ""}">${t.ratio_weighted_tsr.toFixed(3)}×</span></td>
        <td class="num">${t.threshold}</td><td class="num">${fmt(t.aac_m3_yr)}</td></tr>`).join("")}
      </tbody></table>`;

  const area = chart("chart-area");
  area.setOption({
    grid: { left: 70, right: 24, top: 30, bottom: 34 },
    tooltip: { trigger: "axis", valueFormatter: v => `${Number(v).toFixed(2)} Mha` },
    legend: { data: ["managed (weighted)", "unmanaged matrix"], top: 0, textStyle: baseText },
    xAxis: { type: "category", data: lb.map(t => t.name), axisLabel: { ...baseText, interval: 0, rotate: 20 } },
    yAxis: { type: "value", axisLabel: { ...baseText, formatter: v => `${v} Mha` }, splitLine: { lineStyle: { color: "#eee9dd" } } },
    series: [
      { name: "managed (weighted)", type: "bar", stack: "a", data: lb.map(t => +(t.managed_weighted_ha / 1e6).toFixed(2)), itemStyle: { color: PALETTE.forest } },
      { name: "unmanaged matrix", type: "bar", stack: "a", data: lb.map(t => +((t.total_ha - t.managed_weighted_ha) / 1e6).toFixed(2)), itemStyle: { color: "#cfd8cf" } },
    ],
  });

  const ratio = chart("chart-ratio");
  ratio.setOption({
    grid: { left: 60, right: 24, top: 30, bottom: 34 },
    tooltip: { trigger: "axis", valueFormatter: v => `${Number(v).toFixed(3)}×` },
    xAxis: { type: "category", data: lb.map(t => t.name), axisLabel: { ...baseText, interval: 0, rotate: 20 } },
    yAxis: { type: "value", min: 0, max: 2, axisLabel: baseText, splitLine: { lineStyle: { color: "#eee9dd" } } },
    series: [{
      type: "bar", barWidth: 34, data: lb.map(t => ({ value: t.ratio_weighted_tsr, itemStyle: { color: t.ratio_weighted_tsr > 1.1 ? PALETTE.clay : PALETTE.forest } })),
      label: { show: true, position: "top", formatter: p => `${p.value.toFixed(2)}×`, color: "#3d4d45", fontSize: 11 },
      markLine: { silent: true, symbol: "none", lineStyle: { color: "#999", type: "dashed" }, data: [{ yAxis: 1 }, { yAxis: 0.95 }] },
    }],
  });

  const sel = $("#age-tsa");
  sel.innerHTML = lb.map(t => `<option value="${t.tsa}">${t.name}</option>`).join("");
  sel.onchange = () => renderAge(sel.value);
  renderAge(lb[0].tsa);
}

function renderAge(tsa) {
  const t = state.landbase.tsas.find(x => x.tsa === tsa);
  const c = chart("chart-age");
  c.setOption({
    grid: { left: 60, right: 24, top: 34, bottom: 40 },
    tooltip: { trigger: "axis" },
    legend: { data: ["managed", "unmanaged"], top: 0, textStyle: baseText },
    xAxis: { type: "category", data: t.age_bins.map(b => `${b}`), name: "stand age (years)", nameLocation: "middle", nameGap: 26, axisLabel: baseText },
    yAxis: { type: "value", name: "polygons", axisLabel: baseText, splitLine: { lineStyle: { color: "#eee9dd" } } },
    series: [
      { name: "managed", type: "bar", data: t.age_managed, itemStyle: { color: PALETTE.forest } },
      { name: "unmanaged", type: "bar", data: t.age_unmanaged, itemStyle: { color: "#c9d3c9" } },
    ],
  });
}

function coefTable(block, title) {
  const rows = Object.entries(block).map(([k, v]) => `<tr><td class="mono">${k}</td><td class="num">${Number(v).toFixed(4)}</td></tr>`).join("");
  return `<table><thead><tr><th>Coefficient</th><th class="num">estimate</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function etaAspatial(c, age, soft, hard) {
  return c.intercept + c.softwood * Math.log1p(soft) + c.hardwood * Math.log1p(hard) + c.age * age;
}
function etaSpatial(c, age, soft, hard, edge, early, forest = 1.0) {
  return c.intercept + c.log1p_softwood * Math.log1p(soft) + c.log1p_hardwood * Math.log1p(hard)
    + c.age * age + c.pct_forest_1km * forest + c.edge_1km * edge + c.pct_early_500m * early;
}

function renderModels() {
  const fits = state.fits;
  const cov = fits.covariates || {};
  $("#cov-table").innerHTML = `<table><thead><tr><th>covariate</th><th class="num">mean</th><th class="num">p05</th><th class="num">p50</th><th class="num">p95</th></tr></thead><tbody>
    ${Object.entries(cov).map(([k, v]) => `<tr><td class="mono">${k}</td><td class="num">${v.mean}</td><td class="num">${v.p05}</td><td class="num">${v.p50}</td><td class="num">${v.p95}</td></tr>`).join("")}
  </tbody></table>`;

  const sel = $("#model-species");
  sel.innerHTML = fits.species.map(s => `<option value="${s.code}">${s.label} (${s.code})</option>`).join("");
  sel.onchange = () => renderSpecies(sel.value);
  renderSpecies(fits.species[0].code);

  $("#diag-table").innerHTML = `<table><thead><tr><th>species</th><th class="num">AIC aspatial</th><th class="num">AIC spatial</th><th class="num">ΔAIC</th><th class="num">dispersion a</th><th class="num">dispersion s</th></tr></thead><tbody>
    ${fits.species.map(s => {
      const da = s.aspatial.aic, ds = s.spatial.aic;
      return `<tr><td>${s.label} <span class="pill">${s.code}</span></td><td class="num">${fmt(da)}</td><td class="num">${fmt(ds)}</td>
        <td class="num">${da && ds ? fmt(ds - da) : "—"}</td><td class="num">${s.aspatial.dispersion?.toFixed(3) ?? "—"}</td><td class="num">${s.spatial.dispersion?.toFixed(3) ?? "—"}</td></tr>`;
    }).join("")}</tbody></table>`;
}

function renderSpecies(code) {
  const s = state.fits.species.find(x => x.code === code);
  const a = s.aspatial.coefficients, p = s.spatial.coefficients;
  $("#coef-aspatial").innerHTML = coefTable(a);
  $("#coef-spatial").innerHTML = coefTable(p);

  const ages = Array.from({ length: 301 }, (_, i) => i);
  const soft = 140, hard = 60;
  const capA = s.aspatial.eta_cap ?? 30, capS = s.spatial.eta_cap ?? 30;
  const curve = (eta, cap) => ages.map(x => Math.exp(Math.min(eta(x), cap)));

  const ca = chart("chart-age-response");
  ca.setOption({
    grid: { left: 58, right: 20, top: 30, bottom: 38 },
    tooltip: { trigger: "axis", valueFormatter: v => Number(v).toFixed(3) },
    legend: { data: ["aspatial", "spatial"], top: 0, textStyle: baseText },
    xAxis: { type: "category", data: ages, name: "stand age", nameLocation: "middle", nameGap: 26, axisLabel: { ...baseText, interval: 49 } },
    yAxis: { type: "value", name: "birds / unit", axisLabel: baseText, splitLine: { lineStyle: { color: "#eee9dd" } } },
    series: [
      { name: "aspatial", type: "line", showSymbol: false, data: curve(x => etaAspatial(a, x, soft, hard), capA), lineStyle: { color: PALETTE.aspatial, width: 2.5 } },
      { name: "spatial", type: "line", showSymbol: false, data: curve(x => etaSpatial(p, x, soft, hard, 0, 0), capS), lineStyle: { color: PALETTE.spatial, width: 2.5 } },
    ],
  });

  const ce = chart("chart-edge-response");
  ce.setOption({
    grid: { left: 58, right: 20, top: 30, bottom: 38 },
    tooltip: { trigger: "axis", valueFormatter: v => Number(v).toFixed(3) },
    legend: { data: ["spatial, no harvest nearby", "spatial, edge 0.35 / early 0.25"], top: 0, textStyle: { ...baseText, fontSize: 10 } },
    xAxis: { type: "category", data: ages, name: "stand age", nameLocation: "middle", nameGap: 26, axisLabel: { ...baseText, interval: 49 } },
    yAxis: { type: "value", axisLabel: baseText, splitLine: { lineStyle: { color: "#eee9dd" } } },
    series: [
      { name: "spatial, no harvest nearby", type: "line", showSymbol: false, data: curve(x => etaSpatial(p, x, soft, hard, 0, 0), capS), lineStyle: { color: PALETTE.spatial, width: 2.5 } },
      { name: "spatial, edge 0.35 / early 0.25", type: "line", showSymbol: false, data: curve(x => etaSpatial(p, x, soft, hard, 0.35, 0.25), capS), lineStyle: { color: PALETTE.clay, width: 2.5, type: "dashed" } },
    ],
  });
}

function renderTradeoffs() {
  const fr = state.frontiers;
  const pts = fr.points;
  const guildPts = fr.guild_frontier || [];
  const guildResponse = fr.guild_response || [];
  const guilds = [...new Set(guildPts.map(p => p.bird))].sort();
  $("#tradeoff-status").innerHTML = fr.status === "pilot"
    ? `<b>Pilot data.</b> These points are the TSA41 / GCKI pilot.`
    : `<b>Campaign data.</b> ${pts.length} points across ${[...new Set(pts.map(p => p.tsa))].length} TSAs and ${[...new Set(pts.map(p => p.bird))].length} species, two attainments, two models. `
      + (guildPts.length ? `Plus ${guilds.length} guild response curves for TSA41 (${guilds.map(g => g.replaceAll("_", " ")).join(", ")}).` : "");

  const tsas = [...new Set(pts.map(p => p.tsa))].sort();
  const speciesList = [...new Set(pts.map(p => p.bird))].sort();
  const birds = [...speciesList, ...guilds];
  const tsaSel = $("#front-tsa"), birdSel = $("#front-bird");
  tsaSel.innerHTML = tsas.map(t => `<option value="${t}">${t.replace("tsa", "TSA ")}</option>`).join("");
  birdSel.innerHTML = [
    `<optgroup label="Species">`,
    ...speciesList.map(b => `<option value="${b}">${b.toUpperCase()}</option>`),
    `</optgroup>`,
    `<optgroup label="Guild aggregates (sum of member species)">`,
    ...guilds.map(g => `<option value="${g}">GUILD · ${g.replaceAll("_", " ")}</option>`),
    `</optgroup>`,
  ].join("");
  if (tsas.includes("tsa41")) tsaSel.value = "tsa41";
  if (birds.includes("gockin")) birdSel.value = "gockin";

  function draw() {
    const bird = birdSel.value;
    const isGuild = guilds.includes(bird);
    if (isGuild) tsaSel.value = "tsa41";
    const tsa = tsaSel.value;
    tsaSel.disabled = isGuild;
    if (isGuild && guildResponse.length) {
      const card = document.querySelector("#chart-frontier").closest(".card");
      const h3 = card && card.querySelector("h3");
      if (h3) h3.textContent = "Guild response (TSA41)";
      const resp = guildResponse.filter(p => p.bird === bird && p.tsa === tsa)
        .sort((a, b) => a.harvest_M_m3_yr - b.harvest_M_m3_yr);
      const xs = resp.map(p => p.harvest_M_m3_yr);
      const ys = resp.flatMap(p => [p.aspatial_pct, p.spatial_pct]);
      const xmin = Math.max(0, Math.floor((Math.min(...xs) - 0.02) * 100) / 100);
      const xmax = Math.ceil((Math.max(...xs) + 0.02) * 100) / 100;
      const ymin = Math.max(0, Math.floor(Math.min(...ys) - 4));
      const ymax = Math.ceil(Math.max(...ys) + 4);
      const c = chart("chart-frontier");
      c.setOption({
        grid: { left: 110, right: 28, top: 34, bottom: 42 },
        tooltip: { trigger: "axis", valueFormatter: v => `${Number(v).toFixed(1)}%` },
        legend: { data: ["aspatial", "spatial"], top: 0, textStyle: baseText },
        xAxis: { type: "value", min: xmin, max: xmax, name: "harvest (M m³/yr)", nameLocation: "middle", nameGap: 28,
                 axisLabel: baseText, splitLine: { lineStyle: { color: "#eee9dd" } } },
        yAxis: { type: "value", min: ymin, max: ymax, name: "guild (% baseline)", axisLabel: baseText,
                 splitLine: { lineStyle: { color: "#eee9dd" } } },
        series: [
          { name: "aspatial", type: "line", data: resp.map(p => [p.harvest_M_m3_yr, p.aspatial_pct]),
            lineStyle: { color: PALETTE.aspatial, width: 2.2 }, itemStyle: { color: PALETTE.aspatial }, symbolSize: 7 },
          { name: "spatial", type: "line", data: resp.map(p => [p.harvest_M_m3_yr, p.spatial_pct]),
            lineStyle: { color: PALETTE.spatial, width: 2.2 }, itemStyle: { color: PALETTE.spatial }, symbolSize: 7 },
        ],
      });
      $("#frontier-table").innerHTML = `<table><thead><tr><th>harvest</th><th class="num">aspatial</th><th class="num">spatial</th></tr></thead><tbody>
        ${[...new Map(resp.map(p => [p.harvest_M_m3_yr.toFixed(2), p])).values()].map(p => `<tr><td>${p.harvest_M_m3_yr.toFixed(2)}</td><td class="num">${p.aspatial_pct.toFixed(1)}%</td><td class="num">${p.spatial_pct.toFixed(1)}%</td></tr>`).join("")}</tbody></table>`;
      return;
    }
    const sel = isGuild ? guildPts.filter(p => p.tsa === tsa && p.bird === bird)
                        : pts.filter(p => p.tsa === tsa && p.bird === bird);
    const modes = ["aspatial", "spatial"];
    const seeds = (fr.seeds || []).filter(p => p.tsa === tsa && p.bird === bird);
    const c = chart("chart-frontier");
    c.setOption({
      grid: { left: 62, right: 28, top: 34, bottom: 42 },
      tooltip: { trigger: "axis", valueFormatter: v => Number(v).toFixed(3) },
      legend: { data: [...modes, "seed checks"], top: 0, textStyle: baseText },
      xAxis: { type: "value", min: 0.7, max: 1.0, name: "constraint target (share of no-harvest)",
               nameLocation: "middle", nameGap: 28, axisLabel: { ...baseText, formatter: v => v.toFixed(2) } },
      yAxis: { type: "value", name: "harvest (M m³/yr)", axisLabel: baseText, splitLine: { lineStyle: { color: "#eee9dd" } } },
      series: [
        ...modes.map(m => ({
          name: m, type: "line",
          data: sel.filter(p => p.mode === m)
                   .sort((a, b) => a.target_attainment - b.target_attainment)
                   .map(p => [p.target_attainment, p.harvest_M_m3_yr]),
          lineStyle: { color: PALETTE[m], width: 2.5 }, itemStyle: { color: PALETTE[m] }, symbolSize: 8,
        })),
        { name: "seed checks", type: "scatter",
          data: seeds.map(p => [p.target_attainment, p.harvest_M_m3_yr]),
          itemStyle: { color: "#fff", borderColor: "#666", borderWidth: 1.4 }, symbolSize: 9 },
      ],
    });
    const rows = sel.filter(p => p.mode === "aspatial" || p.mode === "spatial")
      .sort((a, b) => a.target_attainment - b.target_attainment || a.mode.localeCompare(b.mode));
    const pair = {};
    rows.forEach(r => { const k = Number(r.target_attainment); pair[k] = pair[k] || {}; pair[k][r.mode] = r; });
    $("#frontier-table").innerHTML = `<table><thead><tr><th>target</th><th class="num">aspatial</th><th class="num">spatial</th><th class="num">delta</th></tr></thead><tbody>
      ${Object.keys(pair).map(Number).sort((a, b) => a - b).map(k => {
        const v = pair[k];
        if (!v.aspatial || !v.spatial) return "";
        const a = Number(v.aspatial.harvest_M_m3_yr), s = Number(v.spatial.harvest_M_m3_yr);
        const d = s ? 100 * (a - s) / s : NaN;
        return `<tr><td>${k.toFixed(2)}</td><td class="num">${a.toFixed(3)}</td><td class="num">${s.toFixed(3)}</td><td class="num">${d.toFixed(1)}%</td></tr>`;
      }).join("")}</tbody></table>`;
  }
  tsaSel.onchange = draw;
  birdSel.onchange = draw;

  const impact = fr.impact;
  const ci = chart("chart-impact");
  ci.setOption({
    grid: { left: 82, right: 30, top: 34, bottom: 34 },
    tooltip: { trigger: "axis", valueFormatter: v => `${Number(v).toFixed(1)}%` },
    legend: { data: ["aspatial", "spatial"], top: 0, textStyle: baseText },
    xAxis: { type: "value", axisLabel: { ...baseText, formatter: "{value}%" }, splitLine: { lineStyle: { color: "#eee9dd" } } },
    yAxis: { type: "category", data: impact.map(r => r.species.toUpperCase()), axisLabel: { ...baseText, fontSize: 10 } },
    series: [
      { name: "aspatial", type: "bar", data: impact.map(r => r.aspatial_pct), itemStyle: { color: PALETTE.aspatial }, barWidth: 7 },
      { name: "spatial", type: "bar", data: impact.map(r => r.spatial_pct), itemStyle: { color: PALETTE.spatial }, barWidth: 7 },
    ],
  });

  const flips = impact.filter(r => r.sign_flip).map(r => r.species.toUpperCase());
  $("#verdict").innerHTML = `
    <p class="note" style="margin:8px 0"><b>Rule:</b> ${fr.verdict.rule}</p>
    <p class="note" style="margin:8px 0"><b>Result:</b> ${fr.verdict.result}</p>
    <p class="note" style="margin:8px 0"><b>Sign flips under one identical schedule:</b> ${flips.length ? flips.join(", ") : "none"}.</p>
    <p class="note" style="margin:8px 0">At matched relative attainment the two models can disagree in magnitude and in sign. The spatial model prices edge and early-seral habitat loss on retained neighbouring forest; the aspatial model prices only the harvested stand.</p>
    <p class="note" style="margin:8px 0"><b>TSA41 guild responses:</b> mature conifer declines with harvest under both models (aspatial 95→85%, spatial 100→80%); mixedwood diverges (aspatial 97→92%, spatial 102→107%); early seral and cavity rise (aspatial 120→124% and 123→129%; spatial 99→108% and 105→130%). Only mature conifer shows a tradeoff in this range.</p>`;
  draw();
}

function renderMaps() {
  const lb = state.landbase.tsas;
  const sel = $("#map-tsa");
  sel.innerHTML = lb.map(t => `<option value="${t.tsa}">${t.name}</option>`).join("");
  sel.onchange = () => loadMap(sel.value);
  document.querySelectorAll("#map-layer button").forEach(b => b.onclick = () => {
    document.querySelectorAll("#map-layer button").forEach(x => x.classList.remove("active"));
    b.classList.add("active");
    state.layer = b.dataset.layer;
    paintLayer();
  });
  state.map = new maplibregl.Map({
    container: "map",
    style: {
      version: 8,
      sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OpenStreetMap contributors" } },
      layers: [{ id: "bg", type: "background", paint: { "background-color": "#eef1ea" } }, { id: "osm", type: "raster", source: "osm", paint: { "raster-opacity": 0.35 } }],
    },
    center: [-122.5, 55.5], zoom: 5,
  });
  state.map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  state.map.on("load", () => loadMap(lb[0].tsa));
  state.map.on("zoomend", () => { $("#map-count").textContent = `vector tiles · z${state.map.getZoom().toFixed(1)}`; });
}

async function loadMap(tsa) {
  const map = state.map;
  state.mapTsa = tsa;
  if (map.getLayer("blocks-fill")) map.removeLayer("blocks-fill");
  if (map.getSource("blocks")) map.removeSource("blocks");
  map.addSource("blocks", {
    type: "vector",
    tiles: [`${location.origin}/tiles/${tsa}/{z}/{x}/{y}.pbf`],
    minzoom: 5,
    maxzoom: 14,
  });
  map.addLayer({
    id: "blocks-fill", type: "fill", source: "blocks", "source-layer": "blocks",
    paint: { "fill-color": "#8fb3a0", "fill-opacity": 0.85, "fill-outline-color": "rgba(255,255,255,0.35)" },
  });
  if (!state.mapClickBound) {
    state.mapClickBound = true;
    map.on("click", "blocks-fill", (e) => {
      const p = e.features[0].properties;
      new maplibregl.Popup({ closeButton: false }).setLngLat(e.lngLat)
        .setHTML(`<b>Block ${p.b}</b><br>${Number(p.m) ? "managed" : "unmanaged"}<br>age ${p.a}<br>${Number(p.y) >= 0 ? `harvest ${p.y}` : "not scheduled"}`).addTo(map);
    });
    map.on("mouseenter", "blocks-fill", () => map.getCanvas().style.cursor = "pointer");
    map.on("mouseleave", "blocks-fill", () => map.getCanvas().style.cursor = "");
  }
  const bounds = (state.bounds && state.bounds[tsa]) ? state.bounds[tsa].bbox : null;
  state.lastBounds = bounds ? [[bounds[0], bounds[1]], [bounds[2], bounds[3]]] : null;
  if (state.lastBounds) map.fitBounds(state.lastBounds, { padding: 24, duration: 400 });
  paintLayer();
  $("#map-count").textContent = `vector tiles · z${map.getZoom().toFixed(1)}`;
}

function paintLayer() {
  const map = state.map;
  if (!map || !map.getLayer("blocks-fill")) return;
  if (state.layer === "managed") {
    map.setPaintProperty("blocks-fill", "fill-color", ["match", ["get", "m"], 1, "#14532d", "#dce5da"]);
    map.setPaintProperty("blocks-fill", "fill-opacity", 0.85);
    $("#map-legend").innerHTML = `<span><i style="background:${PALETTE.forest}"></i>managed (harvestable)</span><span><i style="background:#c7d2c6"></i>unmanaged matrix</span>`;
  } else {
    map.setPaintProperty("blocks-fill", "fill-color", [
      "case", ["<", ["get", "y"], 0], "#e3e6dd",
      ["interpolate", ["linear"], ["get", "y"], 0, "#e8d9b5", 40, "#d9a441", 80, "#c06a2a", 120, "#8f3d2a", 160, "#5c2432", 199, "#2d1b33"],
    ]);
    map.setPaintProperty("blocks-fill", "fill-opacity", 0.92);
    $("#map-legend").innerHTML = `<span><i style="background:#e3e6dd"></i>not scheduled</span><span><i style="background:#e8d9b5"></i>0–40</span><span><i style="background:#d9a441"></i>40–80</span><span><i style="background:#c06a2a"></i>80–120</span><span><i style="background:#8f3d2a"></i>120–160</span><span><i style="background:#2d1b33"></i>160–199</span>`;
  }
}

function wireNav() {
  document.querySelectorAll("#nav button").forEach(b => b.onclick = () => {
    document.querySelectorAll("#nav button").forEach(x => x.classList.remove("active"));
    b.classList.add("active");
    document.querySelectorAll("main section").forEach(s => s.classList.remove("active"));
    document.getElementById(`page-${b.dataset.page}`).classList.add("active");
    setTimeout(() => {
      Object.values(charts).forEach(c => c.resize());
      if (b.dataset.page === "maps" && state.map) {
        state.map.resize();
        if (state.lastBounds) state.map.fitBounds(state.lastBounds, { padding: 24, duration: 0 });
      }
    }, 80);
  });
  window.addEventListener("resize", () => Object.values(charts).forEach(c => c.resize()));
}

(async function boot() {
  try {
    const [manifest, landbase, fits, frontiers, bounds] = await Promise.all([
      getJSON("manifest.json"), getJSON("landbase.json"), getJSON("fits.json"), getJSON("frontiers.json"),
      getJSON("tsa_bounds.json").catch(() => ({})),
    ]);
    state.bounds = bounds;
    Object.assign(state, { manifest, landbase, fits, frontiers });
    $("#stat-tsas").textContent = manifest.tsas.length;
    $("#stat-species").textContent = manifest.species.length;
    $("#stat-generated").textContent = manifest.generated_at.slice(0, 10);
    $("#footer-generated").textContent = manifest.generated_at;
    $("#status-text").textContent = manifest.campaign_status;
    $("#status-badge").classList.toggle("is-warn", manifest.campaign_status.includes("in progress") || manifest.campaign_status.includes("pilot"));
    wireNav();
    renderOverview();
    renderLandbase();
    renderModels();
    renderTradeoffs();
    renderMaps();
  } catch (err) {
    console.error(err);
    $("#status-text").textContent = "data contract failed to load";
    $("#status-badge").classList.add("is-warn");
  }
})();
