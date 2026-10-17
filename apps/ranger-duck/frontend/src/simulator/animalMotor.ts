export const ANIMAL_ANCHOR = { x: 1.05, z: -0.05 } as const;
export type AnimalActivity = 'patrol' | 'interact' | 'hold';
export type AnimalMotor = { x: number; z: number; yaw: number; speed: number; phase: number; gait: number };
export const createAnimalMotor = (): AnimalMotor => ({ ...ANIMAL_ANCHOR, yaw: 0, speed: 0, phase: 0, gait: 0 });
const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));
const angle = (value: number) => Math.atan2(Math.sin(value), Math.cos(value));

/** A visual motor outside the duck's physics arena. It never changes duck state. */
export function stepAnimalMotor(motor: AnimalMotor, activity: AnimalActivity, delta: number, duck: { x: number; z: number }) {
  const dt = clamp(delta, 0, 0.05);
  if (activity === 'patrol') motor.phase += dt * 0.65;
  const targetX = activity === 'patrol' ? ANIMAL_ANCHOR.x + 0.12 * (1 - Math.cos(motor.phase)) : ANIMAL_ANCHOR.x;
  const targetZ = activity === 'patrol' ? ANIMAL_ANCHOR.z + Math.sin(motor.phase) * 0.27 : ANIMAL_ANCHOR.z;
  const dx = targetX - motor.x, dz = targetZ - motor.z;
  const distance = Math.hypot(dx, dz);
  const walking = activity !== 'hold' && distance > 0.012;
  const facing = walking ? Math.atan2(dz, -dx) : Math.atan2(duck.z - motor.z, motor.x - duck.x);
  const turn = angle(facing - motor.yaw);
  motor.yaw += clamp(turn, -2.8 * dt, 2.8 * dt);
  // Ease speed in and out, and turn before stepping. Position is bounded even
  // after a long hidden-tab gap; models never cross the yellow box's east edge.
  const desiredSpeed = walking ? Math.min(0.18, distance * 3) * Math.max(0, Math.cos(turn)) : 0;
  motor.speed += clamp(desiredSpeed - motor.speed, -0.9 * dt, 0.45 * dt);
  if (activity === 'hold') motor.speed = 0;
  const travel = Math.min(distance, motor.speed * dt);
  if (distance > 0 && travel > 0) {
    motor.x = Math.max(ANIMAL_ANCHOR.x, motor.x + dx / distance * travel);
    motor.z = clamp(motor.z + dz / distance * travel, ANIMAL_ANCHOR.z - 0.27, ANIMAL_ANCHOR.z + 0.27);
    motor.gait += travel / 0.18 * Math.PI * 2;
  }
  if (activity === 'interact' && distance < 0.012) { motor.x = ANIMAL_ANCHOR.x; motor.z = ANIMAL_ANCHOR.z; motor.speed = 0; }
  return motor;
}
