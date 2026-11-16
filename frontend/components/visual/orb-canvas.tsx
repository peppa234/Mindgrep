"use client";

// The MemoryOrb's WebGL scene. Only ever loaded through next/dynamic from memory-orb.tsx,
// so three.js stays out of every other route's bundle. WebGL renderer only (no WebGPU).
//
// What makes it read as a solid globe rather than a lit disc:
//   - the body is shaded, not self-lit: one key light, so it has a highlight and a dark side;
//   - a Fresnel rim on the surface and a soft atmosphere outside the silhouette;
//   - memories sit on the surface as points of light and travel round with it, coming up
//     over one limb and setting behind the other;
//   - links between them arc above the surface, so they part from it against the edge.

import { MeshDistortMaterial } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

const RADIUS = 1.45;
/** Nodes and the feet of the arcs float just clear of the cage. */
const SURFACE = RADIUS * 1.045;
/** How far an arc rises above the surface at its middle, as a share of the radius. */
const ARC_LIFT = 0.13;
const ATMOSPHERE = RADIUS * 1.32;

type Palette = { light: THREE.Color; body: THREE.Color; deep: THREE.Color; live: THREE.Color; gap: THREE.Color };

/** The scene's colours are the page's: read from the design tokens, never repeated here. */
function readPalette(): Palette {
  const style = getComputedStyle(document.documentElement);
  const token = (name: string, fallback: string) => new THREE.Color(style.getPropertyValue(name).trim() || fallback);
  return {
    light: token("--violet-300", "#C4B5FD"),
    body: token("--violet-600", "#7C3AED"),
    deep: token("--violet-900", "#2E1065"),
    live: token("--cyan-400", "#22D3EE"),
    gap: token("--magenta-500", "#D946EF"),
  };
}

/** Deterministic, so the globe is the same globe on every visit. */
function seeded(seed: number) {
  let s = seed;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}

/**
 * The graph drawn on the globe: memories on the vertices of the same geodesic lattice the
 * cage is made of, a few of them gaps, and links between ones that sit near each other.
 */
function buildGraph() {
  const rand = seeded(23);
  const lattice = new THREE.IcosahedronGeometry(1, 3).getAttribute("position");
  const seen = new Set<string>();
  const vertices: THREE.Vector3[] = [];
  for (let i = 0; i < lattice.count; i++) {
    const v = new THREE.Vector3().fromBufferAttribute(lattice, i).normalize();
    const key = `${v.x.toFixed(3)},${v.y.toFixed(3)},${v.z.toFixed(3)}`;
    if (!seen.has(key)) {
      seen.add(key);
      vertices.push(v);
    }
  }
  const nodes = vertices.filter(() => rand() < 0.34).map((at) => ({ at, gap: rand() < 0.1, seed: rand() }));

  const links: [THREE.Vector3, THREE.Vector3][] = [];
  const degree = new Array(nodes.length).fill(0);
  for (let i = 0; i < nodes.length && links.length < 22; i++) {
    for (let j = i + 1; j < nodes.length && degree[i] < 2; j++) {
      const angle = nodes[i].at.angleTo(nodes[j].at);
      if (degree[j] < 2 && angle > 0.55 && angle < 1.15 && rand() < 0.3) {
        links.push([nodes[i].at, nodes[j].at]);
        degree[i]++;
        degree[j]++;
      }
    }
  }
  return { nodes, links };
}

/** A point on the great circle from a to b, lifted off the surface toward the middle. */
function onArc(a: THREE.Vector3, b: THREE.Vector3, t: number) {
  const omega = a.angleTo(b);
  const p = a
    .clone()
    .multiplyScalar(Math.sin((1 - t) * omega))
    .add(b.clone().multiplyScalar(Math.sin(t * omega)))
    .divideScalar(Math.sin(omega));
  return p.multiplyScalar(SURFACE * (1 + ARC_LIFT * Math.sin(Math.PI * t)));
}

const rimVertex = /* glsl */ `
  varying vec3 vNormal;
  varying vec3 vView;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vNormal = normalize(normalMatrix * normal);
    vView = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }
`;

// Brightest where the surface turns away from the eye: the lit edge of a glassy sphere.
const rimFragment = /* glsl */ `
  uniform vec3 uColor;
  uniform float uPower;
  uniform float uStrength;
  varying vec3 vNormal;
  varying vec3 vView;
  void main() {
    float facing = clamp(dot(normalize(vNormal), normalize(vView)), 0.0, 1.0);
    gl_FragColor = vec4(uColor, pow(1.0 - facing, uPower) * uStrength);
  }
`;

