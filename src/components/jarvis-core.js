/**
 * JARVIS 3D Holographic Core Canvas Engine
 * High-performance 3D perspective projection renderer for the central AI energy orb,
 * layered orbital gyroscope geometry, 3D particle dust field, and state-reactive lighting.
 */

export class JarvisCoreCanvas {
  constructor(canvasElement, options = {}) {
    this.canvas = canvasElement;
    this.ctx = canvasElement.getContext('2d');
    this.options = {
      reducedMotion: false,
      ...options
    };

    this.state = 'IDLE'; // IDLE, LISTENING, PROCESSING, EXECUTING, VERIFYING, RESPONDING, ERROR, OFFLINE
    this.audioLevel = 0.0; // 0.0 to 1.0 (reactive microphone amplitude)
    this.time = 0;
    this.animFrameId = null;
    this.isDestroyed = false;

    // 3D Projection & Camera settings
    this.width = 360;
    this.height = 360;
    this.cx = 180;
    this.cy = 180;
    this.focalLength = 320;

    // Interactive mouse parallax
    this.targetTiltX = 0;
    this.targetTiltY = 0;
    this.tiltX = 0;
    this.tiltY = 0;

    // Scanning laser position for VERIFYING state
    this.scanY = -60;
    this.scanDirection = 1;

    // Acoustic shockwave rings for LISTENING and RESPONDING
    this.pulseRings = [
      { radius: 20, maxRadius: 160, speed: 1.8, opacity: 0.8 },
      { radius: 60, maxRadius: 160, speed: 1.8, opacity: 0.5 },
      { radius: 100, maxRadius: 160, speed: 1.8, opacity: 0.2 }
    ];

    // Generate 3D Particle Dust Field (70 particles in spherical shell)
    this.particles = [];
    for (let i = 0; i < 70; i++) {
      const radius = 55 + Math.random() * 95;
      const theta = Math.random() * Math.PI * 2;
      const phi = (Math.random() - 0.5) * Math.PI;
      this.particles.push({
        x: radius * Math.cos(phi) * Math.cos(theta),
        y: radius * Math.sin(phi),
        z: radius * Math.cos(phi) * Math.sin(theta),
        size: 0.8 + Math.random() * 1.6,
        alpha: 0.2 + Math.random() * 0.7,
        speed: 0.002 + Math.random() * 0.005,
        axis: Math.random() > 0.5 ? 1 : -1
      });
    }

    this.initCanvas();
    this.bindEvents();
    this.startLoop();
  }

  initCanvas() {
    if (!this.canvas) return;
    const rect = this.canvas.getBoundingClientRect();
    this.width = rect.width || 360;
    this.height = rect.height || 360;
    this.cx = this.width / 2;
    this.cy = this.height / 2;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = this.width * dpr;
    this.canvas.height = this.height * dpr;
    this.ctx.resetTransform?.();
    this.ctx.scale(dpr, dpr);
  }

  bindEvents() {
    this.onResize = () => this.initCanvas();
    window.addEventListener('resize', this.onResize);

    this.onMouseMove = (e) => {
      if (!this.canvas) return;
      const rect = this.canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left - rect.width / 2;
      const my = e.clientY - rect.top - rect.height / 2;
      this.targetTiltX = (my / rect.height) * 0.45;
      this.targetTiltY = (-mx / rect.width) * 0.45;
    };
    window.addEventListener('mousemove', this.onMouseMove);

    // Reduced motion preference
    if (window.matchMedia) {
      const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
      if (motionQuery.matches) this.options.reducedMotion = true;
      this.motionListener = (e) => {
        this.options.reducedMotion = e.matches;
      };
      motionQuery.addEventListener('change', this.motionListener);
    }
  }

  setState(state) {
    this.state = (state || 'IDLE').toUpperCase();
  }

  setAudioLevel(level) {
    this.audioLevel = Math.max(0, Math.min(1, level || 0));
  }

  setReducedMotion(enabled) {
    this.options.reducedMotion = !!enabled;
  }

  // 3D perspective projection helper
  project(x, y, z, rotX, rotY, rotZ) {
    // Rotation around X axis
    const cosX = Math.cos(rotX), sinX = Math.sin(rotX);
    const y1 = y * cosX - z * sinX;
    const z1 = y * sinX + z * cosX;

    // Rotation around Y axis
    const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
    const x2 = x * cosY + z1 * sinY;
    const z2 = -x * sinY + z1 * cosY;

    // Rotation around Z axis
    const cosZ = Math.cos(rotZ), sinZ = Math.sin(rotZ);
    const x3 = x2 * cosZ - y1 * sinZ;
    const y3 = x2 * sinZ + y1 * cosZ;
    const z3 = z2;

    const scale = this.focalLength / (this.focalLength + z3);
    return {
      x: this.cx + x3 * scale,
      y: this.cy + y3 * scale,
      scale: scale,
      z: z3
    };
  }

