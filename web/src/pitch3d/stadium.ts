import * as THREE from "three";
import type { Roster } from "../types";
import { L, W, canvasTexture, seeded } from "./core";

/** The fictional league the synthetic matches are played in (see the League tab). */
const LEAGUE = "THE MERIDIAN LEAGUE";
const BRAND = "GAMEDAY INTELLIGENCE";

const STAND_GAP_SIDE = 9; // touchline to the front of the side stands
const STAND_GAP_END = 10; // goal line to the front of the end stands
const STAND_DEPTH = 24;
const STAND_RISE = 15;

/** A crowd in the dark: rows of small dots, mostly shadow, some in each club's colours. */
function crowdTexture(roster: Roster, seed: number) {
  const rnd = seeded(seed);
  const base = ["#14161a", "#1b1e23", "#23262c", "#2b2e35", "#3a3d44"];
  const home = roster.clubs.home.primary;
  const away = roster.clubs.away.primary;
  const t = canvasTexture(1024, 256, (g) => {
    g.fillStyle = "#08090b";
    g.fillRect(0, 0, 1024, 256);
    for (let row = 0; row < 32; row++) {
      for (let col = 0; col < 170; col++) {
        const r = rnd();
        if (r < 0.12) continue; // empty seat
        g.fillStyle = r < 0.2 ? home : r < 0.26 ? away : base[Math.floor(rnd() * base.length)];
        g.globalAlpha = r < 0.26 ? 0.55 : 1;
        g.fillRect(col * 6 + rnd() * 2, row * 8 + rnd() * 2, 4, 5);
      }
    }
    g.globalAlpha = 1;
  });
  t.wrapS = THREE.RepeatWrapping;
  t.wrapT = THREE.RepeatWrapping;
  return t;
}

/** LED board strip: the league, both clubs and our name, in white and club colours on black. */
function boardTexture(roster: Roster) {
  const items: [string, string][] = [
    [LEAGUE, "#cfd2cc"],
    [roster.clubs.home.name.toUpperCase(), roster.clubs.home.primary],
    [BRAND, "#cfd2cc"],
    [roster.clubs.away.name.toUpperCase(), roster.clubs.away.primary],
  ];
  const t = canvasTexture(2048, 64, (g) => {
    g.fillStyle = "#050506";
    g.fillRect(0, 0, 2048, 64);
    g.font = "700 40px 'Barlow Condensed', 'Arial Narrow', sans-serif";
    g.textBaseline = "middle";
    g.textAlign = "center";
    items.forEach(([text, color], i) => {
      g.fillStyle = color;
      g.fillText(text, 256 + i * 512, 34, 480);
      g.fillStyle = "#24262b";
      g.fillRect(i * 512, 8, 2, 48);
    });
  });
  t.wrapS = THREE.RepeatWrapping;
  return t;
}

/** One sloped stand: a crowd surface from the front edge up and back, a back wall and a roof lip. */
function stand(length: number, crowd: THREE.Texture, mat: THREE.Material): THREE.Group {
  const g = new THREE.Group();
  const slope = Math.hypot(STAND_DEPTH, STAND_RISE);
  const tex = crowd.clone();
  tex.repeat.set(length / 40, 2);
  tex.needsUpdate = true;
  const surface = new THREE.Mesh(new THREE.PlaneGeometry(length, slope), new THREE.MeshLambertMaterial({ map: tex }));
  // Built facing +Z (toward the pitch) and tilted back so it rises away from the pitch.
  surface.rotation.x = -Math.atan2(STAND_DEPTH, STAND_RISE);
  surface.position.set(0, 1.2 + STAND_RISE / 2, -STAND_DEPTH / 2);
  g.add(surface);
  const front = new THREE.Mesh(new THREE.BoxGeometry(length, 1.2, 0.4), mat);
  front.position.set(0, 0.6, 0);
  g.add(front);
  const back = new THREE.Mesh(new THREE.BoxGeometry(length, STAND_RISE + 6, 0.6), mat);
  back.position.set(0, (STAND_RISE + 6) / 2, -STAND_DEPTH - 0.3);
  g.add(back);
  const roof = new THREE.Mesh(new THREE.BoxGeometry(length, 0.5, 12), mat);
  roof.position.set(0, STAND_RISE + 6, -STAND_DEPTH + 6);
  g.add(roof);
  return g;
}