// The inside of a larger sphere, of which only the ring outside the body shows: full
// strength where it meets the body's edge, fading to nothing at its own.
const atmosphereFragment = /* glsl */ `
  uniform vec3 uColor;
  uniform float uEdge;
  uniform float uStrength;
  varying vec3 vNormal;
  varying vec3 vView;
  void main() {
    float away = clamp(-dot(normalize(vNormal), normalize(vView)) / uEdge, 0.0, 1.0);
    gl_FragColor = vec4(uColor, pow(away, 3.2) * uStrength);
  }
`;

const nodeVertex = /* glsl */ `
  attribute vec3 aColor;
  attribute float aSeed;
  uniform float uTime;
  uniform float uPixelRatio;
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mv;
    float pulse = 0.7 + 0.3 * sin(uTime * (0.7 + aSeed) + aSeed * 40.0);
    gl_PointSize = (4.0 + aSeed * 4.0) * uPixelRatio * (7.0 / -mv.z);
    vColor = aColor;
    vAlpha = pulse;
  }
`;

// Travels its link once every few seconds; the arc is recomputed here so no geometry moves.
const pulseVertex = /* glsl */ `
  attribute vec3 aEnd;
  attribute float aSeed;
  uniform float uTime;
  uniform float uPixelRatio;
  uniform float uSurface;
  uniform float uLift;
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    float t = fract(uTime * (0.1 + aSeed * 0.08) + aSeed * 7.0);
    float omega = acos(clamp(dot(position, aEnd), -1.0, 1.0));
    vec3 along = (sin((1.0 - t) * omega) * position + sin(t * omega) * aEnd) / sin(omega);
    vec4 mv = modelViewMatrix * vec4(along * uSurface * (1.0 + uLift * sin(3.14159265 * t)), 1.0);
    gl_Position = projectionMatrix * mv;
    gl_PointSize = 3.4 * uPixelRatio * (7.0 / -mv.z);
    vColor = vec3(1.0);
    vAlpha = sin(3.14159265 * t);
  }
`;

const pointFragment = /* glsl */ `
  uniform vec3 uTint;
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    float glow = smoothstep(0.5, 0.0, d);
    gl_FragColor = vec4(vColor * uTint, glow * glow * vAlpha);
  }
`;

