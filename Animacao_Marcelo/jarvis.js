import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';

export class ParticlesSwarm {
    constructor(container, count = 20000) {
        this.count = count;
        this.container = container;
        this.speedMult = 0.4;
        
        // SETUP
        this.scene = new THREE.Scene();
        this.scene.fog = new THREE.FogExp2(0x000000, 0.01);
        this.camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 2000);
        this.camera.position.set(0, 0, 100);
        
        this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
        this.renderer.setSize(window.innerWidth, window.innerHeight);
        this.container.appendChild(this.renderer.domElement);

        // POST PROCESSING
        this.composer = new EffectComposer(this.renderer);
        this.composer.addPass(new RenderPass(this.scene, this.camera));
        const bloomPass = new UnrealBloomPass(new THREE.Vector2(window.innerWidth, window.innerHeight), 1.5, 0.4, 0.85);
        bloomPass.strength = 1.8; bloomPass.radius = 0.4; bloomPass.threshold = 0;
        this.composer.addPass(bloomPass);

        // OBJECTS
        this.dummy = new THREE.Object3D();
        this.color = new THREE.Color();
        this.target = new THREE.Vector3();
        this.pColor = new THREE.Color();
        
        this.geometry = new THREE.PlaneGeometry(0.8, 0.8);
        this.material = new THREE.ShaderMaterial({
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
});
        
        this.mesh = new THREE.InstancedMesh(this.geometry, this.material, this.count);
        this.mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
        this.scene.add(this.mesh);
        
        this.positions = [];
        for(let i=0; i<this.count; i++) {
            this.positions.push(new THREE.Vector3((Math.random()-0.5)*100, (Math.random()-0.5)*100, (Math.random()-0.5)*100));
            this.mesh.setColorAt(i, this.color.setHex(0x00ff88));
        }
        
        this.clock = new THREE.Clock();
        this.animate = this.animate.bind(this);
        this.animate();
    }

    animate() {
        requestAnimationFrame(this.animate);
        const time = this.clock.getElapsedTime() * this.speedMult;
        
        if(this.material.uniforms && this.material.uniforms.uTime) {
            this.material.uniforms.uTime.value = time;
        }

        // API Stubs
        const PARAMS = {"speed":1.086,"spread":10.4,"core":10};
        const addControl = (id, l, min, max, val) => {
             return PARAMS[id] !== undefined ? PARAMS[id] : val;
        };
        const setInfo = () => {};
        const annotate = () => {};
        let THREE_LIB = THREE;
        
        let THREE_LIB = THREE;
        const count = this.count; // Alias for user code
        
        for(let i=0; i<this.count; i++) {
            let target = this.target;
            let color = this.pColor;
            
            // INJECTED CODE
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
            
            // UPDATE
            this.positions[i].lerp(this.target, 0.1);
            this.dummy.position.copy(this.positions[i]);
            this.dummy.updateMatrix();
            this.mesh.setMatrixAt(i, this.dummy.matrix);
            this.mesh.setColorAt(i, this.pColor);
        }
        this.mesh.instanceMatrix.needsUpdate = true;
        this.mesh.instanceColor.needsUpdate = true;
        
        this.composer.render();
    }
    
    dispose() {
        this.geometry.dispose();
        this.material.dispose();
        this.scene.remove(this.mesh);
        this.renderer.dispose();
    }
}