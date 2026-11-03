// Ephemeris of the local system. Positions propagate from published osculating
// elements (JPL SBDB for small bodies, JPL DE421 for planets) on two-body
// Keplerian orbits about the Sun. Distances are true to scale in astronomical
// units; body sizes are enlarged so they stay visible.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const K = 0.01720209895; // Gaussian gravitational constant, rad/day
const DEG = Math.PI / 180;
const RES = {
  any: "All resources", water: "Water", iron: "Iron", nickel: "Nickel",
  cobalt: "Cobalt", pgm: "Platinum-group metals", carbon: "Carbon",
};
const RES_ORDER = ["any", "water", "iron", "nickel", "cobalt", "pgm", "carbon"];
const GROUP_COLOR = {
  carbonaceous: [0.40, 0.31, 0.23], primitive: [0.36, 0.24, 0.19], stony: [0.52, 0.47, 0.40],
  metallic: [0.42, 0.50, 0.58], enstatite: [0.62, 0.59, 0.53], basaltic: [0.47, 0.42, 0.37],
};
const GROUP_LABEL = {
  carbonaceous: "Carbonaceous", primitive: "Primitive", stony: "Stony",
  metallic: "Metallic", enstatite: "Enstatite", basaltic: "Basaltic",
};
const EMBER = new THREE.Color("#E08C35");
const PLANET_COLOR = {
  mercury: "#9C9182", venus: "#D9C9A6", earth: "#6F8FA8", mars: "#B3684A",
  jupiter: "#C9B08A", saturn: "#D8C79E", uranus: "#9CC3C6", neptune: "#6E86B5",
};
// Time rate as a log10 multiple of real time: 0 = real time, 7.5 = one year per second.
const RATE_MAX = Math.log10(365.25 * 86400);
const VIEWS = [["Solar cycle", "solar"], ["Planetary cycle", "planetary"], ["Static", "static"]];
// Direction of the Sun's motion about the galactic centre (galactic l = 90°, b = 0°), ecliptic J2000,
// in scene axes; speed about 230 km/s, which is 0.1328 AU per day.
const GAL_DIR = new THREE.Vector3(0.4941, 0.8623, 0.1110).normalize();
const GAL_AU_PER_DAY = 0.13284;
const TOP = 25;

const $ = (id) => document.getElementById(id);
const state = { resource: "any", neoOnly: false, playing: true, rateLog: 0, view: "planetary", jd: 0, selected: null, focus: null, hover: null };
const daysPerSecond = () => Math.pow(10, state.rateLog) / 86400;

// ---------- orbits ----------
function kepler(M, e) {
  let E = e < 0.8 ? M : Math.PI;
  for (let k = 0; k < 30; k++) {
    const d = (E - e * Math.sin(E) - M) / (1 - e * Math.cos(E));
    E -= d;
    if (Math.abs(d) < 1e-10) break;
  }
  return E;
}

// elements: [epoch, a, e, i, node, peri, M]; writes scene coords (x, y up, z) into out at offset
function propagate(el, jd, out, o) {
  const [epoch, a, e, i, om, w, ma] = el;
  const n = K / Math.pow(a, 1.5);
  let M = (ma * DEG + n * (jd - epoch)) % (2 * Math.PI);
  if (M < 0) M += 2 * Math.PI;
  const E = kepler(M, e);
  const xp = a * (Math.cos(E) - e), yp = a * Math.sqrt(1 - e * e) * Math.sin(E);
  orient(i, om, w, xp, yp, out, o);
}

function orient(i, om, w, xp, yp, out, o) {
  const ci = Math.cos(i * DEG), si = Math.sin(i * DEG);
  const cO = Math.cos(om * DEG), sO = Math.sin(om * DEG);
  const cw = Math.cos(w * DEG), sw = Math.sin(w * DEG);
  const X = (cO * cw - sO * sw * ci) * xp + (-cO * sw - sO * cw * ci) * yp;
  const Y = (sO * cw + cO * sw * ci) * xp + (-sO * sw + cO * cw * ci) * yp;
  const Z = (sw * si) * xp + (cw * si) * yp;
  out[o] = X; out[o + 1] = Z; out[o + 2] = -Y; // ecliptic -> scene (y up)
}

function ellipse(el, segments = 360) {
  const [, a, e, i, om, w] = el;
  const pts = new Float32Array((segments + 1) * 3);
  for (let s = 0; s <= segments; s++) {
    const E = (s / segments) * Math.PI * 2;
    orient(i, om, w, a * (Math.cos(E) - e), a * Math.sqrt(1 - e * e) * Math.sin(E), pts, s * 3);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pts, 3));
  return g;
}