function Globe({ palette }: { palette: Palette }) {
  const group = useRef<THREE.Group>(null);
  const dpr = useThree((s) => s.viewport.dpr);

  const scene = useMemo(() => {
    const { nodes, links } = buildGraph();

    const nodeGeometry = new THREE.BufferGeometry();
    nodeGeometry.setAttribute("position", new THREE.Float32BufferAttribute(nodes.flatMap((n) => n.at.clone().multiplyScalar(SURFACE).toArray()), 3));
    nodeGeometry.setAttribute("aColor", new THREE.Float32BufferAttribute(nodes.flatMap((n) => (n.gap ? palette.gap : palette.live).toArray()), 3));
    nodeGeometry.setAttribute("aSeed", new THREE.Float32BufferAttribute(nodes.map((n) => n.seed), 1));

    // Every arc as short segments in one geometry: one draw call for all of them. Colour
    // fades toward the feet, and with additive blending darker means fainter.
    const STEPS = 28;
    const positions: number[] = [];
    const colors: number[] = [];
    for (const [a, b] of links) {
      for (let s = 0; s < STEPS; s++) {
        for (const t of [s / STEPS, (s + 1) / STEPS]) {
          positions.push(...onArc(a, b, t).toArray());
          colors.push(...palette.light.clone().multiplyScalar(0.25 + 0.75 * Math.sin(Math.PI * t)).toArray());
        }
      }
    }
    const arcGeometry = new THREE.BufferGeometry();
    arcGeometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    arcGeometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));

    const rand = seeded(5);
    const pulseGeometry = new THREE.BufferGeometry();
    pulseGeometry.setAttribute("position", new THREE.Float32BufferAttribute(links.flatMap(([a]) => a.toArray()), 3));
    pulseGeometry.setAttribute("aEnd", new THREE.Float32BufferAttribute(links.flatMap(([, b]) => b.toArray()), 3));
    pulseGeometry.setAttribute("aSeed", new THREE.Float32BufferAttribute(links.map(() => rand()), 1));

    return { nodeGeometry, arcGeometry, pulseGeometry };
  }, [palette]);

  useEffect(
    () => () => {
      scene.nodeGeometry.dispose();
      scene.arcGeometry.dispose();
      scene.pulseGeometry.dispose();
    },
    [scene],
  );

  const uniforms = useMemo(
    () => ({
      rim: { uColor: { value: palette.light }, uPower: { value: 3.0 }, uStrength: { value: 0.7 } },
      atmosphere: {
        uColor: { value: palette.body },
        // The body's edge, as the cosine it has on the atmosphere's inner face.
        uEdge: { value: Math.sqrt(1 - (RADIUS / ATMOSPHERE) ** 2) },
        uStrength: { value: 0.3 },
      },
      nodes: { uTime: { value: 0 }, uPixelRatio: { value: dpr }, uTint: { value: new THREE.Color(1.6, 1.6, 1.6) } },
      pulses: {
        uTime: { value: 0 },
        uPixelRatio: { value: dpr },
        uSurface: { value: SURFACE },
        uLift: { value: ARC_LIFT },
        uTint: { value: palette.light.clone().multiplyScalar(1.8) },
      },
    }),
    [palette, dpr],
  );

  useFrame((state, delta) => {
    if (group.current) {
      group.current.rotation.y += delta * 0.11;
      group.current.rotation.x = 0.22 + Math.sin(state.clock.elapsedTime / 9) * 0.07;
    }
    uniforms.nodes.uTime.value = state.clock.elapsedTime;
    uniforms.pulses.uTime.value = state.clock.elapsedTime;
  });

  return (
    <>
      <group ref={group} rotation={[0.22, 0, 0.12]}>
        <mesh>
          <icosahedronGeometry args={[RADIUS, 32]} />
          <MeshDistortMaterial
            color={palette.body}
            emissive={palette.deep}
            emissiveIntensity={0.28}
            roughness={0.46}
            metalness={0.2}
            clearcoat={0.55}
            clearcoatRoughness={0.42}
            distort={0.16}
            speed={1.2}
          />
        </mesh>
        {/* Same distortion and clock as the body, so the cage breathes with it. */}
        <mesh scale={1.035}>
          <icosahedronGeometry args={[RADIUS, 3]} />
          <MeshDistortMaterial
            wireframe
            transparent
            opacity={0.26}
            color={palette.light}
            emissive={palette.light}
            emissiveIntensity={0.5}
            distort={0.16}
            speed={1.2}
            depthWrite={false}
          />
        </mesh>
        <lineSegments geometry={scene.arcGeometry}>
          <lineBasicMaterial vertexColors transparent opacity={0.9} depthWrite={false} blending={THREE.AdditiveBlending} />
        </lineSegments>
        <points geometry={scene.nodeGeometry}>
          <shaderMaterial
            vertexShader={nodeVertex}
            fragmentShader={pointFragment}
            uniforms={uniforms.nodes}
            transparent
            depthWrite={false}
            blending={THREE.AdditiveBlending}
          />
        </points>
        {/* Its positions are computed in the shader, so its bounds say nothing: never cull it. */}
        <points geometry={scene.pulseGeometry} frustumCulled={false}>
          <shaderMaterial
            vertexShader={pulseVertex}
            fragmentShader={pointFragment}
            uniforms={uniforms.pulses}
            transparent
            depthWrite={false}
            blending={THREE.AdditiveBlending}
          />
        </points>
      </group>

      {/* The two shells do not turn with the globe: light on a sphere stays where the eye is.
          The rim sits just outside the furthest the body's distortion reaches (2.6%), or the
          body would poke through it in patches. */}
      <mesh scale={1.03}>
        <sphereGeometry args={[RADIUS, 64, 64]} />
        <shaderMaterial
          vertexShader={rimVertex}
          fragmentShader={rimFragment}
          uniforms={uniforms.rim}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
      <mesh>
        <sphereGeometry args={[ATMOSPHERE, 64, 64]} />
        <shaderMaterial
          vertexShader={rimVertex}
          fragmentShader={atmosphereFragment}
          uniforms={uniforms.atmosphere}
          side={THREE.BackSide}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
    </>
  );
}