  startLoop() {
    const render = () => {
      if (this.isDestroyed) return;
      this.draw();
      this.animFrameId = requestAnimationFrame(render);
    };
    this.animFrameId = requestAnimationFrame(render);
  }

  draw() {
    const ctx = this.ctx;
    const width = this.width;
    const height = this.height;
    ctx.clearRect(0, 0, width, height);

    // Smooth mouse tilt interpolation
    this.tiltX += (this.targetTiltX - this.tiltX) * 0.05;
    this.tiltY += (this.targetTiltY - this.tiltY) * 0.05;

    const motionScale = this.options.reducedMotion ? 0.2 : 1.0;
    this.time += 0.016 * motionScale;

    // Determine state color theme & rotational speeds
    let baseColor = 'rgba(39, 211, 255, ';     // Electric Cyan (#27D3FF)
    let accentColor = 'rgba(209, 188, 255, '; // Soft Violet (#D1BCFF)
    let coreGlow = '#27D3FF';
    let ringSpeed = 1.0;

    switch (this.state) {
      case 'LISTENING':
      case 'WAKE_WORD_DETECTED':
        baseColor = 'rgba(39, 211, 255, ';
        accentColor = 'rgba(125, 235, 255, ';
        coreGlow = '#27D3FF';
        ringSpeed = 1.4;
        break;
      case 'PROCESSING':
      case 'THINKING':
        baseColor = 'rgba(168, 85, 247, '; // Electric Violet
        accentColor = 'rgba(39, 211, 255, ';
        coreGlow = '#A855F7';
        ringSpeed = 3.2;
        break;
      case 'EXECUTING':
        baseColor = 'rgba(6, 182, 212, '; // Bright Cyan / Teal
        accentColor = 'rgba(59, 130, 246, ';
        coreGlow = '#06B6D4';
        ringSpeed = 2.4;
        break;
      case 'VERIFYING':
        baseColor = 'rgba(16, 185, 129, '; // Scanning Emerald
        accentColor = 'rgba(39, 211, 255, ';
        coreGlow = '#10B981';
        ringSpeed = 1.6;
        break;
      case 'RESPONDING':
      case 'SPEAKING':
      case 'DONE':
        baseColor = 'rgba(52, 211, 153, '; // Emerald / Mint
        accentColor = 'rgba(39, 211, 255, ';
        coreGlow = '#34D399';
        ringSpeed = 1.2;
        break;
      case 'ERROR':
        baseColor = 'rgba(239, 68, 68, '; // Warning Red
        accentColor = 'rgba(251, 146, 60, ';
        coreGlow = '#EF4444';
        ringSpeed = 0.6;
        break;
      case 'OFFLINE':
        baseColor = 'rgba(245, 158, 11, '; // Amber Standby
        accentColor = 'rgba(100, 116, 139, ';
        coreGlow = '#F59E0B';
        ringSpeed = 0.3;
        break;
      default: // IDLE
        baseColor = 'rgba(39, 211, 255, ';
        accentColor = 'rgba(147, 197, 253, ';
        coreGlow = '#27D3FF';
        ringSpeed = 1.0;
        break;
    }

    // 1. Ambient Background Volumetric Flare
    const bgGrad = ctx.createRadialGradient(this.cx, this.cy, 10, this.cx, this.cy, 140);
    const ambientAlpha = this.state === 'LISTENING' ? 0.25 + this.audioLevel * 0.2 : (this.state === 'PROCESSING' ? 0.22 : 0.12);
    bgGrad.addColorStop(0, `${baseColor}${ambientAlpha})`);
    bgGrad.addColorStop(0.5, `${accentColor}${ambientAlpha * 0.4})`);
    bgGrad.addColorStop(1, 'rgba(6, 8, 12, 0)');
    ctx.fillStyle = bgGrad;
    ctx.beginPath();
    ctx.arc(this.cx, this.cy, 150, 0, Math.PI * 2);
    ctx.fill();

    // 2. Pulse / Shockwave Rings (LISTENING, RESPONDING)
    if (this.state === 'LISTENING' || this.state === 'RESPONDING' || this.state === 'WAKE_WORD_DETECTED') {
      this.drawPulseRings(ctx, baseColor);
    }

    // 3. Draw Back Half of 3D Orbital Rings (z > 0)
    const t = this.time * ringSpeed;
    this.drawOrbitalRings(ctx, t, baseColor, accentColor, true);

    // 4. Draw Back Half of 3D Particles (z > 0)
    this.drawParticles(ctx, t, baseColor, true);

    // 5. Draw Central Radiant Energy Core Orb
    this.drawCentralCore(ctx, coreGlow);

    // 6. Draw Scanning Laser Beam (VERIFYING state)
    if (this.state === 'VERIFYING') {
      this.drawScanningLaser(ctx);
    }

    // 7. Draw Front Half of 3D Orbital Rings (z <= 0)
    this.drawOrbitalRings(ctx, t, baseColor, accentColor, false);

    // 8. Draw Front Half of 3D Particles (z <= 0)
    this.drawParticles(ctx, t, baseColor, false);

    // 9. Structured Reticle (EXECUTING state)
    if (this.state === 'EXECUTING') {
      this.drawExecutionReticle(ctx, t);
    }
  }

