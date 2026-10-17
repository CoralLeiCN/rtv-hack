import * as THREE from 'three';

export type AnimalSpecies = 'cat' | 'deer';
export type AnimalPose = 'standing' | 'walking' | 'feeding' | 'hissing' | 'greeting' | 'alert' | 'play';
export interface AnimalActor {
  root: THREE.Group;
  pose(kind: AnimalPose, time: number, dt?: number): void;
}

// Preserve the original animal geometry and articulated poses, while easing
// between them without allocating new vectors on each animation frame.
function poseSmoother(parts: THREE.Object3D[]) {
  const previous = new Float64Array(parts.length * 9);
  return {
    capture() {
      parts.forEach((part, i) => {
        const j = i * 9;
        previous[j] = part.position.x; previous[j + 1] = part.position.y; previous[j + 2] = part.position.z;
        previous[j + 3] = part.rotation.x; previous[j + 4] = part.rotation.y; previous[j + 5] = part.rotation.z;
        previous[j + 6] = part.scale.x; previous[j + 7] = part.scale.y; previous[j + 8] = part.scale.z;
      });
    },
    apply(dt: number) {
      const amount = 1 - Math.exp(-12 * Math.max(0, Math.min(dt, 0.05)));
      parts.forEach((part, i) => {
        const j = i * 9, mix = (n: number, target: number) => THREE.MathUtils.lerp(previous[j + n], target, amount);
        part.position.set(mix(0, part.position.x), mix(1, part.position.y), mix(2, part.position.z));
        part.rotation.set(mix(3, part.rotation.x), mix(4, part.rotation.y), mix(5, part.rotation.z));
        part.scale.set(mix(6, part.scale.x), mix(7, part.scale.y), mix(8, part.scale.z));
      });
    },
  };
}