// ---------- formatting ----------
function tonnes(t) {
  if (t >= 1e12) return `${(t / 1e12).toPrecision(3)} trillion t`;
  if (t >= 1e9) return `${(t / 1e9).toPrecision(3)} billion t`;
  if (t >= 1e6) return `${(t / 1e6).toPrecision(3)} million t`;
  if (t >= 1e3) return `${Math.round(t).toLocaleString("en-US")} t`;
  if (t >= 1) return `${t.toPrecision(3)} t`;
  return `${(t * 1000).toPrecision(2)} kg`;
}
const fmtDate = (jd) => {
  const d = new Date((jd - 2440587.5) * 864e5);
  if (!isFinite(d)) return "";
  return `${d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" })} ${d.toISOString().slice(11, 16)} UTC`;
};
function fmtRate(log) {
  const x = Math.pow(10, log);
  if (log < 0.02) return "Real time";
  const units = [[31557600, "yr"], [2629800, "mo"], [604800, "wk"], [86400, "d"], [3600, "h"], [60, "min"], [1, "s"]];
  for (const [sec, u] of units) if (x >= sec) return `${(x / sec).toPrecision(x / sec < 10 ? 2 : 3)} ${u} per second`;
  return "Real time";
}
const sig = (x, n = 4) => Number(x.toPrecision(n)).toLocaleString("en-US", { maximumFractionDigits: 6 });
function sci(x) {
  const e = Math.floor(Math.log10(Math.abs(x)));
  const m = x / Math.pow(10, e);
  const sup = String(e).split("").map((c) => "⁰¹²³⁴⁵⁶⁷⁸⁹⁻"["0123456789-".indexOf(c)]).join("");
  return `${m.toFixed(3)} × 10${sup}`;
}
const nowJD = () => Date.now() / 864e5 + 2440587.5;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function splitName(full) {
  const m = full.match(/^(\S+)\s+(.*?)\s*(\((.+)\))?$/);
  if (!m) return { title: full, desig: "" };
  const [, num, rest, , prov] = m;
  if (rest && !/^\d/.test(rest)) return { title: rest, desig: [num, prov].filter(Boolean).join(", ") };
  return { title: prov || rest || num, desig: num };
}
function resourceTonnes(b, r) { return r === "any" ? Object.values(b.t).reduce((x, y) => x + y, 0) : b.t[r]; }

// ---------- scene ----------
const canvas = $("field");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setClearColor(0x120f0a, 1);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
// Everything heliocentric lives in `world`; in the solar cycle view the whole frame travels with the Sun.
const world = new THREE.Group();
scene.add(world);
const camera = new THREE.PerspectiveCamera(42, 1, 0.001, 2000);
camera.position.set(0, 2.6, 4.2);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.07;
controls.minDistance = 0.05;
controls.maxDistance = 120;
controls.zoomSpeed = 0.9;

scene.add(new THREE.AmbientLight(0xf2e8d7, 0.08));
const sunLight = new THREE.PointLight(0xfff1dc, 2.2, 0, 0);
scene.add(sunLight);

// sun: a disc plus a soft corona, both additive and camera-facing
function glowMaterial(inner, outer, power) {
  return new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    uniforms: { inner: { value: new THREE.Color(inner) }, outer: { value: new THREE.Color(outer) }, power: { value: power } },
    vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
    fragmentShader: `varying vec2 vUv; uniform vec3 inner; uniform vec3 outer; uniform float power;
      void main(){ float d = length(vUv - 0.5) * 2.0; float a = pow(clamp(1.0 - d, 0.0, 1.0), power);
        gl_FragColor = vec4(mix(outer, inner, a), a); }`,
  });
}
const sun = new THREE.Group();
const corona = new THREE.Sprite(); corona.material = glowMaterial("#FFE7C2", "#C57420", 2.6); corona.scale.setScalar(0.9);
const core = new THREE.Sprite(); core.material = glowMaterial("#FFF6E8", "#F2C48A", 7.0); core.scale.setScalar(0.16);
sun.add(corona, core);
world.add(sun);

// ecliptic reference: faint rings at 1, 2, 3, 5, 10, 20, 30 AU
const ringMat = new THREE.LineBasicMaterial({ color: 0xf2e8d7, transparent: true, opacity: 0.035 });
for (const r of [1, 2, 3, 5, 10, 20, 30]) {
  const pts = [];
  for (let s = 0; s <= 256; s++) { const t = (s / 256) * Math.PI * 2; pts.push(new THREE.Vector3(Math.cos(t) * r, 0, Math.sin(t) * r)); }
  world.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), ringMat));
}

// ---------- data-dependent scene parts ----------
let data, bodies, planets = [], moons = [], points, pointPos, pointSize, pointColor, orbitLines = new THREE.Group(), selOrbit = null;
world.add(orbitLines);

const pointMat = new THREE.ShaderMaterial({
  transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  uniforms: { scale: { value: 1 } },
  vertexShader: `attribute float size; attribute vec3 color; varying vec3 vColor; varying float vEmber; uniform float scale;
    void main(){ vColor = color; vEmber = step(1.5, size);
      vec4 mv = modelViewMatrix * vec4(position, 1.0);
      gl_PointSize = clamp(size * scale / -mv.z, size * 1.2, mix(size * 4.0, size * 9.0, vEmber));
      gl_Position = projectionMatrix * mv; }`,
  fragmentShader: `varying vec3 vColor; varying float vEmber;
    void main(){ vec2 c = gl_PointCoord - 0.5; float d = length(c) * 2.0; if (d > 1.0) discard;
      float core = smoothstep(1.0, 0.0, d); float a = mix(pow(core, 2.2) * 0.85, pow(core, 1.3), vEmber);
      gl_FragColor = vec4(vColor * (0.55 + 0.9 * pow(core, 3.0)), a); }`,
});