  // Draw expanding acoustic shockwave rings
  drawPulseRings(ctx, baseColor) {
    const pulseFactor = this.state === 'LISTENING' ? 1.0 + this.audioLevel * 1.5 : 1.0;
    this.pulseRings.forEach((ring) => {
      ring.radius += ring.speed * pulseFactor;
      if (ring.radius > ring.maxRadius) {
        ring.radius = 24;
      }
      const alpha = Math.max(0, 1 - (ring.radius / ring.maxRadius)) * ring.opacity;
      ctx.beginPath();
      ctx.arc(this.cx, this.cy, ring.radius, 0, Math.PI * 2);
      ctx.strokeStyle = `${baseColor}${alpha.toFixed(2)})`;
      ctx.lineWidth = 1.2;
      ctx.stroke();
    });
  }

  // Draw 3D Orbital Gyroscope Rings with depth splitting
  drawOrbitalRings(ctx, t, baseColor, accentColor, drawBack) {
    const rings = [
      // Ring 1: Equatorial Gyroscope
      {
        radius: 88,
        rotX: 0.45 + this.tiltX,
        rotY: t * 0.8 + this.tiltY,
        rotZ: 0.15,
        color: baseColor,
        dash: [6, 4],
        width: 1.5,
        nodes: 0
      },
      // Ring 2: Polar Gyroscope (counter-rotating)
      {
        radius: 110,
        rotX: -0.7 + this.tiltX,
        rotY: -t * 0.65 + this.tiltY,
        rotZ: t * 0.2,
        color: accentColor,
        dash: [],
        width: 1.2,
        nodes: 4
      },
      // Ring 3: Oblique Gyroscope with telemetry ticks
      {
        radius: 132,
        rotX: 0.9 + this.tiltX,
        rotY: t * 0.4 + this.tiltY,
        rotZ: -t * 0.35,
        color: baseColor,
        dash: [12, 6, 2, 6],
        width: 1.0,
        nodes: 6
      }
    ];

    rings.forEach((ring) => {
      const numSegments = 64;
      const points = [];

      for (let i = 0; i <= numSegments; i++) {
        const angle = (i / numSegments) * Math.PI * 2;
        const x = ring.radius * Math.cos(angle);
        const y = 0;
        const z = ring.radius * Math.sin(angle);
        const proj = this.project(x, y, z, ring.rotX, ring.rotY, ring.rotZ);
        points.push(proj);
      }

      ctx.save();
      ctx.lineWidth = ring.width;
      if (ring.dash.length > 0) ctx.setLineDash(ring.dash);

      for (let i = 0; i < points.length - 1; i++) {
        const p1 = points[i];
        const p2 = points[i + 1];
        const isBack = ((p1.z + p2.z) / 2) > 0;

        if (isBack === drawBack) {
          ctx.beginPath();
          ctx.moveTo(p1.x, p1.y);
          ctx.lineTo(p2.x, p2.y);
          const alpha = drawBack ? 0.22 : (this.state === 'PROCESSING' ? 0.95 : 0.75);
          ctx.strokeStyle = `${ring.color}${alpha})`;
          ctx.stroke();
        }
      }
      ctx.restore();

      // Glowing Node Ticks on ring perimeter
      if (ring.nodes > 0) {
        for (let n = 0; n < ring.nodes; n++) {
          const angle = (n / ring.nodes) * Math.PI * 2 + t * 0.5;
          const x = ring.radius * Math.cos(angle);
          const y = 0;
          const z = ring.radius * Math.sin(angle);
          const p = this.project(x, y, z, ring.rotX, ring.rotY, ring.rotZ);
          const isBack = p.z > 0;

          if (isBack === drawBack) {
            const nodeRadius = drawBack ? 1.8 * p.scale : 3.0 * p.scale;
            ctx.beginPath();
            ctx.arc(p.x, p.y, nodeRadius, 0, Math.PI * 2);
            ctx.fillStyle = drawBack ? 'rgba(255, 255, 255, 0.4)' : '#FFFFFF';
            ctx.shadowColor = coreGlowHex(this.state);
            ctx.shadowBlur = drawBack ? 2 : 8;
            ctx.fill();
            ctx.shadowBlur = 0;
          }
        }
      }
    });
  }

