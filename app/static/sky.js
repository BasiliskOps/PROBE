// The live solar system: real planet positions today, and a probe's real trajectory.
// Distances are drawn on a square-root scale so Mercury and Neptune fit one view.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const COLORS = {
  mercury: 0xb3a79a, venus: 0xe8c27a, earth: 0x5b93e0, mars: 0xc4553b,
  jupiter: 0xd9a46c, saturn: 0xe3cf8f, uranus: 0x8fd3d8, neptune: 0x7c9be6,
};
const GOLD = 0xe2b04a;
const scale = ([x, y, z]) => {
  const r = Math.hypot(x, y, z) || 1;
  const k = (Math.sqrt(r) * 4) / r;
  return new THREE.Vector3(x * k, z * k, -y * k); // ecliptic plane is the scene floor
};

export async function mountSky(el, opts = {}) {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, el.clientWidth / el.clientHeight, 0.1, 500);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setSize(el.clientWidth, el.clientHeight);
  el.appendChild(renderer.domElement);
  const labels = document.createElement("div");
  labels.className = "sky-labels";
  el.appendChild(labels);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.autoRotate = !reduce && !opts.mission;
  controls.autoRotateSpeed = 0.25;
  controls.minDistance = 3;
  controls.maxDistance = 80;

  const sun = new THREE.Mesh(new THREE.SphereGeometry(0.35, 32, 16), new THREE.MeshBasicMaterial({ color: 0xffe9a8 }));
  scene.add(sun);
  const tags = [];
  const tag = (text, pos, cls = "") => {
    const d = document.createElement("span");
    d.textContent = text;
    d.className = cls;
    labels.appendChild(d);
    tags.push({ d, pos });
  };

  const t = opts.mission ? await (await fetch(`/api/v1/missions/${opts.mission}/track`)).json() : null;
  const sky = await (await fetch(t ? `/api/v1/sky?jd=${t.jd_now}` : "/api/v1/sky")).json();
  let outer = 0;
  for (const [name, p] of Object.entries(sky.planets)) {
    const pts = p.orbit.map(scale);
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color: COLORS[name], transparent: true, opacity: 0.28 }));
    scene.add(line);
    const pos = scale(p.position);
    outer = Math.max(outer, pos.length());
    const dot = new THREE.Mesh(new THREE.SphereGeometry(name === "jupiter" || name === "saturn" ? 0.22 : 0.14, 20, 12),
      new THREE.MeshBasicMaterial({ color: COLORS[name] }));
    dot.position.copy(pos);
    scene.add(dot);
    tag(name[0].toUpperCase() + name.slice(1), pos);
  }

  let probe = null;
  if (t && t.target) {
    const ast = 0xa9b7c9;
    scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(t.target.orbit.map(scale)),
      new THREE.LineBasicMaterial({ color: ast, transparent: true, opacity: 0.45 })));
    const rock = new THREE.Mesh(new THREE.DodecahedronGeometry(0.11), new THREE.MeshBasicMaterial({ color: ast }));
    rock.position.copy(scale(t.target.position));
    scene.add(rock);
    tag(t.target.name.replace(/\s*\(.*\)$/, ""), rock.position);
  }
  if (t) {
    const past = [], future = [];
    for (const [x, y, z, jd] of t.track) (jd <= t.jd_now ? past : future).push(scale([x, y, z]));
    if (past.length && future.length) future.unshift(past[past.length - 1]);
    if (past.length > 1) scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(past),
      new THREE.LineBasicMaterial({ color: GOLD })));
    if (future.length > 1) {
      const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(future),
        new THREE.LineDashedMaterial({ color: GOLD, dashSize: 0.18, gapSize: 0.12, transparent: true, opacity: 0.75 }));
      l.computeLineDistances();
      scene.add(l);
    }
    const here = scale(t.now.position_ecliptic_au);
    probe = new THREE.Mesh(new THREE.OctahedronGeometry(0.16), new THREE.MeshBasicMaterial({ color: 0xffffff }));
    probe.position.copy(here);
    scene.add(probe);
    tag(opts.name || "Probe", here, "probe");
    for (const e of t.events) if (e.title.includes("flyby") || e.title.includes("insertion")) {
      const m = new THREE.Mesh(new THREE.RingGeometry(0.12, 0.17, 24),
        new THREE.MeshBasicMaterial({ color: GOLD, side: THREE.DoubleSide }));
      m.position.copy(scale(e.position));
      m.rotation.x = -Math.PI / 2;
      scene.add(m);
    }
    const box = new THREE.Box3().setFromPoints(past.concat(future, [new THREE.Vector3()]));
    const center = box.getCenter(new THREE.Vector3());
    const radius = box.getSize(new THREE.Vector3()).length() / 2;
    const fit = radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2)) / Math.min(1, camera.aspect) * 0.75;
    controls.target.copy(center);
    camera.position.set(center.x, center.y + fit * 0.55, center.z + fit * 0.85);
  } else {
    const fit = outer / Math.min(1, camera.aspect * 0.9);
    camera.position.set(0, fit * 0.55, fit * 1.15);
  }
  const frame = () => {
    // On narrow screens the landing copy covers the lower half, so lift the scene into the upper half.
    if (opts.lift && el.clientWidth < 640) camera.setViewOffset(el.clientWidth, el.clientHeight, 0, el.clientHeight * 0.22, el.clientWidth, el.clientHeight);
    else camera.clearViewOffset();
  };
  frame();
  controls.update();

  const v = new THREE.Vector3();
  const resize = () => {
    camera.aspect = el.clientWidth / el.clientHeight;
    renderer.setSize(el.clientWidth, el.clientHeight);
    frame();
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(el);
  renderer.setAnimationLoop((time) => {
    controls.update();
    if (probe && !reduce) probe.rotation.y = time / 900;
    renderer.render(scene, camera);
    for (const { d, pos } of tags) {
      v.copy(pos).project(camera);
      const hidden = v.z > 1;
      d.style.display = hidden ? "none" : "";
      d.style.transform = `translate(${(v.x * 0.5 + 0.5) * el.clientWidth}px, ${(-v.y * 0.5 + 0.5) * el.clientHeight}px)`;
    }
  });
  return sky;
}