function buildPlanets() {
  for (const p of data.planets) {
    const el = [p.epoch, p.a, p.e, p.i, p.om, p.w, p.ma];
    const r = Math.max(0.012, Math.cbrt(p.radius_km / 6371) * 0.018) * (p.a > 5 ? 3.2 : 1);
    const mesh = new THREE.Mesh(
      new THREE.SphereGeometry(r, 48, 32),
      new THREE.MeshStandardMaterial({ color: PLANET_COLOR[p.id], roughness: 0.9, metalness: 0 }),
    );
    if (p.id === "saturn") {
      const ring = new THREE.Mesh(new THREE.RingGeometry(r * 1.35, r * 2.25, 96),
        new THREE.MeshBasicMaterial({ color: 0xd8c79e, transparent: true, opacity: 0.35, side: THREE.DoubleSide }));
      ring.rotation.x = Math.PI / 2 - 0.47;
      mesh.add(ring);
    }
    world.add(mesh);
    const line = new THREE.Line(ellipse(el, 512),
      new THREE.LineBasicMaterial({ color: 0xf2e8d7, transparent: true, opacity: p.a > 5 ? 0.14 : 0.2 }));
    orbitLines.add(line);
    const sats = new THREE.Group();
    world.add(sats);
    const planet = { ...p, el, mesh, r, sats, line, label: makeLabel(p.name), kind: "planet", pos: new THREE.Vector3() };
    planets.push(planet);
  }
}

// Natural satellites from JPL Horizons, propagated about their planet. True directions and
// eccentricities; distances from the planet are compressed so each system stays legible.
function moonDisplayDist(planet, rKm) {
  const R = (planet.phys && planet.phys.radius_km) || planet.radius_km;
  return planet.r * (1.8 + 1.1 * Math.log2(Math.max(rKm / R, 1.2)));
}
function buildMoons() {
  const byId = Object.fromEntries(planets.map((p) => [p.id, p]));
  for (const m of data.moons || []) {
    const parent = byId[m.parent];
    if (!parent) continue;
    const Rm = (m.phys && m.phys.radius_km) || 0;
    const size = Math.max(0.0035, Math.min(parent.r * 0.42, Rm ? Math.cbrt(Rm / 6371) * 0.018 * (parent.a > 5 ? 2.2 : 1.4) : parent.r * 0.08));
    const mat = new THREE.MeshStandardMaterial({ color: 0xbdb3a3, roughness: 0.95, metalness: 0, transparent: true, opacity: 0 });
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(size, 32, 20), mat);
    // orbit line: true shape and orientation, radius compressed point by point
    const pts = new Float32Array(361 * 3), tmpv = new Float32Array(3), dir = new THREE.Vector3();
    for (let k = 0; k <= 360; k++) {
      const E = (k / 360) * Math.PI * 2;
      orient(m.i, m.om, m.w, m.a_km * (Math.cos(E) - m.e), m.a_km * Math.sqrt(1 - m.e * m.e) * Math.sin(E), tmpv, 0);
      dir.set(tmpv[0], tmpv[1], tmpv[2]);
      const d = moonDisplayDist(parent, dir.length());
      dir.normalize().multiplyScalar(d);
      pts.set([dir.x, dir.y, dir.z], k * 3);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pts, 3));
    const line = new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0xf2e8d7, transparent: true, opacity: 0 }));
    parent.sats.add(mesh, line);
    const label = makeLabel(m.name, "moon");
    moons.push({ ...m, parent, mesh, line, size, label, kind: "moon", local: new THREE.Vector3(), pos: new THREE.Vector3(), vis: 0 });
  }
}
function moonLocal(m, jd, out) {
  let M = (m.ma + m.n * (jd - m.epoch)) * DEG % (2 * Math.PI);
  if (M < 0) M += 2 * Math.PI;
  const E = kepler(M, m.e);
  const t = new Float32Array(3);
  orient(m.i, m.om, m.w, m.a_km * (Math.cos(E) - m.e), m.a_km * Math.sqrt(1 - m.e * m.e) * Math.sin(E), t, 0);
  out.set(t[0], t[1], t[2]);
  const km = out.length();
  out.normalize().multiplyScalar(moonDisplayDist(m.parent, km));
  return km;
}

function buildPoints() {
  const n = bodies.length;
  pointPos = new Float32Array(n * 3);
  pointSize = new Float32Array(n);
  pointColor = new Float32Array(n * 3);
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pointPos, 3).setUsage(THREE.DynamicDrawUsage));
  g.setAttribute("size", new THREE.BufferAttribute(pointSize, 1));
  g.setAttribute("color", new THREE.BufferAttribute(pointColor, 3));
  points = new THREE.Points(g, pointMat);
  points.frustumCulled = false;
  world.add(points);
}

