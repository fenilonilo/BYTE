import React, { useRef, useMemo, useEffect } from 'react';
import { Canvas, useFrame, extend } from '@react-three/fiber';
import { OrbitControls, Effects } from '@react-three/drei';
import { UnrealBloomPass } from 'three-stdlib';
import * as THREE from 'three';

extend({ UnrealBloomPass });

const ParticleSwarm = () => {
  const meshRef = useRef();
  const count = 20000;
  const speedMult = 0.4;
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const target = useMemo(() => new THREE.Vector3(), []);
  const pColor = useMemo(() => new THREE.Color(), []);
  const color = pColor; // Alias for user code compatibility
  
  const positions = useMemo(() => {
     const pos = [];
     for(let i=0; i<count; i++) pos.push(new THREE.Vector3((Math.random()-0.5)*100, (Math.random()-0.5)*100, (Math.random()-0.5)*100));
     return pos;
  }, []);

  // Material & Geom
  const material = useMemo(() => new THREE.ShaderMaterial({
    uniforms: { uTime: { value: 0 } },
    vertexShader: `
        varying vec2 vUv;
        varying vec3 vColor;
        void main() { 
            vUv = uv; 
            vColor = instanceColor;
            gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position, 1.0); 
        }
    `,
    fragmentShader: `
        varying vec2 vUv;
        varying vec3 vColor;
        uniform float uTime;
        float rand(vec2 n) { return fract(sin(dot(n, vec2(12.9898, 4.1414))) * 43758.5453); }
        float noise(vec2 p) { vec2 ip = floor(p); vec2 u = fract(p); u = u*u*(3.0-2.0*u); float res = mix(mix(rand(ip),rand(ip+vec2(1.0,0.0)),u.x),mix(rand(ip+vec2(0.0,1.0)),rand(ip+vec2(1.0,1.0)),u.x),u.y); return res * res; }
        void main() {
            float dist = distance(vUv, vec2(0.5));
            float n = noise(vUv * 5.0 + uTime * 0.5);
            float alpha = (1.0 - smoothstep(0.2, 0.5, dist)) * (0.5 + 0.5 * n);
            if(alpha < 0.1) discard;
            gl_FragColor = vec4(vColor + 0.2, alpha * 0.8);
        }
    `,
    transparent: true, depthWrite: false, side: 2, blending: 2
}), []);
  const geometry = useMemo(() => new THREE.PlaneGeometry(0.8, 0.8), []);

  const PARAMS = useMemo(() => ({"speed":1.086,"spread":10.4,"core":10}), []);
  const addControl = (id, l, min, max, val) => {
      return PARAMS[id] !== undefined ? PARAMS[id] : val;
  };
  const setInfo = () => {};
  const annotate = () => {};

  useFrame((state) => {
    if (!meshRef.current) return;
    const time = state.clock.getElapsedTime() * speedMult;
    const THREE_LIB = THREE;

    if(material.uniforms && material.uniforms.uTime) {
         material.uniforms.uTime.value = time;
    }

    for (let i = 0; i < count; i++) {
        // USER CODE START
        const speed = addControl("speed", "Swarm Speed", 0.1, 3.0, 0.4);
        const spread = addControl("spread", "Cloud Radius", 5.0, 50.0, 22.0);
        const core = addControl("core", "Core Density", 1.0, 10.0, 3.5);
        
        if (i === 0) {
        setInfo("Violet Swarm", "A concentrated entity of purple nodes. High core density diffusing into a gentle outer orbital cloud.");
        annotate("center", new THREE.Vector3(0, 0, 0), "Nucleus");
        }
        
        const t = time * speed;
        
        const n1 = Math.abs((Math.sin(i * 12.9898) * 43758.5453) % 1.0);
        const n2 = Math.abs((Math.sin(i * 78.233) * 43758.5453) % 1.0);
        const n3 = Math.abs((Math.sin(i * 93.989) * 43758.5453) % 1.0);
        
        const radiusDist = Math.pow(n3, 5.0);
        const currentRadius = core + spread * radiusDist;
        
        const theta = n1 * Math.PI * 2.0;
        const phi = Math.acos((n2 * 2.0) - 1.0);
        
        let xBase = Math.cos(theta) * Math.sin(phi) * currentRadius;
        let yBase = Math.sin(theta) * Math.sin(phi) * currentRadius;
        let zBase = Math.cos(phi) * currentRadius;
        
        const motion = t + (n1 * 15.0);
        const breathe = Math.sin(t * 2.0) * (1.0 - radiusDist) * 0.5;
        
        xBase += Math.sin(motion + yBase * 0.2) * 0.8 + breathe;
        yBase += Math.cos(motion + zBase * 0.2) * 0.8 + breathe;
        zBase += Math.sin(motion + xBase * 0.2) * 0.8 + breathe;
        
        const rotT = t * 0.15;
        const cosR = Math.cos(rotT);
        const sinR = Math.sin(rotT);
        
        const fx = xBase * cosR - zBase * sinR;
        const fz = xBase * sinR + zBase * cosR;
        
        target.set(fx, yBase, fz);
        
        const h = 0.78 + (n1 * 0.08);
        const s = 0.85 + (n2 * 0.15);
        const l = 0.15 + (1.0 - radiusDist) * 0.45 + (Math.sin(motion * 2.0) * 0.1);
        
        color.setHSL(h, s, l);
        // USER CODE END

        positions[i].lerp(target, 0.1);
        dummy.position.copy(positions[i]);
        dummy.updateMatrix();
        meshRef.current.setMatrixAt(i, dummy.matrix);
        meshRef.current.setColorAt(i, pColor);
    }
    meshRef.current.instanceMatrix.needsUpdate = true;
    if (meshRef.current.instanceColor) meshRef.current.instanceColor.needsUpdate = true;
  });

  return (
    <instancedMesh ref={meshRef} args={[geometry, material, count]} />
  );
};

export default function App() {
  return (
    <div style={{ width: '100vw', height: '100vh', background: '#000' }}>
      <Canvas camera={{ position: [0, 0, 100], fov: 60 }}>
        <fog attach="fog" args={['#000000', 0.01]} />
        <ParticleSwarm />
        <OrbitControls autoRotate={false} />
        <Effects disableGamma>
            <unrealBloomPass threshold={0} strength={1.8} radius={0.4} />
        </Effects>
      </Canvas>
    </div>
  );
}