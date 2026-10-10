import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

describe('ChatGPT-Style Fixed Bottom Composer & Independent Scrolling UI', () => {
  const assistantPath = path.resolve('assistant.html');
  const content = fs.readFileSync(assistantPath, 'utf-8');

  test('assistant.html contains fixed bottom composer dock with dark glassmorphism styling', () => {
    assert.ok(content.includes('id="bottom-composer-dock"'), 'Must have bottom composer dock container');
    assert.ok(content.includes('footer id="bottom-composer-dock"'), 'Bottom composer dock must be a semantic footer or dock');
    assert.ok(content.includes('backdrop-blur'), 'Bottom composer dock must have backdrop-blur styling');
  });

  test('composer provides multiline textarea with "Message JARVIS…" placeholder', () => {
    assert.ok(content.includes('<textarea'), 'Input must be a multiline textarea element');
    assert.ok(content.includes('id="agent-input-buffer"'), 'Textarea must have id="agent-input-buffer"');
    assert.ok(content.includes('placeholder="Message JARVIS…"'), 'Textarea must have placeholder "Message JARVIS…"');
  });

  test('composer supports auto-resizing and Enter / Shift+Enter handling', () => {
    assert.ok(content.includes('autoResizeComposer'), 'Must define autoResizeComposer function');
    assert.ok(content.includes("e.key === 'Enter' && !e.shiftKey"), 'Enter sends message without shiftKey');
    assert.ok(content.includes('resize-none'), 'Textarea must disable default manual resize handle in favor of auto-resize');
  });

  test('persistent microphone button is docked inside bottom composer beside send button', () => {
    const bottomDockMatch = content.match(/<footer id="bottom-composer-dock"[\s\S]*?<\/footer>/);
    assert.ok(bottomDockMatch, 'Must find bottom composer dock in assistant.html');
    const dockHtml = bottomDockMatch[0];

    assert.ok(dockHtml.includes('id="btn-microphone"'), 'Microphone button must be inside bottom composer dock');
    assert.ok(dockHtml.includes('id="btn-transmit"'), 'Transmit send button must be inside bottom composer dock');
    assert.ok(dockHtml.includes('id="audio-wave-meter"'), 'Audio wave meter must be accessible in bottom composer dock');
    assert.ok(dockHtml.includes('id="btn-screen-capture"'), 'Screen capture trigger must be accessible in bottom composer dock');
  });

  test('independent conversation scroll area exists above bottom composer', () => {
    assert.ok(content.includes('id="conversation-scroll-wrapper"'), 'Must have dedicated scrollable wrapper');
    assert.ok(content.includes('overflow-y-auto'), 'Scroll wrapper must have overflow-y-auto');
    assert.ok(content.includes('id="chat-messages-container"'), 'Messages container must reside within scroll wrapper');
  });

  test('preserves reading position on scroll up and provides floating "Scroll to latest" button', () => {
    assert.ok(content.includes('id="btn-scroll-latest"'), 'Must have floating scroll to latest button');
    assert.ok(content.includes('scrollToLatestMessage'), 'Must have scrollToLatestMessage function');
    assert.ok(content.includes('isUserScrolledUp'), 'Must track whether user is scrolled up to prevent unwanted auto-scrolling');
  });

  test('prevents duplicate submissions and preserves 3D holographic core in responsive top HUD', () => {
    assert.ok(content.includes('isTransmitting'), 'Must enforce transmission lock against duplicate clicks/enters');
    assert.ok(content.includes('id="jarvis-core-hud"'), 'Must have top HUD section for 3D core');
    assert.ok(content.includes('id="jarvis-core-canvas"'), 'Must retain 3D holographic core canvas');
    assert.ok(content.includes('id="status-dot"'), 'Must retain dynamic status dot');
    assert.ok(content.includes('id="status-text"'), 'Must retain dynamic status text');
  });

  test('suggestion chips include natural language music, browser, and task examples', () => {
    assert.ok(content.includes('Play Wake Me Up When September Ends by Green Day'), 'Must suggest music command');
    assert.ok(content.includes('Pause the music'), 'Must suggest pause command');
    assert.ok(content.includes('Open Chrome and search for machine learning'), 'Must suggest browser search command');
    assert.ok(content.includes('Create a task to study DBMS tomorrow'), 'Must suggest task creation command');
  });
});