// ---------- ranking view ----------
let ranked = [];
function applyRanking() {
  const key = state.resource;
  const pool = bodies.filter((b) => !state.neoOnly || b.neo);
  ranked = pool.slice().sort((a, b) => a.rk[key] - b.rk[key]);
  const top = new Set(ranked.slice(0, TOP));
  const pc = new THREE.Color();
  bodies.forEach((b, i) => {
    const visible = !state.neoOnly || b.neo;
    if (top.has(b)) { pc.copy(EMBER); pointSize[i] = 3.2; }
    else {
      const c = GROUP_COLOR[b.grp] || GROUP_COLOR.stony;
      const dim = visible ? 1 : 0.0;
      pc.setRGB(c[0] * dim, c[1] * dim, c[2] * dim);
      pointSize[i] = visible ? Math.min(1.2, 0.5 + Math.log10(1 + b.d) * 0.45) : 0;
    }
    pointColor[i * 3] = pc.r; pointColor[i * 3 + 1] = pc.g; pointColor[i * 3 + 2] = pc.b;
  });
  points.geometry.attributes.size.needsUpdate = true;
  points.geometry.attributes.color.needsUpdate = true;
  renderLedger();
}

function renderLedger() {
  const key = state.resource;
  const list = ranked.slice(0, 60);
  $("ranks").innerHTML = list.map((b, idx) => {
    const { title } = splitName(b.name);
    return `<li><button data-id="${esc(b.id)}" aria-current="${state.selected === b}">
      <span class="n">${idx + 1}</span><span class="nm">${esc(title)}</span><span class="v">${esc(tonnes(resourceTonnes(b, key)))}</span>
      <span class="sub">${esc(GROUP_LABEL[b.grp])}, ${b.dv.toFixed(1)} km/s to reach</span></button></li>`;
  }).join("");
  $("count").textContent = `${(state.neoOnly ? ranked.length : bodies.length).toLocaleString("en-US")} bodies in view. Ranked by ${RES[key].toLowerCase()}.`;
}

// ---------- labels ----------
function makeLabel(text, cls = "") {
  const el = document.createElement("div");
  el.className = `lbl ${cls}`;
  el.textContent = text;
  $("labels").appendChild(el);
  return el;
}
const v3 = new THREE.Vector3();
function placeLabel(el, x, y, z, dy = 10) {
  v3.set(x, y, z).add(world.position).project(camera);
  if (v3.z > 1 || Math.abs(v3.x) > 1.1 || Math.abs(v3.y) > 1.1) { el.style.display = "none"; return; }
  el.style.display = "block";
  const sx = (v3.x * 0.5 + 0.5) * innerWidth, sy = (-v3.y * 0.5 + 0.5) * innerHeight + dy;
  el.style.transform = `translate(${sx}px, ${sy}px) translate(-50%, 0)`;
}
const selLabel = makeLabel("", "sel");
selLabel.style.display = "none";

// ---------- selection ----------
function select(b, fly = true) {
  state.selected = b;
  if (selOrbit) { world.remove(selOrbit); selOrbit.geometry.dispose(); selOrbit = null; }
  setFocus(null);
  document.body.classList.toggle("has-sel", !!b);
  if (!b) { $("sheet").hidden = true; selLabel.style.display = "none"; renderLedger(); return; }
  selOrbit = new THREE.Line(ellipse(b.el, 720), new THREE.LineBasicMaterial({ color: 0xe08c35, transparent: true, opacity: 0.75 }));
  world.add(selOrbit);
  selLabel.textContent = splitName(b.name).title;
  renderSheet(b);
  renderLedger();
  if (fly) {
    const i = bodies.indexOf(b);
    const target = new THREE.Vector3(pointPos[i * 3], pointPos[i * 3 + 1], pointPos[i * 3 + 2]).add(world.position);
    flyTo(target, Math.max(0.6, Math.min(3, b.el[1] * 0.9)));
  }
}