export function createCat(secondary = false): AnimalActor {
  const root = new THREE.Group();
  const fur = new THREE.MeshStandardMaterial({ color: secondary ? '#68666f' : '#bd7f44', roughness: 1 });
  const cream = new THREE.MeshStandardMaterial({ color: secondary ? '#d1ccd0' : '#f0d5af', roughness: 1 });
  const dark = new THREE.MeshStandardMaterial({ color: '#25202b', roughness: 1 });
  const pink = new THREE.MeshStandardMaterial({ color: '#d78f9c', roughness: 1 });
  function blob(parent: THREE.Group, size: [number, number, number], position: [number, number, number], material = fur) {
    const mesh = new THREE.Mesh(new THREE.IcosahedronGeometry(1, 1), material);
    mesh.scale.set(...size);
    mesh.position.set(...position);
    parent.add(mesh);
    return mesh;
  }
  const torso = new THREE.Group();
  torso.position.y = 0.22;
  root.add(torso);
  const body = blob(torso, [0.2, 0.115, 0.085], [0, 0, 0]);
  blob(torso, [0.115, 0.065, 0.065], [-0.05, -0.055, 0], cream);
  const legs: THREE.Group[] = [];
  for (const x of [-0.13, 0.13]) for (const z of [-0.055, 0.055]) {
    const leg = new THREE.Group();
    leg.position.set(x, 0.22, z);
    const shaft = new THREE.Mesh(new THREE.CylinderGeometry(0.027, 0.018, 0.2, 5), fur);
    shaft.position.y = -0.1;
    leg.add(shaft);
    blob(leg, [0.045, 0.025, 0.032], [-0.015, -0.2, 0], cream);
    root.add(leg);
    legs.push(leg);
  }
  const head = new THREE.Group();
  head.position.set(-0.17, 0.29, 0);
  root.add(head);
  blob(head, [0.095, 0.083, 0.075], [-0.025, 0, 0]);
  blob(head, [0.045, 0.03, 0.055], [-0.095, -0.025, 0], cream);
  blob(head, [0.012, 0.012, 0.018], [-0.132, -0.01, 0], pink);
  const jaw = blob(head, [0.04, 0.014, 0.042], [-0.094, -0.047, 0], cream);
  const mouth = blob(head, [0.035, 0.017, 0.04], [-0.102, -0.037, 0], dark);
  mouth.visible = false;
  const ears: THREE.Group[] = [];
  for (const z of [-0.055, 0.055]) {
    const ear = new THREE.Group();
    ear.position.set(0.006, 0.054, z);
    const outer = new THREE.Mesh(new THREE.ConeGeometry(0.044, 0.11, 3), fur);
    outer.position.y = 0.035;
    outer.rotation.y = Math.PI / 6;
    ear.add(outer);
    const inner = new THREE.Mesh(new THREE.ConeGeometry(0.026, 0.07, 3), pink);
    inner.position.set(-0.013, 0.036, 0);
    inner.rotation.y = Math.PI / 6;
    ear.add(inner);
    head.add(ear);
    ears.push(ear);
    blob(head, [0.012, 0.02, 0.012], [-0.075, 0.019, z * 1.05], new THREE.MeshStandardMaterial({ color: '#cce775' }));
    blob(head, [0.006, 0.014, 0.005], [-0.083, 0.019, z * 1.14], dark);
    for (const offset of [-0.015, 0, 0.015]) {
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(-0.107, -0.022, z * 0.6), new THREE.Vector3(-0.135, -0.022 + offset, z * 2.5),
      ]), new THREE.LineBasicMaterial({ color: '#e5d7bc' }));
      head.add(line);
    }
  }
  const tail = new THREE.Group();
  tail.position.set(0.17, 0.27, 0);
  root.add(tail);
  const tailPoints = [new THREE.Vector3(), new THREE.Vector3(0.1, 0.08, 0), new THREE.Vector3(0.13, 0.2, 0), new THREE.Vector3(0.09, 0.29, 0)];
  tail.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(tailPoints), 12, 0.022, 5, false), fur));
  const cueCanvas = document.createElement('canvas');
  cueCanvas.width = 320; cueCanvas.height = 80;
  const context = cueCanvas.getContext('2d');
  if (context) {
    context.fillStyle = '#08080c'; context.fillRect(0, 0, 320, 80);
    context.strokeStyle = '#ff2fa8'; context.lineWidth = 5; context.strokeRect(3, 3, 314, 74);
    context.fillStyle = '#faf8f2'; context.font = 'bold 25px monospace'; context.textAlign = 'center';
    context.fillText('SCRIPTED HISS', 160, 49);
  }
  const cue = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(cueCanvas), depthTest: false }));
  cue.scale.set(0.45, 0.1125, 1); cue.position.set(-0.04, 0.64, 0); cue.visible = false;
  root.add(cue);
  root.visible = false;
  const smooth = poseSmoother([torso, body, ...legs, head, ...ears, jaw, tail]);
  return {
    root,
    pose(kind, time, dt = 1 / 60) {
      smooth.capture();
      const hissing = kind === 'hissing';
      const playful = kind === 'play';
      torso.position.y = hissing ? 0.265 : playful ? 0.19 : 0.22;
      body.scale.y = hissing ? 0.15 : 0.115;
      legs.forEach((leg, i) => {
        leg.rotation.z = kind === 'walking' ? Math.sin(time + (i === 0 || i === 3 ? 0 : Math.PI)) * 0.32 : 0;
        if (playful && i === 0) leg.rotation.z = -0.85 + Math.sin(time * 5) * 0.28;
      });
      head.rotation.z = kind === 'feeding' ? 0.9 : hissing ? -0.1 : playful ? 0.17 : 0;
      head.rotation.y = kind === 'alert' ? Math.sin(time * 1.6) * 0.18 : kind === 'greeting' ? Math.sin(time * 2) * 0.08 : 0;
      head.position.y = kind === 'feeding' ? 0.17 : hissing ? 0.27 : 0.29;
      ears.forEach((ear, i) => { ear.rotation.x = hissing ? (i === 0 ? -1 : 1) * 1.05 : (i === 0 ? -1 : 1) * 0.12; });
      mouth.visible = hissing;
      jaw.position.y = hissing ? -0.07 : -0.047;
      tail.rotation.z = kind === 'greeting' ? -0.3 : hissing ? 0.8 : 0.2;
      tail.rotation.x = hissing ? Math.sin(time * 9) * 0.12 : Math.sin(time * 2) * 0.25;
      cue.visible = hissing;
      smooth.apply(dt);
    },
  };
}

