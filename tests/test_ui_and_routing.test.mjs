import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

describe('Root Routing and Navigation Architecture', () => {

  test('index.html contains immediate redirection to assistant.html', () => {
    const indexPath = path.resolve('index.html');
    const content = fs.readFileSync(indexPath, 'utf-8');

    assert.ok(content.includes('assistant.html'), 'index.html must reference assistant.html for redirection');
    assert.ok(content.includes('http-equiv="refresh"'), 'index.html must have meta refresh tag');
    assert.ok(content.includes('window.location.replace'), 'index.html must have window.location.replace to preserve history');
  });

  test('vite.config.js has server redirect plugin from / to /assistant.html', () => {
    const configPath = path.resolve('vite.config.js');
    const content = fs.readFileSync(configPath, 'utf-8');

    assert.ok(content.includes("Location: '/assistant.html'"), 'vite.config.js must redirect root route / to /assistant.html');
  });

  test('assistant.html has Home/Dashboard removed from primary sidebar navigation', () => {
    const assistantPath = path.resolve('assistant.html');
    const content = fs.readFileSync(assistantPath, 'utf-8');

    // Check that primary navigation does NOT contain a link to Home / index.html
    const primaryNavMatch = content.match(/<nav class="space-y-1\.5 font-sans">([\s\S]*?)<\/nav>/);
    assert.ok(primaryNavMatch, 'Must find primary navigation in assistant.html');
    const navContent = primaryNavMatch[1];

    assert.ok(!navContent.includes('href="index.html"'), 'Primary navigation in assistant.html must not contain href="index.html"');
    assert.ok(!navContent.includes('>Home<'), 'Primary navigation in assistant.html must not contain Home link');
    assert.ok(navContent.includes('href="assistant.html"'), 'Primary navigation must contain Assistant link');
    assert.ok(navContent.includes('href="activity.html"'), 'Primary navigation must contain History link');
    assert.ok(navContent.includes('href="settings.html"'), 'Primary navigation must contain Settings link');
  });

  test('tasks.html has Dashboard removed from primary navigation', () => {
    const content = fs.readFileSync(path.resolve('tasks.html'), 'utf-8');
    const navMatch = content.match(/<nav class="flex flex-col gap-1 mt-2">([\s\S]*?)<\/nav>/);
    assert.ok(navMatch);
    assert.ok(!navMatch[1].includes('href="index.html"'));
    assert.ok(navMatch[1].includes('href="assistant.html"'));
  });

  test('projects.html has Dashboard removed from primary navigation', () => {
    const content = fs.readFileSync(path.resolve('projects.html'), 'utf-8');
    const navMatch = content.match(/<nav class="space-y-1">([\s\S]*?)<\/nav>/);
    assert.ok(navMatch);
    assert.ok(!navMatch[1].includes('href="index.html"'));
    assert.ok(navMatch[1].includes('href="assistant.html"'));
  });

  test('memory.html has Dashboard removed from primary navigation', () => {
    const content = fs.readFileSync(path.resolve('memory.html'), 'utf-8');
    const navMatch = content.match(/<nav class="space-y-1">([\s\S]*?)<\/nav>/);
    assert.ok(navMatch);
    assert.ok(!navMatch[1].includes('href="index.html"'));
    assert.ok(navMatch[1].includes('href="assistant.html"'));
  });

  test('activity.html has Home removed from primary navigation', () => {
    const content = fs.readFileSync(path.resolve('activity.html'), 'utf-8');
    const navMatch = content.match(/<nav class="space-y-1\.5 font-sans">([\s\S]*?)<\/nav>/);
    assert.ok(navMatch);
    assert.ok(!navMatch[1].includes('href="index.html"'));
    assert.ok(navMatch[1].includes('href="assistant.html"'));
  });

  test('settings.html has Home/Dashboard removed from navigation', () => {
    const content = fs.readFileSync(path.resolve('settings.html'), 'utf-8');
    assert.ok(!content.includes('href="index.html"'), 'settings.html must not contain href="index.html"');
  });

  test('assistant.html contains 3D canvas and wake word controller bindings', () => {
    const content = fs.readFileSync(path.resolve('assistant.html'), 'utf-8');
    assert.ok(content.includes('id="jarvis-core-canvas"'), 'Must have 3D core canvas element');
    assert.ok(content.includes('JarvisCoreCanvas'), 'Must import JarvisCoreCanvas component');
    assert.ok(content.includes('WakeWordController'), 'Must import WakeWordController service');
    assert.ok(content.includes('btn-top-wake-word'), 'Must have top wake word toggle button');
    assert.ok(content.includes('btn-stop-speaking'), 'Must have stop speaking button for TTS');
  });

});