// ---------- planets and moons ----------
function focusPos(f, out) { return out.copy(f.pos).add(world.position); }
function setFocus(f) {
  if (state.focus) state.focus.label.classList.remove("sel");
  state.focus = f;
  if (!f) return;
  f.label.classList.add("sel");
}
function selectWorld(f) {
  if (state.selected) select(null);
  setFocus(f);
  document.body.classList.add("has-sel");
  renderWorldSheet(f);
  const target = focusPos(f, new THREE.Vector3());
  const outer = f.kind === "planet" ? Math.max(0, ...moons.filter((m) => m.parent === f).map((m) => moonDisplayDist(f, m.a_km))) : 0;
  const dist = f.kind === "planet" ? Math.max(f.r * 7, outer * 2.4) : Math.max(f.size * 14, f.parent.r * 2.4);
  flyTo(target, dist);
}
function row(k, v) { return v == null || v === "" ? "" : `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`; }
function physRows(ph) {
  ph = ph || {};
  return [
    row("Mean radius", ph.radius_km != null ? `${sig(ph.radius_km, 5)} km` : null),
    row("Mass", ph.mass_kg != null ? `${sci(ph.mass_kg)} kg` : null),
    row("Bulk density", ph.density != null ? `${ph.density} g/cm³` : null),
    row("Surface gravity", ph.gravity != null ? `${ph.gravity} m/s²` : null),
    row("Escape velocity", ph.escape != null ? `${ph.escape} km/s` : null),
    row("Rotation period", ph.rotation_h != null ? (ph.rotation_h > 72 ? `${sig(ph.rotation_h / 24, 4)} days` : `${sig(ph.rotation_h, 5)} hours`) : null),
    row("Geometric albedo", ph.albedo != null ? String(ph.albedo) : null),
  ].join("");
}
const earthPos = new THREE.Vector3();
function renderWorldSheet(f) {
  const earth = planets.find((p) => p.id === "earth");
  let head, facts, src;
  if (f.kind === "planet") {
    const moonsOf = moons.filter((m) => m.parent === f).map((m) => m.name);
    const dSun = f.pos.length();
    const dEarth = earth && earth !== f ? f.pos.distanceTo(earth.pos) : null;
    head = `<h2>${esc(f.name)}</h2><p class="desig">Planet${moonsOf.length ? `, ${moonsOf.length} moon${moonsOf.length > 1 ? "s" : ""} shown` : ""}</p>`;
    facts = physRows(f.phys) +
      row("Orbit", `${f.a.toFixed(4)} AU, e ${f.e.toFixed(4)}, i ${f.i.toFixed(2)}°`) +
      row("Orbital period", `${sig(Math.pow(f.a, 1.5), 4)} years`) +
      `<dt>From the Sun now</dt><dd id="live-sun">${dSun.toFixed(4)} AU</dd>` +
      (dEarth != null ? `<dt>From Earth now</dt><dd id="live-earth">${dEarth.toFixed(4)} AU</dd>` : "") +
      (moonsOf.length ? row("Moons", moonsOf.join(", ")) : "");
    src = `Orbit from the JPL DE421 ephemeris at the collection epoch. Physical data from <a href="https://ssd.jpl.nasa.gov/horizons/app.html" target="_blank" rel="noopener noreferrer">JPL Horizons</a>.`;
  } else {
    const pr = f.period_d;
    head = `<h2>${esc(f.name)}</h2><p class="desig">Moon of ${esc(f.parent.name)}</p>`;
    facts = physRows(f.phys) +
      row("Orbit", `${sig(f.a_km, 6)} km from ${f.parent.name}, e ${f.e.toFixed(4)}, i ${f.i.toFixed(2)}° to the ecliptic`) +
      row("Orbital period", pr ? (pr < 2 ? `${sig(pr * 24, 4)} hours` : `${sig(pr, 4)} days`) : null) +
      `<dt>From ${esc(f.parent.name)} now</dt><dd id="live-parent">${Math.round(f.km).toLocaleString("en-US")} km</dd>`;
    src = `Orbit and physical data from <a href="https://ssd.jpl.nasa.gov/horizons/app.html" target="_blank" rel="noopener noreferrer">JPL Horizons</a>, osculating elements about ${esc(f.parent.name)} at the collection epoch. Moon distances are drawn compressed so each system reads; directions are true.`;
  }
  $("sheet-body").innerHTML = `${head}<dl class="facts">${facts}</dl><p class="src">${src}</p>`;
  $("sheet").hidden = false;
  $("sheet").scrollTop = 0;
}
function updateLiveSheet() {
  const f = state.focus;
  if (!f) return;
  if (f.kind === "planet") {
    const a = $("live-sun"), b = $("live-earth"), earth = planets.find((p) => p.id === "earth");
    if (a) a.textContent = `${f.pos.length().toFixed(4)} AU`;
    if (b && earth) b.textContent = `${f.pos.distanceTo(earth.pos).toFixed(4)} AU`;
  } else {
    const c = $("live-parent");
    if (c) c.textContent = `${Math.round(f.km).toLocaleString("en-US")} km`;
  }
}

let flight = null;
function flyTo(target, dist) {
  const dir = camera.position.clone().sub(controls.target).normalize();
  flight = {
    t0: performance.now(), dur: matchMedia("(prefers-reduced-motion: reduce)").matches ? 1 : 1400,
    fromT: controls.target.clone(), toT: target.clone(),
    fromP: camera.position.clone(), toP: target.clone().add(dir.multiplyScalar(dist)),
  };
}

