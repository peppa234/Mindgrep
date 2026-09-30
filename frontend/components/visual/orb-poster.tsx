// The MemoryOrb's static poster: rendered on the server, shown before the canvas loads,
// and the whole orb for reduced motion or no WebGL. Geometry is computed once at module
// load, so the poster is plain SVG with no runtime cost.

const PHI = (1 + Math.sqrt(5)) / 2;
const SIZE = 400;
const C = SIZE / 2;
const R = 108;

function icosahedronPath(): string {
  const raw: [number, number, number][] = [];
  for (const a of [-1, 1]) for (const b of [-PHI, PHI]) raw.push([0, a, b], [a, b, 0], [b, 0, a]);
  // Tilt it so no edge lines up with the screen axes.
  const [ry, rx] = [0.55, 0.38];
  const pts = raw.map(([x, y, z]) => {
    const x1 = x * Math.cos(ry) + z * Math.sin(ry);
    const z1 = -x * Math.sin(ry) + z * Math.cos(ry);
    const y2 = y * Math.cos(rx) - z1 * Math.sin(rx);
    const n = Math.hypot(x, y, z);
    return [C + (x1 / n) * R, C - (y2 / n) * R] as const;
  });
  const segments: string[] = [];
  for (let i = 0; i < raw.length; i++)
    for (let j = i + 1; j < raw.length; j++) {
      const d = Math.hypot(raw[i][0] - raw[j][0], raw[i][1] - raw[j][1], raw[i][2] - raw[j][2]);
      if (Math.abs(d - 2) < 1e-6) segments.push(`M${pts[i][0].toFixed(1)} ${pts[i][1].toFixed(1)}L${pts[j][0].toFixed(1)} ${pts[j][1].toFixed(1)}`);
    }
  return segments.join("");
}

function particles(count: number) {
  let seed = 7;
  const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  return Array.from({ length: count }, () => {
    const angle = rand() * Math.PI * 2;
    const radius = 150 + rand() * 45;
    const x = Math.cos(angle) * radius;
    const y = Math.sin(angle) * radius * 0.28 + (rand() - 0.5) * 10;
    // Tilt the disc slightly.
    const t = -0.2;
    return {
      x: C + x * Math.cos(t) - y * Math.sin(t),
      y: C + x * Math.sin(t) + y * Math.cos(t),
      r: 0.6 + rand() * 1.1,
      o: 0.25 + rand() * 0.6,
    };
  });
}

const WIREFRAME = icosahedronPath();
const PARTICLES = particles(150);

export function OrbPoster({ className = "", id = "orb" }: { className?: string; id?: string }) {
  return (
    <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className={`h-full w-full ${className}`} aria-hidden>
      <defs>
        <radialGradient id={`${id}-halo`}>
          <stop offset="0%" style={{ stopColor: "var(--violet-600)", stopOpacity: 0.5 }} />
          <stop offset="55%" style={{ stopColor: "var(--violet-600)", stopOpacity: 0.12 }} />
          <stop offset="100%" style={{ stopColor: "var(--violet-600)", stopOpacity: 0 }} />
        </radialGradient>
        <radialGradient id={`${id}-body`} cx="36%" cy="30%" r="80%">
          <stop offset="0%" style={{ stopColor: "var(--violet-300)" }} />
          <stop offset="38%" style={{ stopColor: "var(--violet-500)" }} />
          <stop offset="78%" style={{ stopColor: "var(--violet-600)" }} />
          <stop offset="100%" style={{ stopColor: "var(--violet-900)" }} />
        </radialGradient>
      </defs>
      <circle cx={C} cy={C} r={C} fill={`url(#${id}-halo)`} />
      <circle cx={C} cy={C} r={R} fill={`url(#${id}-body)`} style={{ filter: "drop-shadow(0 0 24px rgba(139, 92, 246, 0.55))" }} />
      <path d={WIREFRAME} fill="none" strokeWidth={0.9} style={{ stroke: "var(--violet-300)", opacity: 0.5 }} />
      <g style={{ fill: "var(--cyan-400)" }}>
        {PARTICLES.map((p, i) => (
          <circle key={i} cx={p.x.toFixed(1)} cy={p.y.toFixed(1)} r={p.r.toFixed(2)} opacity={p.o.toFixed(2)} />
        ))}
      </g>
    </svg>
  );
}
