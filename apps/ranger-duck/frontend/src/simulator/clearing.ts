import * as THREE from 'three';

/** Visual scene actors only. The duck and flat floor remain MuJoCo bodies. */
export function createClearing(scene: THREE.Scene) {
  const group = new THREE.Group();
  scene.add(group);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(16, 16), new THREE.MeshStandardMaterial({ color: '#202c20', roughness: 1 }));
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.005;
  ground.receiveShadow = true;
  group.add(ground);
  const patch = new THREE.Mesh(new THREE.CircleGeometry(1.48, 40), new THREE.MeshStandardMaterial({ color: '#34402a', roughness: 1 }));
  patch.rotation.x = -Math.PI / 2;
  patch.position.y = -0.002;
  group.add(patch);
  const zone = new THREE.Mesh(new THREE.RingGeometry(0.35, 0.365, 48), new THREE.MeshBasicMaterial({ color: '#2ff0e6', side: THREE.DoubleSide, transparent: true, opacity: 0.75 }));
  zone.rotation.x = -Math.PI / 2;
  zone.position.set(0.65, 0.004, -0.15);
  group.add(zone);
  const duckZone = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(-1.1, 0.005, 0.45), new THREE.Vector3(0.15, 0.005, 0.45),
    new THREE.Vector3(0.15, 0.005, -0.45), new THREE.Vector3(-1.1, 0.005, -0.45),
  ]), new THREE.LineBasicMaterial({ color: '#ffd23f', transparent: true, opacity: 0.45 }));
  group.add(duckZone);

  for (let i = 0; i < 13; i++) {
    const tree = new THREE.Group();
    const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.06, 0.85, 5), new THREE.MeshStandardMaterial({ color: '#3c3328' }));
    trunk.position.y = 0.4;
    tree.add(trunk);
    for (let layer = 0; layer < 3; layer++) {
      const crown = new THREE.Mesh(new THREE.ConeGeometry(0.32 - layer * 0.06, 0.65, 5), new THREE.MeshStandardMaterial({ color: layer % 2 ? '#263d2b' : '#1b3025', roughness: 1 }));
      crown.position.y = 0.65 + layer * 0.25;
      tree.add(crown);
    }
    tree.position.set((i - 6) * 0.53, 0, -1.8 - (i % 3) * 0.24);
    tree.rotation.y = i * 1.7;
    tree.scale.setScalar(0.85 + (i % 4) * 0.14);
    group.add(tree);
  }

  const deer = new THREE.Group();
  const fur = new THREE.MeshStandardMaterial({ color: '#92704b', roughness: 1 });
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
  group.add(deer);

  let encounter: { id: string; behavior: string; start: number; reached: boolean } | null = null;
  return {
    start(id: string, behavior: string, now: number) {
      encounter = { id, behavior, start: now, reached: false };
      deer.visible = true;
      deer.position.set(2.8, 0, -0.15);
      neck.rotation.z = 0;
    },
    reset() { encounter = null; deer.visible = false; },
    frame(now: number): string | null {
      if (!encounter) return null;
      const t = (now - encounter.start) / 1000;
      const entrance = Math.min(1, t / 1.8);
      deer.position.x = THREE.MathUtils.lerp(2.8, 0.65, entrance * entrance * (3 - 2 * entrance));
      const walking = entrance < 1 || encounter.behavior === 'walking';
      legs.forEach((leg, i) => { leg.rotation.z = walking ? Math.sin(t * 7 + (i === 0 || i === 3 ? 0 : Math.PI)) * 0.22 : 0; });
      if (entrance >= 1) {
        if (encounter.behavior === 'feeding') neck.rotation.z = 2.1 + Math.sin(t * 1.8) * 0.055;
        else neck.rotation.z = Math.sin(t * 0.8) * 0.025;
        if (encounter.behavior === 'walking') deer.position.x += Math.sin((t - 1.8) * 1.3) * 0.12;
        if (!encounter.reached) { encounter.reached = true; return encounter.id; }
      }
      return null;
    },
    dispose() {
      group.traverse(object => {
        const mesh = object as THREE.Mesh;
        mesh.geometry?.dispose();
        if (Array.isArray(mesh.material)) mesh.material.forEach(material => material.dispose());
        else mesh.material?.dispose();
      });
      scene.remove(group);
    },
  };
}