function renderSheet(b) {
  const { title, desig } = splitName(b.name);
  const key = state.resource;
  const rank = b.rk[key];
  const mass = b.mass;
  const groups = data.groups[b.grp];
  const yieldRows = data.resources.map((r) => {
    const t = b.t[r], lo = groups[r][0] * mass / 1000, hi = groups[r][1] * mass / 1000;
    const L = (x) => Math.log10(Math.max(x, 1e-3));
    const span = L(hi) - L(lo) || 1, pad = span * 0.15;
    const min = L(lo) - pad, max = L(hi) + pad, pos = (x) => ((L(x) - min) / (max - min)) * 100;
    return `<div class="row"><span class="k">${RES[r]}</span><span class="t">${esc(tonnes(t))}</span>
      <span class="range" aria-hidden="true" data-l="${pos(lo)}" data-r="${100 - pos(hi)}" data-m="${pos(t)}"><i></i><b></b></span>
      <span class="rr">Range ${esc(tonnes(lo))} to ${esc(tonnes(hi))}</span></div>`;
  }).join("");
  const meas = b.meas || {};
  const refs = Object.entries(meas).map(([k, v]) => {
    const unit = v.units ? ` ${v.units}` : "";
    const label = { mass: "GM", density: "Density", diameter: "Diameter", rotation: "Rotation period" }[k] || k;
    return `<li><span>${esc(label)} ${esc(v.value)}${esc(unit)}</span><br>${esc(v.ref || "Reference not listed")}</li>`;
  }).join("");
  const imgs = b.img ? `<h3>Mission imagery, ${esc(b.img.mission)}</h3><div class="imgs">${b.img.images.map((im) =>
    `<a href="${esc(im.page)}" target="_blank" rel="noopener noreferrer" title="${esc(im.title)}"><img src="${esc(im.thumb)}" alt="${esc(im.title)}" loading="lazy" referrerpolicy="no-referrer" /></a>`).join("")}</div>` : "";
  const sbdb = `https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr=${encodeURIComponent(b.id)}`;
  $("sheet-body").innerHTML = `
    <h2>${esc(title)}</h2>
    <p class="desig">${esc(desig)}</p>
    <p class="rankline">Ranked ${rank.toLocaleString("en-US")} of ${bodies.length.toLocaleString("en-US")} for ${RES[key].toLowerCase()}</p>
    <dl class="facts">
      <dt>Composition</dt><dd>${esc(GROUP_LABEL[b.grp])}, from ${esc(b.basis)}</dd>
      <dt>Diameter</dt><dd>${b.d.toPrecision(3)} km${b.dm ? "" : ", estimated from brightness"}</dd>
      <dt>Orbit</dt><dd>${b.el[1].toFixed(3)} AU, e ${b.el[2].toFixed(3)}, i ${b.el[3].toFixed(1)}°</dd>
      <dt>Reach</dt><dd>${b.dv.toFixed(2)} km/s from Earth's orbit</dd>
      ${b.neo ? "<dt>Class</dt><dd>Near-Earth" + (b.pha ? ", potentially hazardous" : "") + "</dd>" : ""}
    </dl>
    <h3>Expected yield</h3>
    <div class="yield">${yieldRows}</div>
    <p class="note">Estimated from spectral class and meteorite analogs. Bars show the analog range, the mark shows the central estimate.</p>
    ${refs ? `<h3>Measured</h3><ul class="refs">${refs}</ul>` : ""}
    ${imgs}
    <p class="src"><a href="${sbdb}" target="_blank" rel="noopener noreferrer">Source record at JPL</a></p>`;
  for (const el of $("sheet-body").querySelectorAll(".range")) {
    el.firstChild.style.left = `${el.dataset.l}%`;
    el.firstChild.style.right = `${el.dataset.r}%`;
    el.lastChild.style.left = `calc(${el.dataset.m}% - 1px)`;
  }
  $("sheet").hidden = false;
  $("sheet").scrollTop = 0;
}

// ---------- picking ----------
function pickWorld(cx, cy, radius) {
  let best = null, bestD = Infinity;
  const w = innerWidth, h = innerHeight, c = new THREE.Vector3();
  const cands = planets.concat(moons.filter((m) => m.vis > 0.3));
  for (const f of cands) {
    focusPos(f, c);
    const dist = camera.position.distanceTo(c);
    c.project(camera);
    if (c.z > 1) continue;
    const pr = ((f.kind === "planet" ? f.r : f.size) / (dist * Math.tan((camera.fov * DEG) / 2))) * (h / 2);
    const dx = (c.x * 0.5 + 0.5) * w - cx, dy = (-c.y * 0.5 + 0.5) * h - cy;
    const d = Math.hypot(dx, dy);
    if (d < Math.max(radius, pr + 4) && d < bestD) { bestD = d; best = f; }
  }
  return best;
}
function pick(cx, cy, radius = 14) {
  let best = null, bestD = radius * radius;
  const w = innerWidth, h = innerHeight;
  for (let i = 0; i < bodies.length; i++) {
    if (pointSize[i] === 0) continue;
    v3.set(pointPos[i * 3], pointPos[i * 3 + 1], pointPos[i * 3 + 2]).add(world.position).project(camera);
    if (v3.z > 1) continue;
    const dx = (v3.x * 0.5 + 0.5) * w - cx, dy = (-v3.y * 0.5 + 0.5) * h - cy;
    const d = dx * dx + dy * dy - (pointSize[i] > 2 ? 60 : 0); // ranked bodies are easier to hit
    if (d < bestD) { bestD = d; best = bodies[i]; }
  }
  return best;
}

let down = null;
canvas.addEventListener("pointerdown", (e) => { down = { x: e.clientX, y: e.clientY }; });
canvas.addEventListener("pointerup", (e) => {
  if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) return;
  const r = e.pointerType === "touch" ? 26 : 14;
  const f = pickWorld(e.clientX, e.clientY, r);
  if (f) { selectWorld(f); return; }
  const b = pick(e.clientX, e.clientY, r);
  select(b || null, !!b);
});
let hoverQueued = false;
canvas.addEventListener("pointermove", (e) => {
  if (e.pointerType === "touch" || hoverQueued) return;
  hoverQueued = true;
  requestAnimationFrame(() => {
    hoverQueued = false;
    const tip = $("hover");
    const f = pickWorld(e.clientX, e.clientY, 10);
    const b = f ? null : pick(e.clientX, e.clientY);
    if (!b && !f) { tip.hidden = true; canvas.style.cursor = ""; return; }
    if (f) tip.innerHTML = `${esc(f.name)}<small>${f.kind === "planet" ? "Planet" : `Moon of ${esc(f.parent.name)}`}</small>`;
    else {
      const { title } = splitName(b.name);
      tip.innerHTML = `${esc(title)}<small>${esc(GROUP_LABEL[b.grp])}, rank ${b.rk[state.resource].toLocaleString("en-US")}</small>`;
    }
    tip.style.transform = `translate(${e.clientX + 14}px, ${e.clientY + 12}px)`;
    tip.hidden = false;
    canvas.style.cursor = "pointer";
  });
});

