"use client";

// The MemoryOrb's WebGL scene. Only ever loaded through next/dynamic from memory-orb.tsx,
// so three.js stays out of every other route's bundle. WebGL renderer only (no WebGPU).

import { MeshDistortMaterial, Points } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

const VIOLET_300 = "#C4B5FD";
const VIOLET_500 = "#8B5CF6";
const VIOLET_600 = "#7C3AED";
const CYAN_400 = "#22D3EE";

function Orb() {
  const group = useRef<THREE.Group>(null);
  useFrame((_, delta) => {
    if (!group.current) return;
    group.current.rotation.y += delta * 0.08;
    group.current.rotation.x = Math.sin(performance.now() / 9000) * 0.12;
  });
  return (
    <group ref={group}>
      <mesh>
        <icosahedronGeometry args={[1.45, 32]} />
        <MeshDistortMaterial
          color={VIOLET_600}
          emissive={VIOLET_500}
          emissiveIntensity={0.55}
          roughness={0.28}
          metalness={0.25}
          distort={0.16}
          speed={1.2}
        />
      </mesh>
      {/* Same distortion and clock as the body, so the cage breathes with it. */}
      <mesh scale={1.035}>
        <icosahedronGeometry args={[1.45, 3]} />
        <MeshDistortMaterial
          wireframe
          transparent
          opacity={0.4}
          color={VIOLET_300}
          emissive={VIOLET_300}
          emissiveIntensity={0.9}
          distort={0.16}
          speed={1.2}
          depthWrite={false}
        />
      </mesh>
    </group>
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
    vAlpha = 0.35 + 0.65 * seed;
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

function Particles({ count }: { count: number }) {
  const material = useRef<THREE.ShaderMaterial>(null);
  const dpr = useThree((s) => s.viewport.dpr);
  const positions = useMemo(() => {
    let seed = 11;
    const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    const out = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const angle = rand() * Math.PI * 2;
      const r = 1.85 + Math.pow(rand(), 0.7) * 0.7;
      const spread = (rand() + rand() + rand() - 1.5) * 0.12 * r;
      out.set([Math.cos(angle) * r, spread, Math.sin(angle) * r], i * 3);
    }
    return out;
  }, [count]);
  const uniforms = useMemo(
    () => ({ uTime: { value: 0 }, uPixelRatio: { value: dpr }, uColor: { value: new THREE.Color(CYAN_400) } }),
    [dpr],
  );
  useFrame((state) => {
    if (material.current) material.current.uniforms.uTime.value = state.clock.elapsedTime;
  });
  return (
    <group rotation={[0.42, 0, -0.18]}>
      <Points positions={positions}>
        <shaderMaterial
          ref={material}
          vertexShader={particleVertex}
          fragmentShader={particleFragment}
          uniforms={uniforms}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </Points>
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
        <ambientLight intensity={0.35} />
        <pointLight position={[3, 3, 4]} intensity={38} color={VIOLET_300} />
        <pointLight position={[-4, -2, -2]} intensity={18} color={CYAN_400} />
        <Orb />
        <Particles count={800} />
        <Parallax />
        <EffectComposer multisampling={0}>
          <Bloom mipmapBlur intensity={1.2} luminanceThreshold={0.2} />
        </EffectComposer>
      </Canvas>
    </div>
  );
}
