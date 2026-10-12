/**
 * AtomicCore3D - Three.js 3D Atomic Reactor Core Component
 * 
 * Features:
 * - Nucleus: 32 glossy, multicolored spheres with subtle organic breathing motion
 * - Six tilted elliptical orbital rings with distinct Euler tilts, eccentricities, and rotation speeds
 * - Moving luminous electrons traveling along elliptical curves with coronas and orbital glow trails
 * - Ambient energy particle field drifting in a spherical envelope
 * - Central state-reactive PointLight and multi-directional specular lighting
 * - Interactive states: IDLE, LISTENING, THINKING / PROCESSING, EXECUTING, VERIFYING, SPEAKING / RESPONDING, ERROR, OFFLINE
 * - Smooth camera breathing and pointer parallax
 * - Prefers-reduced-motion compliance and WebGL fallback
 * - Clean lifecycle disposal (geometries, materials, renderer, event listeners)
 */

import * as THREE from 'three';

export function isWebGLAvailable() {
  try {
    const canvas = document.createElement('canvas');
    return !!(
      window.WebGLRenderingContext &&
      (canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
    );
  } catch (e) {
    return false;
  }
}

// Color palettes for multicolored glossy nucleus
const NUCLEUS_PALETTE = [
  0x27D3FF, // Cyan
  0xFFD700, // Gold
  0xFF7A00, // Orange
  0xFF007F, // Magenta
  0x8B5CF6, // Violet
  0x0051FF, // Deep Blue
  0x00F0FF, // Electric Cyan
  0xF43F5E, // Rose Red
  0xA855F7, // Purple
  0xFBBF24  // Amber Gold
];

// Configuration for the 6 elliptical orbits
const ORBIT_CONFIGS = [
  {
    a: 4.4,
    b: 2.2,
    tilt: [0.95, 0.35, 0.15],
    speed: 0.9,
    color: 0x27D3FF, // Cyan
    electronSize: 0.16
  },
  {
    a: 4.7,
    b: 2.5,
    tilt: [-0.75, 0.85, -0.40],
    speed: -0.75,
    color: 0xFF007F, // Magenta
    electronSize: 0.17
  },
  {
    a: 4.9,
    b: 2.3,
    tilt: [0.50, -1.05, 0.65],
    speed: 0.85,
    color: 0xFFD700, // Gold
    electronSize: 0.16
  },
  {
    a: 4.5,
    b: 2.6,
    tilt: [-1.20, -0.50, 0.30],
    speed: -0.80,
    color: 0x8B5CF6, // Violet
    electronSize: 0.18
  },
  {
    a: 5.1,
    b: 2.4,
    tilt: [0.25, 1.30, -0.85],
    speed: 0.70,
    color: 0x0066FF, // Deep Blue
    electronSize: 0.16
  },
  {
    a: 4.6,
    b: 2.7,
    tilt: [-0.35, -0.80, 1.15],
    speed: -0.95,
    color: 0xFF7A00, // Orange
    electronSize: 0.17
  }
];

export class AtomicCore3D {
  /**
   * @param {HTMLCanvasElement} canvasElement
   * @param {Object} options
   */
  constructor(canvasElement, options = {}) {
    if (!canvasElement) {
      throw new Error('AtomicCore3D requires a valid HTMLCanvasElement.');
    }

    this.canvas = canvasElement;
    this.options = {
      reducedMotion: false,
      interactive: true,
      ...options
    };

    this.state = 'IDLE';
    this.audioLevel = 0.0;
    this.isDestroyed = false;
    this.animFrameId = null;
    this.clock = new THREE.Clock();

    // Motion parameters
    this.speedMultiplier = 1.0;
    this.targetSpeedMultiplier = 1.0;
    this.targetLightIntensity = 1.8;
    this.currentLightIntensity = 1.8;
    this.targetLightColor = new THREE.Color(0x27D3FF);
    this.currentLightColor = new THREE.Color(0x27D3FF);
    this.speakingPulse = 0.0;

    // Pointer parallax
    this.targetTiltX = 0;
    this.targetTiltY = 0;
    this.currentTiltX = 0;
    this.currentTiltY = 0;

    // Three.js Core Objects
    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.rootGroup = null;
    this.nucleusGroup = null;
    this.orbitsGroup = null;
    this.particles = null;
    this.corePointLight = null;
    this.ambientLight = null;

    // Internal collections for animation
    this.nucleusSpheres = [];
    this.orbitObjects = [];
    this.disposables = [];

    // Check reduced motion preference
    if (window.matchMedia) {
      const motionMedia = window.matchMedia('(prefers-reduced-motion: reduce)');
      if (motionMedia.matches) {
        this.options.reducedMotion = true;
      }
      this.motionListener = (e) => {
        this.options.reducedMotion = e.matches;
      };
      motionMedia.addEventListener('change', this.motionListener);
    }

    // Initialize WebGL Scene or Fallback
    if (!isWebGLAvailable()) {
      this.initFallback();
      return;
    }

    try {
      this.initScene();
      this.buildNucleus();
      this.buildOrbitsAndElectrons();
      this.buildParticleField();
      this.buildLighting();
      this.bindEvents();
      this.startLoop();
    } catch (err) {
      console.error('Failed to initialize Three.js AtomicCore3D:', err);
      this.initFallback();
    }
  }

  initFallback() {
    // 2D Canvas graceful fallback
    const ctx = this.canvas.getContext('2d');
    if (!ctx) return;
    const drawFallback = () => {
      if (this.isDestroyed) return;
      const w = this.canvas.clientWidth || 300;
      const h = this.canvas.clientHeight || 300;
      this.canvas.width = w;
      this.canvas.height = h;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = '#0B1017';
      ctx.fillRect(0, 0, w, h);
      ctx.strokeStyle = '#27D3FF';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(w / 2, h / 2, Math.min(w, h) * 0.35, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = '#27D3FF';
      ctx.font = '12px monospace';
      ctx.textAlign = 'center';
      ctx.fillText('3D ATOM CORE [2D FALLBACK]', w / 2, h / 2 + 4);
    };
    drawFallback();
  }

  initScene() {
    this.scene = new THREE.Scene();

    const rect = this.canvas.getBoundingClientRect();
    const width = rect.width || this.canvas.clientWidth || 400;
    const height = rect.height || this.canvas.clientHeight || 400;

    this.camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
    this.camera.position.set(0, 0, 13.5);

    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      alpha: true,
      antialias: true,
      powerPreference: 'high-performance'
    });

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.renderer.setPixelRatio(dpr);
    this.renderer.setSize(width, height, false);
    this.renderer.setClearColor(0x000000, 0); // Transparent canvas

    this.rootGroup = new THREE.Group();
    this.scene.add(this.rootGroup);

    this.nucleusGroup = new THREE.Group();
    this.rootGroup.add(this.nucleusGroup);

    this.orbitsGroup = new THREE.Group();
    this.rootGroup.add(this.orbitsGroup);
  }

  buildNucleus() {
    const sphereCount = 32;
    const baseRadius = 0.22;
    const sphereGeo = new THREE.SphereGeometry(baseRadius, 24, 24);
    this.disposables.push(sphereGeo);

    // Pre-create shared materials for performance and memory
    const materials = NUCLEUS_PALETTE.map((color) => {
      const mat = new THREE.MeshPhysicalMaterial({
        color: color,
        emissive: color,
        emissiveIntensity: 0.18,
        roughness: 0.12,
        metalness: 0.15,
        clearcoat: 1.0,
        clearcoatRoughness: 0.08
      });
      this.disposables.push(mat);
      return mat;
    });

    // Golden spiral distribution on spherical volume
    for (let i = 0; i < sphereCount; i++) {
      const phi = Math.acos(-1 + (2 * i) / sphereCount);
      const theta = Math.sqrt(sphereCount * Math.PI) * phi;
      const distance = 0.35 + 0.75 * Math.pow(i / sphereCount, 0.55);

      const x = distance * Math.sin(phi) * Math.cos(theta);
      const y = distance * Math.sin(phi) * Math.sin(theta);
      const z = distance * Math.cos(phi);

      const mat = materials[i % materials.length];
      const mesh = new THREE.Mesh(sphereGeo, mat);
      
      const scale = 0.85 + Math.random() * 0.45;
      mesh.scale.set(scale, scale, scale);
      mesh.position.set(x, y, z);

      this.nucleusGroup.add(mesh);

      this.nucleusSpheres.push({
        mesh,
        basePos: new THREE.Vector3(x, y, z),
        freq: 1.2 + Math.random() * 1.8,
        phase: Math.random() * Math.PI * 2,
        amp: 0.08 + Math.random() * 0.06
      });
    }
  }

  buildOrbitsAndElectrons() {
    const segments = 128;

    ORBIT_CONFIGS.forEach((cfg, idx) => {
      const orbitContainer = new THREE.Group();
      orbitContainer.rotation.set(cfg.tilt[0], cfg.tilt[1], cfg.tilt[2]);
      this.orbitsGroup.add(orbitContainer);

      // 1. Build Elliptical Ring Curve Geometry
      const points = [];
      for (let i = 0; i <= segments; i++) {
        const theta = (i / segments) * Math.PI * 2;
        points.push(new THREE.Vector3(cfg.a * Math.cos(theta), cfg.b * Math.sin(theta), 0));
      }
      const ringGeo = new THREE.BufferGeometry().setFromPoints(points);
      this.disposables.push(ringGeo);

      // Subtle additive neon glow ring material
      const ringMat = new THREE.LineBasicMaterial({
        color: cfg.color,
        transparent: true,
        opacity: 0.55,
        blending: THREE.AdditiveBlending
      });
      this.disposables.push(ringMat);

      const ringLine = new THREE.Line(ringGeo, ringMat);
      orbitContainer.add(ringLine);

      // 2. Electron Sphere
      const electronGeo = new THREE.SphereGeometry(cfg.electronSize, 16, 16);
      this.disposables.push(electronGeo);

      const electronMat = new THREE.MeshStandardMaterial({
        color: 0xffffff,
        emissive: cfg.color,
        emissiveIntensity: 2.2,
        roughness: 0.1,
        metalness: 0.2
      });
      this.disposables.push(electronMat);

      const electronMesh = new THREE.Mesh(electronGeo, electronMat);
      orbitContainer.add(electronMesh);

      // 3. Electron Corona / Glowing Halo (concentric additive shell)
      const coronaGeo = new THREE.SphereGeometry(cfg.electronSize * 2.2, 12, 12);
      this.disposables.push(coronaGeo);

      const coronaMat = new THREE.MeshBasicMaterial({
        color: cfg.color,
        transparent: true,
        opacity: 0.45,
        blending: THREE.AdditiveBlending,
        wireframe: false
      });
      this.disposables.push(coronaMat);

      const coronaMesh = new THREE.Mesh(coronaGeo, coronaMat);
      electronMesh.add(coronaMesh);

      // 4. Trailing Glow Nodes along the ellipse behind electron
      const trailCount = 6;
      const trailMeshes = [];
      const trailGeo = new THREE.SphereGeometry(cfg.electronSize * 0.75, 8, 8);
      this.disposables.push(trailGeo);

      for (let t = 0; t < trailCount; t++) {
        const trailMat = new THREE.MeshBasicMaterial({
          color: cfg.color,
          transparent: true,
          opacity: 0.35 * (1 - t / trailCount),
          blending: THREE.AdditiveBlending
        });
        this.disposables.push(trailMat);

        const trailNode = new THREE.Mesh(trailGeo, trailMat);
        const nodeScale = 1 - (t / trailCount) * 0.6;
        trailNode.scale.set(nodeScale, nodeScale, nodeScale);
        orbitContainer.add(trailNode);
        trailMeshes.push(trailNode);
      }

      this.orbitObjects.push({
        orbitContainer,
        config: cfg,
        electronMesh,
        trailMeshes,
        theta: Math.random() * Math.PI * 2,
        currentSpeed: cfg.speed
      });
    });
  }

  buildParticleField() {
    const particleCount = 110;
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);

    const baseColor = new THREE.Color(0x27D3FF);
    const goldColor = new THREE.Color(0xFFD700);
    const violetColor = new THREE.Color(0x8B5CF6);

    for (let i = 0; i < particleCount; i++) {
      const radius = 5.2 + Math.random() * 5.8;
      const theta = Math.random() * Math.PI * 2;
      const phi = (Math.random() - 0.5) * Math.PI;

      positions[i * 3] = radius * Math.cos(phi) * Math.cos(theta);
      positions[i * 3 + 1] = radius * Math.sin(phi);
      positions[i * 3 + 2] = radius * Math.cos(phi) * Math.sin(theta);

      const choice = Math.random();
      const col = choice < 0.5 ? baseColor : choice < 0.8 ? violetColor : goldColor;
      colors[i * 3] = col.r;
      colors[i * 3 + 1] = col.g;
      colors[i * 3 + 2] = col.b;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    this.disposables.push(geometry);

    const material = new THREE.PointsMaterial({
      size: 0.08,
      vertexColors: true,
      transparent: true,
      opacity: 0.65,
      blending: THREE.AdditiveBlending
    });
    this.disposables.push(material);

    this.particles = new THREE.Points(geometry, material);
    this.rootGroup.add(this.particles);
  }

  buildLighting() {
    // 1. Central state-reactive PointLight
    this.corePointLight = new THREE.PointLight(0x27D3FF, 1.8, 20);
    this.corePointLight.position.set(0, 0, 0);
    this.scene.add(this.corePointLight);

    // 2. Ambient light for baseline visibility
    this.ambientLight = new THREE.AmbientLight(0x0E1726, 1.2);
    this.scene.add(this.ambientLight);

    // 3. Directional Key Light for crisp glossy specular highlights
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.4);
    keyLight.position.set(10, 12, 14);
    this.scene.add(keyLight);

    // 4. Directional Cyan Rim Light
    const rimLight = new THREE.DirectionalLight(0x27D3FF, 0.9);
    rimLight.position.set(-12, -8, -10);
    this.scene.add(rimLight);
  }

  bindEvents() {
    this.onResize = () => this.resize();
    window.addEventListener('resize', this.onResize);

    if (this.options.interactive) {
      this.onMouseMove = (e) => {
        const cx = window.innerWidth / 2;
        const cy = window.innerHeight / 2;
        this.targetTiltY = ((e.clientX - cx) / cx) * 0.35;
        this.targetTiltX = ((e.clientY - cy) / cy) * 0.35;
      };
      window.addEventListener('mousemove', this.onMouseMove);
    }
  }

  resize() {
    if (!this.renderer || !this.camera || !this.canvas) return;
    const rect = this.canvas.getBoundingClientRect();
    const width = rect.width || this.canvas.clientWidth || 400;
    const height = rect.height || this.canvas.clientHeight || 400;

    if (width === 0 || height === 0) return;

    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.renderer.setPixelRatio(dpr);
    this.renderer.setSize(width, height, false);
  }

  startLoop() {
    const animate = () => {
      if (this.isDestroyed) return;
      this.animFrameId = requestAnimationFrame(animate);
      this.render();
    };
    animate();
  }

  render() {
    const delta = Math.min(this.clock.getDelta(), 0.1);
    const elapsedTime = this.clock.getElapsedTime();

    // Check reduced motion multiplier
    const motionFactor = this.options.reducedMotion ? 0.2 : 1.0;

    // Smooth speed multiplier interpolation
    this.speedMultiplier += (this.targetSpeedMultiplier - this.speedMultiplier) * 0.08;

    // Smooth light intensity and color transition
    this.currentLightIntensity += (this.targetLightIntensity - this.currentLightIntensity) * 0.1;
    this.currentLightColor.lerp(this.targetLightColor, 0.08);

    // Update central point light
    let dynamicIntensity = this.currentLightIntensity;
    if (this.state === 'SPEAKING' || this.state === 'RESPONDING') {
      // Rhythmic outward harmonic light pulse
      this.speakingPulse += delta * 7.0;
      dynamicIntensity += Math.sin(this.speakingPulse) * 0.85 + this.audioLevel * 1.5;
    } else if (this.state === 'LISTENING') {
      dynamicIntensity += Math.sin(elapsedTime * 5.0) * 0.4 + this.audioLevel * 1.8;
    } else {
      // Gentle IDLE breathing
      dynamicIntensity += Math.sin(elapsedTime * 1.8) * 0.25;
    }

    if (this.corePointLight) {
      this.corePointLight.intensity = Math.max(0.4, dynamicIntensity);
      this.corePointLight.color.copy(this.currentLightColor);
    }

    // Pointer parallax interpolation
    this.currentTiltX += (this.targetTiltX - this.currentTiltX) * 0.05;
    this.currentTiltY += (this.targetTiltY - this.currentTiltY) * 0.05;

    if (this.rootGroup) {
      this.rootGroup.rotation.x = this.currentTiltX;
      this.rootGroup.rotation.y = this.currentTiltY + elapsedTime * 0.05 * motionFactor;
    }

    // 1. Animate Nucleus Spheres (Organic Breathing & Undulation)
    const nucleusScalePulse = (this.state === 'SPEAKING' || this.state === 'RESPONDING')
      ? 1.0 + Math.sin(elapsedTime * 8.0) * 0.08
      : (this.state === 'THINKING' || this.state === 'PROCESSING')
      ? 0.94 + Math.sin(elapsedTime * 4.0) * 0.03
      : 1.0 + Math.sin(elapsedTime * 1.5) * 0.03;

    this.nucleusGroup.scale.set(nucleusScalePulse, nucleusScalePulse, nucleusScalePulse);
    this.nucleusGroup.rotation.y += delta * 0.12 * motionFactor;
    this.nucleusGroup.rotation.z += delta * 0.08 * motionFactor;

    for (let i = 0; i < this.nucleusSpheres.length; i++) {
      const item = this.nucleusSpheres[i];
      const offset = Math.sin(elapsedTime * item.freq + item.phase) * item.amp * motionFactor;
      item.mesh.position.copy(item.basePos).multiplyScalar(1.0 + offset);
    }

    // 2. Animate Orbits, Electrons, and Trails
    const orbitSpeedMultiplier = this.speedMultiplier * motionFactor;

    this.orbitObjects.forEach((orbit) => {
      // Advance electron angle along elliptical orbit
      orbit.theta += delta * orbit.currentSpeed * orbitSpeedMultiplier;

      const a = orbit.config.a;
      const b = orbit.config.b;

      // Position electron
      const ex = a * Math.cos(orbit.theta);
      const ey = b * Math.sin(orbit.theta);
      orbit.electronMesh.position.set(ex, ey, 0);

      // Position trailing glow nodes behind electron
      const trailLag = 0.045 * Math.sign(orbit.currentSpeed || 1);
      for (let t = 0; t < orbit.trailMeshes.length; t++) {
        const lagTheta = orbit.theta - (t + 1) * trailLag;
        const tx = a * Math.cos(lagTheta);
        const ty = b * Math.sin(lagTheta);
        orbit.trailMeshes[t].position.set(tx, ty, 0);
      }

      // Continuous subtle precession of orbit planes
      orbit.orbitContainer.rotation.z += delta * 0.04 * orbitSpeedMultiplier;
    });

    // 3. Animate Ambient Energy Particles
    if (this.particles) {
      this.particles.rotation.y -= delta * 0.03 * motionFactor;
      this.particles.rotation.x += delta * 0.02 * motionFactor;

      // In THINKING state, particles swirl faster
      if (this.state === 'THINKING' || this.state === 'PROCESSING') {
        this.particles.rotation.y -= delta * 0.15;
      }
    }

    // Render Scene
    if (this.renderer && this.scene && this.camera) {
      this.renderer.render(this.scene, this.camera);
    }
  }

  /**
   * Set the interactive reactor state
   * @param {string} state - IDLE | LISTENING | THINKING | PROCESSING | EXECUTING | VERIFYING | SPEAKING | RESPONDING | ERROR | OFFLINE
   */
  setState(state) {
    const s = (state || 'IDLE').toUpperCase();
    this.state = s;

    switch (s) {
      case 'LISTENING':
      case 'WAKE_WORD_DETECTED':
        this.targetSpeedMultiplier = 1.2;
        this.targetLightIntensity = 2.8;
        this.targetLightColor.setHex(0x00FFFF); // Intense Cyan
        break;

      case 'THINKING':
      case 'PROCESSING':
      case 'ANALYZING':
        this.targetSpeedMultiplier = 2.6; // High velocity convergence
        this.targetLightIntensity = 2.4;
        this.targetLightColor.setHex(0xA855F7); // Violet
        break;

      case 'EXECUTING':
        this.targetSpeedMultiplier = 2.0;
        this.targetLightIntensity = 2.2;
        this.targetLightColor.setHex(0x27D3FF); // Bright Cyan
        break;

      case 'VERIFYING':
        this.targetSpeedMultiplier = 1.4;
        this.targetLightIntensity = 2.0;
        this.targetLightColor.setHex(0x10B981); // Emerald Green
        break;

      case 'SPEAKING':
      case 'RESPONDING':
        this.targetSpeedMultiplier = 1.3;
        this.targetLightIntensity = 2.6;
        this.targetLightColor.setHex(0x34D399); // Soft Emerald / Mint
        break;

      case 'ERROR':
        this.targetSpeedMultiplier = 0.8;
        this.targetLightIntensity = 2.2;
        this.targetLightColor.setHex(0xEF4444); // Red Alert
        break;

      case 'OFFLINE':
        this.targetSpeedMultiplier = 0.3;
        this.targetLightIntensity = 0.8;
        this.targetLightColor.setHex(0xF59E0B); // Amber Standby
        break;

      case 'IDLE':
      default:
        this.targetSpeedMultiplier = 1.0;
        this.targetLightIntensity = 1.8;
        this.targetLightColor.setHex(0x27D3FF); // Standard JARVIS Cyan
        break;
    }
  }

  setAudioLevel(level) {
    this.audioLevel = Math.max(0.0, Math.min(1.0, level || 0.0));
  }

  setReducedMotion(reduced) {
    this.options.reducedMotion = !!reduced;
  }

  /**
   * Complete teardown and memory cleanup
   */
  destroy() {
    this.dispose();
  }

  dispose() {
    this.isDestroyed = true;

    if (this.animFrameId) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }

    if (this.onResize) {
      window.removeEventListener('resize', this.onResize);
    }

    if (this.onMouseMove) {
      window.removeEventListener('mousemove', this.onMouseMove);
    }

    if (this.motionListener && window.matchMedia) {
      window.matchMedia('(prefers-reduced-motion: reduce)').removeEventListener('change', this.motionListener);
    }

    // Dispose cached geometries and materials
    this.disposables.forEach((item) => {
      try {
        if (item && typeof item.dispose === 'function') {
          item.dispose();
        }
      } catch (e) {
        // Ignore disposal errors
      }
    });
    this.disposables = [];

    // Traverse and dispose everything left in scene
    if (this.scene) {
      this.scene.traverse((obj) => {
        if (obj.geometry) {
          obj.geometry.dispose();
        }
        if (obj.material) {
          if (Array.isArray(obj.material)) {
            obj.material.forEach((m) => m && m.dispose && m.dispose());
          } else {
            obj.material.dispose();
          }
        }
      });
    }

    if (this.renderer) {
      try {
        this.renderer.dispose();
        this.renderer.forceContextLoss();
      } catch (e) {
        // Ignore renderer disposal error
      }
      this.renderer = null;
    }

    this.scene = null;
    this.camera = null;
  }
}