/** A floodlight tower: a mast and a bank of lamps angled down at the pitch. Flat lamps, no glow. */
function floodlight(x: number, z: number, poleMat: THREE.Material, lampMat: THREE.Material, frameMat: THREE.Material) {
  const g = new THREE.Group();
  const h = 38;
  const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.6, h, 8), poleMat);
  mast.position.y = h / 2;
  g.add(mast);
  const head = new THREE.Group();
  head.position.y = h;
  const frame = new THREE.Mesh(new THREE.BoxGeometry(8, 4.4, 0.5), frameMat);
  head.add(frame);
  for (let r = 0; r < 3; r++)
    for (let c = 0; c < 6; c++) {
      const lamp = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), lampMat);
      lamp.position.set(-3.1 + c * 1.24, -1.35 + r * 1.35, 0.26);
      head.add(lamp);
    }
  g.add(head);
  g.position.set(x, 0, z);
  // Face the centre spot and tip the lamp bank down toward it.
  head.lookAt(new THREE.Vector3(-x, -h * 0.9, -z).add(new THREE.Vector3(x, h, z)));
  return g;
}

/** Stands on all four sides, advertising boards round the pitch and four floodlight towers. */
export function buildStadium(roster: Roster): THREE.Group {
  const g = new THREE.Group();
  const seedOf = (s: string) => [...s].reduce((a, ch) => a * 31 + ch.charCodeAt(0), 7);
  const crowd = crowdTexture(roster, seedOf(roster.clubs.home.id + roster.clubs.away.id));
  const concrete = new THREE.MeshLambertMaterial({ color: 0x15171b });

  const sides: [number, number, number, number][] = [
    // length, x, z, rotation so the stand faces the pitch
    [L + 30, 0, W / 2 + STAND_GAP_SIDE, Math.PI],
    [L + 30, 0, -(W / 2 + STAND_GAP_SIDE), 0],
    [W + 10, L / 2 + STAND_GAP_END, 0, -Math.PI / 2],
    [W + 10, -(L / 2 + STAND_GAP_END), 0, Math.PI / 2],
  ];
  for (const [len, x, z, rot] of sides) {
    const s = stand(len, crowd, concrete);
    s.position.set(x, 0, z);
    s.rotation.y = rot;
    g.add(s);
  }
  crowd.dispose(); // each stand holds its own clone

  // Boards: a strip along each touchline and behind each goal, a few metres off the pitch.
  const boards = boardTexture(roster);
  const boardMat = (len: number) => {
    const t = boards.clone();
    t.repeat.set(len / 36, 1);
    t.needsUpdate = true;
    return new THREE.MeshBasicMaterial({ map: t });
  };
  const runs: [number, number, number, number][] = [
    [L + 8, 0, W / 2 + 4, Math.PI],
    [L + 8, 0, -(W / 2 + 4), 0],
    [W + 8, L / 2 + 4.5, 0, -Math.PI / 2],
    [W + 8, -(L / 2 + 4.5), 0, Math.PI / 2],
  ];
  for (const [len, x, z, rot] of runs) {
    const b = new THREE.Group();
    const face = new THREE.Mesh(new THREE.PlaneGeometry(len, 0.9), boardMat(len));
    face.position.set(0, 0.45, 0.06);
    b.add(face);
    const box = new THREE.Mesh(new THREE.BoxGeometry(len, 0.9, 0.1), concrete);
    box.position.y = 0.45;
    b.add(box);
    b.position.set(x, 0, z);
    b.rotation.y = rot;
    g.add(b);
  }
  boards.dispose();

  const pole = new THREE.MeshLambertMaterial({ color: 0x2a2d33 });
  const lamp = new THREE.MeshBasicMaterial({ color: 0xe9ebe4 });
  const frame = new THREE.MeshBasicMaterial({ color: 0x0b0c0e });
  for (const [x, z] of [
    [L / 2 + 16, W / 2 + 16],
    [-(L / 2 + 16), W / 2 + 16],
    [L / 2 + 16, -(W / 2 + 16)],
    [-(L / 2 + 16), -(W / 2 + 16)],
  ])
    g.add(floodlight(x, z, pole, lamp, frame));
  return g;
}
