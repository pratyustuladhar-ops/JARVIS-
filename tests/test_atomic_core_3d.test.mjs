import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

describe('Three.js 3D Atomic Reactor Core Integration', () => {
  const assistantPath = path.resolve('assistant.html');
  const assistantHtml = fs.readFileSync(assistantPath, 'utf-8');
  const atomicCorePath = path.resolve('src/components/atomic-core-3d.js');
  const atomicCoreJs = fs.readFileSync(atomicCorePath, 'utf-8');
  const packageJson = JSON.parse(fs.readFileSync(path.resolve('package.json'), 'utf-8'));

  test('Three.js is declared in package.json dependencies for offline bundling', () => {
    assert.ok(packageJson.dependencies, 'Dependencies field must exist in package.json');
    assert.ok(packageJson.dependencies.three, 'three must be in package.json dependencies');
  });

  test('AtomicCore3D component exports class and WebGL detector', () => {
    assert.ok(atomicCoreJs.includes('export class AtomicCore3D'), 'Must export AtomicCore3D class');
    assert.ok(atomicCoreJs.includes('export function isWebGLAvailable'), 'Must export isWebGLAvailable function');
    assert.ok(atomicCoreJs.includes("import * as THREE from 'three';"), 'Must import Three.js');
  });

  test('AtomicCore3D implements 6 elliptical orbits with distinct tilts and electrons', () => {
    assert.ok(atomicCoreJs.includes('ORBIT_CONFIGS'), 'Must define orbit configurations');
    assert.ok(atomicCoreJs.includes('buildOrbitsAndElectrons'), 'Must build orbits and moving electrons');
    assert.ok(atomicCoreJs.includes('electronMesh'), 'Must instantiate electron mesh for each orbit');
    assert.ok(atomicCoreJs.includes('trailMeshes'), 'Must instantiate glowing trail nodes behind electrons');
    assert.ok(atomicCoreJs.includes('NUCLEUS_PALETTE'), 'Must define multicolored glossy nucleus palette');
    assert.ok(atomicCoreJs.includes('buildNucleus'), 'Must build nucleus with glossy spheres');
    assert.ok(atomicCoreJs.includes('buildParticleField'), 'Must build ambient energy particles');
  });

  test('AtomicCore3D supports interactive reactor states and reduced motion', () => {
    assert.ok(atomicCoreJs.includes('setState(state)'), 'Must implement setState method');
    assert.ok(atomicCoreJs.includes('setReducedMotion'), 'Must implement setReducedMotion method');
    assert.ok(atomicCoreJs.includes('dispose()'), 'Must implement dispose method for resource cleanup');
    assert.ok(atomicCoreJs.includes('prefers-reduced-motion'), 'Must check prefers-reduced-motion media query');
  });

  test('assistant.html mounts 3D atomic centerpiece in central conversation hero area', () => {
    assert.ok(assistantHtml.includes('id="atomic-reactor-hero"'), 'Must contain atomic-reactor-hero container');
    assert.ok(assistantHtml.includes('id="atomic-core-3d-canvas"'), 'Must contain atomic-core-3d-canvas element');
    assert.ok(assistantHtml.includes('title="JARVIS 3D Atomic Reactor Core"'), 'Canvas must have descriptive title');
  });

  test('assistant.html imports and wires AtomicCore3D into application lifecycle', () => {
    assert.ok(assistantHtml.includes("import { AtomicCore3D } from './src/components/atomic-core-3d.js';"), 'Must import AtomicCore3D');
    assert.ok(assistantHtml.includes('atomicCore3D = new AtomicCore3D(atomicCanvasEl);'), 'Must instantiate AtomicCore3D on DOM load');
    assert.ok(assistantHtml.includes('atomicCore3D.setState(s);'), 'Must sync agent state to atomic reactor');
    assert.ok(assistantHtml.includes('atomicCore3D.dispose();'), 'Must dispose atomic reactor on beforeunload');
  });

  test('UI preservation: fixed bottom composer dock and compact sidebar remain intact', () => {
    // Fixed bottom composer preserved at the bottom
    assert.ok(assistantHtml.includes('footer id="bottom-composer-dock"'), 'Bottom composer dock must remain as footer');
    assert.ok(assistantHtml.includes('id="agent-input-buffer"'), 'Input buffer textarea preserved');
    assert.ok(assistantHtml.includes('id="btn-transmit"'), 'Transmit button preserved');
    assert.ok(assistantHtml.includes('id="btn-microphone"'), 'Microphone button preserved');

    // Sidebar navigation preserved
    assert.ok(assistantHtml.includes('href="assistant.html"'), 'Sidebar must have Assistant link');
    assert.ok(assistantHtml.includes('href="activity.html"'), 'Sidebar must have History link');
    assert.ok(assistantHtml.includes('href="settings.html"'), 'Sidebar must have Settings link');

    // No forbidden Stitch dashboard clutter
    assert.ok(!assistantHtml.includes('Operator Profile'), 'Must not include Stitch Operator Profile');
    assert.ok(!assistantHtml.includes('Execute Command panel'), 'Must not include Stitch Execute Command panel');
    assert.ok(!assistantHtml.includes('Telemetry filter'), 'Must not include Stitch Telemetry filter');
  });
});