// ---------- controls ----------
function segmented(el, items, current, onPick) {
  el.innerHTML = items.map(([label, value]) =>
    `<button class="seg" role="radio" aria-checked="${value === current}" data-v="${value}">${label}</button>`).join("");
  el.addEventListener("click", (e) => {
    const btn = e.target.closest(".seg");
    if (!btn) return;
    el.querySelectorAll(".seg").forEach((s) => s.setAttribute("aria-checked", String(s === btn)));
    onPick(btn.dataset.v);
  });
}

function wireControls() {
  segmented($("resources"), RES_ORDER.map((k) => [RES[k], k]), state.resource, (v) => {
    state.resource = v; applyRanking(); if (state.selected) renderSheet(state.selected);
  });
  segmented($("views"), VIEWS, state.view, setView);
  const rate = $("rate");
  rate.max = String(RATE_MAX);
  rate.value = String(state.rateLog);
  const showRate = () => { $("rate-label").textContent = fmtRate(state.rateLog); };
  rate.addEventListener("input", () => { state.rateLog = Number(rate.value); showRate(); });
  showRate();
  $("play").addEventListener("click", () => {
    state.playing = !state.playing;
    syncPlay();
  });
  $("today").addEventListener("click", () => { state.jd = nowJD(); resetTrails(); });
  $("neo-only").addEventListener("change", (e) => { state.neoOnly = e.target.checked; applyRanking(); });
  $("ranks").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-id]");
    if (btn) select(bodies.find((b) => b.id === btn.dataset.id));
  });
  const closeAll = () => { select(null); setFocus(null); $("sheet").hidden = true; document.body.classList.remove("has-sel"); };
  $("sheet-close").addEventListener("click", closeAll);
  addEventListener("keydown", (e) => { if (e.key === "Escape") closeAll(); });
  const ledger = $("ledger");
  const mq = matchMedia("(max-width: 900px)");
  const setOpen = (open) => { ledger.dataset.open = String(open); $("ledger-toggle").setAttribute("aria-expanded", String(open)); };
  setOpen(!mq.matches);
  mq.addEventListener("change", (e) => setOpen(!e.matches));
  $("ledger-toggle").addEventListener("click", () => setOpen(ledger.dataset.open !== "true"));
}

function syncPlay() {
  const live = state.view === "static";
  $("play").disabled = live; $("rate").disabled = live;
  $("play").setAttribute("aria-pressed", String(state.playing));
  $("play").textContent = state.playing ? "Pause" : "Play";
  document.body.dataset.view = state.view;
}

// ---------- views ----------
// Static: the system as it stands at this moment, held to the wall clock.
// Planetary cycle: heliocentric motion at the chosen rate.
// Solar cycle: the same motion carried along the Sun's path about the galactic centre.
let galAnchor = 0;
const TRAIL = 2400;
const trails = [];
function buildTrails() {
  const objs = [{ color: new THREE.Color("#E08C35"), get: (o) => o.set(0, 0, 0) }]
    .concat(planets.map((p) => ({ color: new THREE.Color(PLANET_COLOR[p.id]), get: (o) => o.copy(p.pos) })));
  for (const t of objs) {
    const pos = new Float32Array(TRAIL * 3), col = new Float32Array(TRAIL * 3);
    for (let j = 0; j < TRAIL; j++) { const f = Math.pow(j / (TRAIL - 1), 1.5) * 0.85; col.set([t.color.r * f, t.color.g * f, t.color.b * f], j * 3); }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    const line = new THREE.Line(g, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false }));
    line.frustumCulled = false; line.visible = false;
    scene.add(line);
    trails.push({ ...t, pos, line, last: null });
  }
}
const tv = new THREE.Vector3();
function resetTrails() {
  for (const t of trails) {
    t.get(tv).add(world.position);
    for (let j = 0; j < TRAIL; j++) t.pos.set([tv.x, tv.y, tv.z], j * 3);
    t.line.geometry.attributes.position.needsUpdate = true;
    t.last = tv.clone();
  }
}
function stepTrails() {
  const minStep = camera.position.distanceTo(controls.target) * 0.002;
  for (const t of trails) {
    t.get(tv).add(world.position);
    if (t.last && t.last.distanceTo(tv) < minStep) continue;
    t.pos.copyWithin(0, 3);
    t.pos.set([tv.x, tv.y, tv.z], TRAIL * 3 - 3);
    t.line.geometry.attributes.position.needsUpdate = true;
    t.last = tv.clone();
  }
}
function setView(v) {
  const prev = world.position.clone();
  state.view = v;
  if (v === "static") { state.jd = nowJD(); state.playing = true; }
  if (v === "solar") { galAnchor = state.jd; resetTrails(); }
  else world.position.set(0, 0, 0);
  const shift = world.position.clone().sub(prev);
  camera.position.add(shift); controls.target.add(shift);
  for (const t of trails) t.line.visible = v === "solar";
  syncPlay();
}