  // Draw 3D Particle Cloud with depth sorting
  drawParticles(ctx, t, baseColor, drawBack) {
    this.particles.forEach((p) => {
      // Rotate particle around Y-axis
      const rotY = t * p.speed * p.axis + this.tiltY;
      const rotX = this.tiltX;
      const proj = this.project(p.x, p.y, p.z, rotX, rotY, 0);
      const isBack = proj.z > 0;

      if (isBack === drawBack) {
        const alpha = drawBack ? (p.alpha * 0.35) : Math.min(1, p.alpha * 1.2);
        const size = Math.max(0.6, p.size * proj.scale);
        ctx.beginPath();
        ctx.arc(proj.x, proj.y, size, 0, Math.PI * 2);
        ctx.fillStyle = `${baseColor}${alpha.toFixed(2)})`;
        ctx.fill();
      }
    });
  }

  // Draw Central Radiant Energy Core Orb
  drawCentralCore(ctx, coreGlow) {
    const breathe = Math.sin(this.time * 2.2);
    let orbRadius = 46 + breathe * 2.5;

    // React to real-time audio amplitude
    if (this.state === 'LISTENING') {
      orbRadius += this.audioLevel * 12;
    } else if (this.state === 'PROCESSING') {
      orbRadius += Math.sin(this.time * 6) * 3;
    }

    // Outer corona glow
    const outerGrad = ctx.createRadialGradient(this.cx, this.cy, orbRadius * 0.7, this.cx, this.cy, orbRadius * 1.5);
    outerGrad.addColorStop(0, coreGlow);
    outerGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.save();
    ctx.globalCompositeOperation = 'screen';
    ctx.fillStyle = outerGrad;
    ctx.beginPath();
    ctx.arc(this.cx, this.cy, orbRadius * 1.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    // Core 3D Sphere Surface
    const coreGrad = ctx.createRadialGradient(
      this.cx - orbRadius * 0.35,
      this.cy - orbRadius * 0.35,
      orbRadius * 0.1,
      this.cx,
      this.cy,
      orbRadius
    );

    if (this.state === 'PROCESSING' || this.state === 'THINKING') {
      coreGrad.addColorStop(0, '#FFFFFF');
      coreGrad.addColorStop(0.35, '#E9D5FF');
      coreGrad.addColorStop(0.65, '#A855F7');
      coreGrad.addColorStop(0.9, '#3B0764');
      coreGrad.addColorStop(1, '#0F031E');
    } else if (this.state === 'RESPONDING' || this.state === 'SPEAKING' || this.state === 'DONE') {
      coreGrad.addColorStop(0, '#FFFFFF');
      coreGrad.addColorStop(0.35, '#A7F3D0');
      coreGrad.addColorStop(0.65, '#10B981');
      coreGrad.addColorStop(0.9, '#065F46');
      coreGrad.addColorStop(1, '#022C22');
    } else if (this.state === 'ERROR') {
      coreGrad.addColorStop(0, '#FFFFFF');
      coreGrad.addColorStop(0.35, '#FECACA');
      coreGrad.addColorStop(0.65, '#EF4444');
      coreGrad.addColorStop(0.9, '#991B1B');
      coreGrad.addColorStop(1, '#450A0A');
    } else if (this.state === 'OFFLINE') {
      coreGrad.addColorStop(0, '#FFFFFF');
      coreGrad.addColorStop(0.35, '#FDE68A');
      coreGrad.addColorStop(0.65, '#F59E0B');
      coreGrad.addColorStop(0.9, '#92400E');
      coreGrad.addColorStop(1, '#3A1C04');
    } else {
      // Electric Cyan (IDLE, LISTENING, EXECUTING)
      coreGrad.addColorStop(0, '#FFFFFF');
      coreGrad.addColorStop(0.3, '#BAF3FF');
      coreGrad.addColorStop(0.6, '#27D3FF');
      coreGrad.addColorStop(0.85, '#0D4B68');
      coreGrad.addColorStop(1, '#041523');
    }

    ctx.save();
    ctx.beginPath();
    ctx.arc(this.cx, this.cy, orbRadius, 0, Math.PI * 2);
    ctx.fillStyle = coreGrad;
    ctx.shadowColor = coreGlow;
    ctx.shadowBlur = this.state === 'LISTENING' ? 35 : 20;
    ctx.fill();
    ctx.restore();

    // Internal Plasma Rings (inner geometric telemetry)
    ctx.save();
    ctx.beginPath();
    ctx.arc(this.cx, this.cy, orbRadius * 0.65, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.45)';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(this.cx, this.cy, orbRadius * 0.4, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.65)';
    ctx.setLineDash([6, 2]);
    ctx.stroke();
    ctx.restore();
  }

  // Draw scanning laser beam (VERIFYING state)
  drawScanningLaser(ctx) {
    this.scanY += 1.8 * this.scanDirection;
    if (this.scanY > 55) {
      this.scanY = 55;
      this.scanDirection = -1;
    } else if (this.scanY < -55) {
      this.scanY = -55;
      this.scanDirection = 1;
    }

    const y = this.cy + this.scanY;
    const laserWidth = 110;

    const grad = ctx.createLinearGradient(this.cx - laserWidth / 2, y, this.cx + laserWidth / 2, y);
    grad.addColorStop(0, 'rgba(16, 185, 129, 0)');
    grad.addColorStop(0.2, 'rgba(16, 185, 129, 0.8)');
    grad.addColorStop(0.5, '#FFFFFF');
    grad.addColorStop(0.8, 'rgba(16, 185, 129, 0.8)');
    grad.addColorStop(1, 'rgba(16, 185, 129, 0)');

    ctx.save();
    ctx.beginPath();
    ctx.moveTo(this.cx - laserWidth / 2, y);
    ctx.lineTo(this.cx + laserWidth / 2, y);
    ctx.strokeStyle = grad;
    ctx.lineWidth = 2.5;
    ctx.shadowColor = '#10B981';
    ctx.shadowBlur = 12;
    ctx.stroke();

    // Scanner grid aura
    ctx.fillStyle = 'rgba(16, 185, 129, 0.08)';
    ctx.fillRect(this.cx - laserWidth / 2, this.cy - 50, laserWidth, 100);
    ctx.restore();
  }

  // Draw structured reticle (EXECUTING state)
  drawExecutionReticle(ctx, t) {
    ctx.save();
    ctx.translate(this.cx, this.cy);
    ctx.rotate(t * 0.8);

    ctx.strokeStyle = 'rgba(6, 182, 212, 0.65)';
    ctx.lineWidth = 1.2;
    ctx.setLineDash([10, 15]);

    // Outer bracket ring
    ctx.beginPath();
    ctx.arc(0, 0, 72, 0, Math.PI * 2);
    ctx.stroke();

    // Crosshair ticks
    ctx.setLineDash([]);
    const tickLen = 8;
    for (let i = 0; i < 4; i++) {
      const angle = (i * Math.PI) / 2;
      const x1 = Math.cos(angle) * 65;
      const y1 = Math.sin(angle) * 65;
      const x2 = Math.cos(angle) * (65 + tickLen);
      const y2 = Math.sin(angle) * (65 + tickLen);
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    }
    ctx.restore();
  }

  destroy() {
    this.isDestroyed = true;
    if (this.animFrameId) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
    if (this.onResize) window.removeEventListener('resize', this.onResize);
    if (this.onMouseMove) window.removeEventListener('mousemove', this.onMouseMove);
    if (this.motionListener && window.matchMedia) {
      window.matchMedia('(prefers-reduced-motion: reduce)').removeEventListener('change', this.motionListener);
    }
  }
}

function coreGlowHex(state) {
  switch (state) {
    case 'PROCESSING':
    case 'THINKING':
      return '#A855F7';
    case 'RESPONDING':
    case 'SPEAKING':
    case 'DONE':
      return '#34D399';
    case 'VERIFYING':
      return '#10B981';
    case 'ERROR':
      return '#EF4444';
    case 'OFFLINE':
      return '#F59E0B';
    default:
      return '#27D3FF';
  }
}