const particleVertex = /* glsl */ `
  uniform float uTime;
  uniform float uPixelRatio;
  varying float vAlpha;
  void main() {
    // Keplerian drift: inner particles orbit faster. Per-particle variation comes from a
    // hash of the start position, so no extra attributes are needed.
    float seed = fract(sin(dot(position, vec3(12.9898, 78.233, 37.719))) * 43758.5453);
    float r = length(position.xz);
    float angle = atan(position.z, position.x) + uTime * (0.32 / sqrt(r));
    vec3 p = vec3(cos(angle) * r, position.y + sin(uTime * 0.6 + seed * 6.2831) * 0.04, sin(angle) * r);
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    gl_PointSize = (1.2 + seed * 2.2) * uPixelRatio * (7.0 / -mv.z);
    // The far side of the ring is dimmer than the near side: distance, without fog.
    vAlpha = (0.35 + 0.65 * seed) * mix(0.3, 1.0, smoothstep(-10.4, -6.2, mv.z));
  }
`;

const particleFragment = /* glsl */ `
  uniform vec3 uColor;
  varying float vAlpha;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    float a = smoothstep(0.5, 0.05, d);
    gl_FragColor = vec4(uColor, a * vAlpha);
  }
`;

function Particles({ count, color }: { count: number; color: THREE.Color }) {
  const dpr = useThree((s) => s.viewport.dpr);
  const geometry = useMemo(() => {
    const rand = seeded(11);
    const out = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const angle = rand() * Math.PI * 2;
      const r = 2.05 + Math.pow(rand(), 0.7) * 0.7;
      const spread = (rand() + rand() + rand() - 1.5) * 0.12 * r;
      out.set([Math.cos(angle) * r, spread, Math.sin(angle) * r], i * 3);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(out, 3));
    return g;
  }, [count]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  const uniforms = useMemo(() => ({ uTime: { value: 0 }, uPixelRatio: { value: dpr }, uColor: { value: color } }), [dpr, color]);
  useFrame((state) => {
    uniforms.uTime.value = state.clock.elapsedTime;
  });
  return (
    <group rotation={[0.42, 0, -0.18]}>
      {/* The shader moves every particle round its orbit, so the static bounds are wrong. */}
      <points geometry={geometry} frustumCulled={false}>
        <shaderMaterial
          vertexShader={particleVertex}
          fragmentShader={particleFragment}
          uniforms={uniforms}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
    </group>
  );
}

/** Gentle parallax: the camera eases toward the pointer, never snaps. */
function Parallax() {
  const target = useRef(new THREE.Vector2());
  useEffect(() => {
    const onMove = (e: PointerEvent) => target.current.set(e.clientX / window.innerWidth - 0.5, e.clientY / window.innerHeight - 0.5);
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, []);
  useFrame(({ camera }, delta) => {
    camera.position.x = THREE.MathUtils.damp(camera.position.x, target.current.x * 0.9, 2.2, delta);
    camera.position.y = THREE.MathUtils.damp(camera.position.y, -target.current.y * 0.6, 2.2, delta);
    camera.lookAt(0, 0, 0);
  });
  return null;
}

export default function OrbCanvas({ onReady, className = "" }: { onReady?: () => void; className?: string }) {
  const wrapper = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(true);
  const [pageVisible, setPageVisible] = useState(true);
  const palette = useMemo(readPalette, []);

  // Render only while on screen and while the tab is visible; otherwise the loop sleeps.
  useEffect(() => {
    const el = wrapper.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), { rootMargin: "100px" });
    io.observe(el);
    const onVisibility = () => setPageVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      io.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return (
    <div ref={wrapper} className={className}>
      <Canvas
        dpr={[1, 2]}
        frameloop={inView && pageVisible ? "always" : "never"}
        camera={{ position: [0, 0, 8.1], fov: 38 }}
        gl={{ alpha: true, antialias: false, powerPreference: "high-performance" }}
        onCreated={({ gl }) => {
          gl.setClearColor(0x000000, 0);
          // Two frames later the first image is on screen: then fade the poster out.
          requestAnimationFrame(() => requestAnimationFrame(() => onReady?.()));
        }}
      >
        {/* One key light from the upper left, toward the headline, gives the globe a lit
            side and a dark side; the cyan light behind it catches the far edge. */}
        <ambientLight intensity={0.1} />
        <pointLight position={[-4.6, 3.6, 3.4]} intensity={120} color={palette.light} />
        <pointLight position={[4.4, -1.6, -3.0]} intensity={42} color={palette.live} />
        <Globe palette={palette} />
        <Particles count={800} color={palette.live} />
        <Parallax />
        <EffectComposer multisampling={0}>
          <Bloom mipmapBlur intensity={0.95} luminanceThreshold={0.5} luminanceSmoothing={0.3} />
        </EffectComposer>
      </Canvas>
    </div>
  );
}