export function createDeer(secondary = false): AnimalActor {
  const deer = new THREE.Group();
  const fur = new THREE.MeshStandardMaterial({ color: secondary ? '#795b40' : '#92704b', roughness: 1 });
  const dark = new THREE.MeshStandardMaterial({ color: '#3d3025', roughness: 1 });
  const pale = new THREE.MeshStandardMaterial({ color: '#c4a57b', roughness: 1 });
  function ellipsoid(parent: THREE.Group, size: [number, number, number], position: [number, number, number], material = fur) {
    const mesh = new THREE.Mesh(new THREE.IcosahedronGeometry(1, 1), material);
    mesh.scale.set(...size);
    mesh.position.set(...position);
    parent.add(mesh);
    return mesh;
  }
  ellipsoid(deer, [0.3, 0.17, 0.12], [0, 0.45, 0]);
  ellipsoid(deer, [0.07, 0.055, 0.06], [0.29, 0.51, 0], pale);
  const legs: THREE.Group[] = [];
  for (const x of [-0.19, 0.19]) for (const z of [-0.07, 0.07]) {
    const leg = new THREE.Group();
    leg.position.set(x, 0.42, z);
    const shaft = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.015, 0.4, 5), fur);
    shaft.position.y = -0.2;
    leg.add(shaft);
    ellipsoid(leg, [0.035, 0.025, 0.028], [-0.007, -0.4, 0], dark);
    deer.add(leg);
    legs.push(leg);
  }
  const neck = new THREE.Group();
  neck.position.set(-0.22, 0.5, 0);
  deer.add(neck);
  ellipsoid(neck, [0.08, 0.2, 0.07], [-0.05, 0.13, 0]);
  ellipsoid(neck, [0.115, 0.07, 0.065], [-0.1, 0.31, 0]);
  ellipsoid(neck, [0.06, 0.045, 0.05], [-0.19, 0.28, 0], pale);
  ellipsoid(neck, [0.022, 0.025, 0.04], [-0.235, 0.28, 0], dark);
  for (const z of [-0.07, 0.07]) {
    const ear = ellipsoid(neck, [0.025, 0.085, 0.035], [-0.06, 0.38, z], pale);
    ear.rotation.x = Math.sign(z) * 0.5;
    ellipsoid(neck, [0.012, 0.012, 0.008], [-0.13, 0.33, z * 0.85], dark);
    const antler = new THREE.Group();
    antler.position.set(-0.04, 0.36, z * 0.7);
    antler.rotation.x = Math.sign(z) * 0.32;
    const bone = new THREE.MeshStandardMaterial({ color: '#d4be94', roughness: 1 });
    for (const [x, y, length, angle] of [[0.02, 0.09, 0.22, -0.22], [-0.025, 0.07, 0.1, 0.9], [-0.01, 0.14, 0.09, 0.75]] as const) {
      const branch = new THREE.Mesh(new THREE.CylinderGeometry(0.005, 0.009, length, 5), bone);
      branch.position.set(x, y, 0);
      branch.rotation.z = angle;
      antler.add(branch);
    }
    neck.add(antler);
  }
  deer.scale.setScalar(0.72);
  deer.position.set(2.8, 0, -0.15);
  deer.visible = false;
  const smooth = poseSmoother([...legs, neck]);
  return {
    root: deer,
    pose(kind, time, dt = 1 / 60) {
      smooth.capture();
      legs.forEach((leg, i) => { leg.rotation.z = kind === 'walking' ? Math.sin(time + (i === 0 || i === 3 ? 0 : Math.PI)) * 0.22 : 0; });
      neck.rotation.z = kind === 'feeding' ? 2.1 + Math.sin(time * 1.8) * 0.055 : Math.sin(time * 0.8) * 0.025;
      neck.rotation.y = kind === 'alert' ? Math.sin(time * 1.7) * 0.16 : 0;
      smooth.apply(dt);
    },
  };
}