// ---------- frame ----------
function resize() {
  const w = innerWidth, h = innerHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  pointMat.uniforms.scale.value = h * 0.35 * renderer.getPixelRatio();
}
addEventListener("resize", resize);

let last = performance.now();
const tmp = new Float32Array(3);
function frame(now) {
  const dt = Math.min(0.1, (now - last) / 1000);
  last = now;
  if (state.view === "static") state.jd = nowJD();
  else if (state.playing) state.jd += dt * daysPerSecond();
  const later = []; // labels are placed after the camera moves this frame
  const before = world.position.clone();
  const focusBefore = state.focus ? focusPos(state.focus, new THREE.Vector3()) : null;
  if (state.view === "solar") world.position.copy(GAL_DIR).multiplyScalar(GAL_AU_PER_DAY * (state.jd - galAnchor));
  for (let i = 0; i < bodies.length; i++) propagate(bodies[i].el, state.jd, pointPos, i * 3);
  points.geometry.attributes.position.needsUpdate = true;
  for (const p of planets) {
    propagate(p.el, state.jd, tmp, 0);
    p.pos.set(tmp[0], tmp[1], tmp[2]);
    p.mesh.position.copy(p.pos);
    p.sats.position.copy(p.pos);
    p.mesh.rotation.y += dt * 0.05;
    const [lx, ly, lz] = tmp;
    const pd = camera.position.distanceTo(v3.set(lx, ly, lz).add(world.position));
    const pr = (p.r / (pd * Math.tan((camera.fov * DEG) / 2))) * (innerHeight / 2);
    later.push(() => placeLabel(p.label, lx, ly, lz, Math.max(12, pr + 6)));
  }
  const cw = new THREE.Vector3();
  for (const m of moons) {
    m.km = moonLocal(m, state.jd, m.local);
    m.mesh.position.copy(m.local);
    m.pos.copy(m.parent.pos).add(m.local);
    const near = camera.position.distanceTo(cw.copy(m.parent.pos).add(world.position)) / m.parent.r;
    const vis = 1 - THREE.MathUtils.smoothstep(near, 60, 140);
    m.vis = vis;
    m.mesh.material.opacity = vis; m.line.material.opacity = vis * 0.22;
    m.mesh.visible = m.line.visible = vis > 0.01;
    if (near < 70 || m === state.focus) { const q = m.pos.clone(); later.push(() => placeLabel(m.label, q.x, q.y, q.z, 8)); }
    else m.label.style.display = "none";
  }
  // keep the camera with the moving frame and with a focused planet or moon
  if (state.focus && !flight) {
    const after = focusPos(state.focus, new THREE.Vector3()).sub(focusBefore);
    camera.position.add(after); controls.target.add(after);
  } else if (!flight) {
    const shift = world.position.clone().sub(before);
    camera.position.add(shift); controls.target.add(shift);
  }
  if (flight && state.focus) flight.toT.copy(focusPos(state.focus, new THREE.Vector3()));
  if (state.view === "solar") stepTrails();
  updateLiveSheet();
  if (state.selected) {
    const i = bodies.indexOf(state.selected);
    const [sx, sy, sz] = [pointPos[i * 3], pointPos[i * 3 + 1], pointPos[i * 3 + 2]];
    later.push(() => placeLabel(selLabel, sx, sy, sz, 12));
  }
  if (flight) {
    const k = Math.min(1, (now - flight.t0) / flight.dur), s = 1 - Math.pow(1 - k, 3);
    controls.target.lerpVectors(flight.fromT, flight.toT, s);
    camera.position.lerpVectors(flight.fromP, flight.toP, s);
    if (k >= 1) flight = null;
  }
  // corona keeps a steady apparent size as the camera pulls out
  const dist = camera.position.distanceTo(world.position);
  corona.scale.setScalar(Math.max(0.9, dist * 0.12));
  core.scale.setScalar(Math.max(0.16, dist * 0.022));
  $("date").textContent = fmtDate(state.jd);
  controls.update();
  camera.updateMatrixWorld();
  for (const f of later) f();
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}

// ---------- boot ----------
async function boot() {
  resize();
  try {
    const [sys, man] = await Promise.all([
      fetch("data/system.json").then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }),
      fetch("data/manifest.json").then((r) => (r.ok ? r.json() : null)).catch(() => null),
    ]);
    data = sys;
  } catch (err) {
    $("status").textContent = "The dataset did not load. Reload the page to try again.";
    return;
  }
  bodies = data.bodies;
  state.jd = nowJD();
  buildPlanets();
  buildMoons();
  buildPoints();
  buildTrails();
  wireControls();
  syncPlay();
  applyRanking();
  const gen = new Date(data.generated_at);
  $("provenance").innerHTML = `${bodies.length.toLocaleString("en-US")} bodies from the <a href="https://ssd.jpl.nasa.gov/tools/sbdb_query.html" target="_blank" rel="noopener noreferrer">JPL Small-Body Database</a>, collected ${gen.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" })}. Planets from JPL DE421. Moons and physical data from JPL Horizons. Imagery from the <a href="https://images.nasa.gov/" target="_blank" rel="noopener noreferrer">NASA Image and Video Library</a>.`;
  $("status").classList.add("done");
  requestAnimationFrame(frame);
}
boot();
