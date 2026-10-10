# JARVIS — Personal AI Operating System & Autonomous Agent

**JARVIS** is an Intelligent AI Personal Assistant and Autonomous Operating Agent.

JARVIS features a React + TypeScript tactical HUD, a high-performance FastAPI backend, a PostgreSQL persistence store, an autonomous AI Planner, an allowlisted Windows Local Agent, Step 9 Multimodal Vision Intelligence, and **Step 10 Hands-Free Wake Word System**.

---

## Capabilities & Architecture (Steps 1–10)

- **Frontend HUD**: React + TypeScript + Tailwind (Tactical HUD, Assistant, Dashboard, Tasks, Projects, Memory, Activity, Settings, CMS Center).
- **Backend Core**: FastAPI, SQLAlchemy, PostgreSQL, and Pydantic v2.
- **AI Agent Brain**:
  - Hybrid Intent Classifier (Rule-based, ML logistic regression, LLM fallback).
  - Context Retrieval Engine (Tasks, Projects, Relevant Memories, System Context, Visual Context).
  - Autonomous Multi-step Planner with chained tool decomposition.
  - Safe Tool Registry & Sandboxed Execution Enclave.
  - Verification Engine auditing every action before user response.
  - Conversational Synthesis with speech-ready text output.
- **Voice Intelligence (Step 7)**: Web Speech STT and neural TTS voice synthesis.
- **Windows Local Agent (Step 8)**: Authenticated, allowlisted local desktop agent on port 8001.
- **Multimodal Vision Intelligence (Step 9)**:
  - Screen capture (`LOCAL_CAPTURE_SCREEN` / `capture_screen`) — zero continuous surveillance, user-initiated only.
  - Vision Reasoning (`VISION_ANALYSIS`) & Screen Element Description.
  - OCR Text Extraction (`VISION_OCR`) from screenshots and error dialogs.
  - Pluggable Vision Providers (`mock`, `gemini`, `openai`).
- **Multi-Step AI Agent Planner (Step 9.1)**:
  - Intelligent Natural Language Command Decomposer (`and`, `then`, `after that`, `next`, `followed by`, `also`, `first ... then ...`).
  - Strict Pydantic Execution Plan Model with Step IDs, registered tools, arguments, and dependency graphs (`depends_on`).
  - Guaranteed Sequential Execution Engine with immediate failure halting (Step 2 never executes if Step 1 fails).
  - Step-by-Step Verification with PID tracking and persistence checking.
  - Loop & Step Limits (`MAX_PLAN_STEPS = 10`) and arbitrary command rejection (`powershell`, `cmd`, `bash`, `python`).
  - Granular Activity Logging (`PLAN_CREATED`, `STEP_STARTED`, `STEP_COMPLETED`, `STEP_VERIFIED`, `STEP_FAILED`, `PLAN_COMPLETED`, `PLAN_FAILED`).
  - Natural truthful response synthesis for success and partial/full failure.
- **Intelligent Browser Automation (Step 9.2)**:
  - Controlled browser automation service powered by Playwright with existing Microsoft Edge / Chrome installations.
  - 10 registered browser tools: `browser_open`, `browser_navigate`, `browser_get_page_info`, `browser_find_element`, `browser_fill_input`, `browser_click_element`, `browser_press_key`, `browser_get_text`, `browser_wait_for_state`, `browser_close`.
  - Strict URL Security & SSRF Protection: HTTP/HTTPS scheme enforcement, loopback/private/metadata IP blocking, DNS rebinding prevention, route interception, credential redaction.
  - Dedicated isolated browser profiles (`jarvis_browser_profiles/<session_id>`) protecting user's personal browser data.
  - End-to-end multi-step web interaction (e.g. YouTube & Google search workflows) with independent state verification.
  - Prompt injection immunity: untrusted webpage text is treated strictly as data and cannot hijack agent tool dispatching.
- **Hands-Free Wake Word (Step 10)**:
  - Configurable wake phrase (`"Hey JARVIS"`).
  - Modular Wake Word Engine Abstraction (`BaseWakeWordProvider`, `LocalKeywordSpotterProvider`, `PorcupineWakeWordProvider`, `MockWakeWordProvider`).
  - Local on-device detection without uploading continuous audio streams to backend/cloud.
  - 10-state Voice State Machine (`IDLE` -> `WAKE_WORD_LISTENING` -> `WAKE_WORD_DETECTED` -> `LISTENING` -> `PROCESSING` -> `ANALYZING` -> `EXECUTING` -> `VERIFYING` -> `RESPONDING` -> `WAKE_WORD_LISTENING`).
  - Configurable wake acknowledgment response (`"Yes?"` or `"I'm listening."`).
  - Command listening window with 8-second configurable silence timeout (`"I didn't hear a command."`).
  - Auto-resume follow-up window (8 seconds) for chained voice commands.
  - Echo loop & self-activation prevention: detector paused during TTS playback and resumed after audio clear.
  - Windows Local Agent desktop wake word integration.
  - Strict privacy: zero raw microphone audio stored in database or activity audit logs.

---

## Step 9.1 Architecture: Multi-Step AI Agent Planner

```
USER
 ↓
Intent Detection (Hybrid: Rule + MultiStepDecomposer + ML + Fallback)
 ↓
Context Retrieval (Tasks, Projects, Memories, Settings)
 ↓
MULTI-STEP PLANNER (Pydantic Dependency Graph & Tool Allowlist)
 ↓
Structured Execution Plan (PlanStep: tool, arguments, depends_on)
 ↓
Tool Registry (Allowlisted System, Local Windows, Task, & Vision Tools)
 ↓
Sequential Executor
 ↓
Step Verification (Database State / Local Process PID & Running Check)
 ↓
Next Step (Halts immediately if prior step execution or verification fails)
 ↓
Final Verification & Granular Activity Logging
 ↓
Response Generator (Truthful natural status synthesis)
 ↓
USER
```

### Supported Multi-Step Examples:
1. `"Open Chrome and open YouTube."` → Step 1: `LOCAL_OPEN_APPLICATION(chrome)` → Verify → Step 2: `LOCAL_OPEN_URL(https://youtube.com)` → Verify → Response: `"Done. Chrome is open and YouTube is open."`
2. `"Open Notepad and Calculator."` → Step 1: `LOCAL_OPEN_APPLICATION(notepad)` → Verify → Step 2: `LOCAL_OPEN_APPLICATION(calculator)` → Verify
3. `"Open Chrome and Edge."` → Step 1: `LOCAL_OPEN_APPLICATION(chrome)` → Verify → Step 2: `LOCAL_OPEN_APPLICATION(edge)` → Verify
4. `"Open Chrome, then open YouTube, then open Spotify."` → 3 sequential verified steps
5. `"Create a task to study DBMS and open VS Code."` → Step 1: `TASK_CREATE` → Verify → Step 2: `LOCAL_OPEN_APPLICATION(vscode)` → Verify
6. `"Open VS Code then open my project folder."` → Step 1: `LOCAL_OPEN_APPLICATION(vscode)` → Verify → Step 2: `LOCAL_OPEN_FOLDER(Documents)` → Verify

### Safety & Loop Guarantees:
- **Sequential Execution**: Step 2 depends on Step 1 (`depends_on: [1]`). If Step 1 fails, Step 2 is marked `SKIPPED` and NEVER executed.
- **Truthful Failure Reporting**: `"I couldn't open Chrome, so I didn't continue with the next step."`
- **Security Enclave**: Rejects arbitrary shell execution (`powershell`, `cmd`, `bash`, `python`, `shell`).
- **Loop Protection**: `MAX_PLAN_STEPS = 10`. Any plan exceeding 10 steps is rejected.

---

## Step 10 Architecture: Hands-Free Wake Word Flow

```
Microphone
    ↓
Local Wake Word Detector (Browser / Desktop Agent)
    ↓ (Listens locally; NO continuous audio upload)
"Hey JARVIS" detected
    ↓
Activate JARVIS (State: WAKE_WORD_DETECTED)
    ↓
Verbal Acknowledgment ("Yes?")
    ↓ (Detector PAUSED during TTS to prevent echo loops)
Command Listening Window (State: LISTENING, 8s timeout)
    ↓
Speech Recognition (STT)
    ↓
POST /api/v1/assistant/message
    ↓
Existing AI Brain (Intent → Planner → Tool Registry)
    ↓
Execution & Verification (Windows Local Agent / Tools / Vision)
    ↓
TTS Spoken Response (State: RESPONDING)
    ↓
Follow-Up Window (8s) / Return to WAKE_WORD_LISTENING
```

---

## Configuration & Environment Variables

Configure hands-free wake word parameters via environment variables or the **Settings Console**:

| Variable | Default | Description |
|---|---|---|
| `WAKE_WORD_ENABLED` | `false` | Master toggle for hands-free wake word mode |
| `WAKE_WORD_PROVIDER` | `local` | Wake word provider (`local`, `porcupine`, `mock`) |
| `WAKE_WORD` | `hey_jarvis` | Internal identifier for wake word |
| `WAKE_PHRASE` | `Hey JARVIS` | Spoken phrase that activates JARVIS |
| `WAKE_ACKNOWLEDGMENT` | `Yes?` | TTS phrase spoken upon wake activation |
| `COMMAND_TIMEOUT_SECONDS` | `8` | Listening duration before silence timeout |
| `FOLLOW_UP_TIMEOUT_SECONDS` | `8` | Follow-up window duration for chained commands |
| `AUTO_RESUME_LISTENING` | `true` | Automatically enter follow-up window after speech |
| `WAKE_WORD_SENSITIVITY` | `0.7` | Confidence threshold for phrase spotting (0.1–1.0) |
| `PORCUPINE_ACCESS_KEY` | `""` | Optional Picovoice API key if using Porcupine provider |

---

## Privacy & Security Model

- **No Continuous Uploading**: The microphone is processed locally on the client machine. Zero continuous audio data is sent to the FastAPI backend or external AI cloud providers.
- **Zero Raw Audio Storage**: Neither database tables nor audit logs store audio waveforms, PCM buffers, or speech recordings. Only structured metadata (timestamp, event type, duration) is retained.
- **Self-Activation Prevention**: Wake detection is explicitly paused during TTS audio playback, preventing acoustic feedback loops.
- **No Arbitrary Execution**: Wake-word activation only activates the assistant and does not bypass existing authorization, tool registries, or allowlists.

---

## Quick Start: How to Run JARVIS

### 1. Start the Windows Local Agent (Port 8001)
```powershell
python local_agent/agent.py
```

### 2. Start the JARVIS Backend Core (Port 8000)
```powershell
cd jarvis-backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 3. Start the Frontend HUD (Port 5173)
```powershell
npm run dev
```

Visit the application in your browser:
- **Assistant HUD**: `http://localhost:5173/assistant.html`
- **Tactical Dashboard**: `http://localhost:5173/index.html`
- **Settings Console**: `http://localhost:5173/settings.html`
- **Dynamic CMS / Admin Panel**: `http://localhost:5173/cms.html`
- **FastAPI Interactive Docs**: `http://127.0.0.1:8000/docs`

---

## How to Test Hands-Free "Hey JARVIS"

1. Open `http://localhost:5173/assistant.html`.
2. In the VOX-7 audio interface header, click **WAKE WORD: OFF** to toggle it to **WAKE WORD: ON** (or enable it in Settings under Category 11: Voice & Wake Word).
3. Allow browser microphone access when prompted.
4. The HUD will transition to **● LISTENING FOR "HEY JARVIS"**.
5. Say clearly:
   ```
   "Hey JARVIS"
   ```
6. JARVIS detects the phrase locally, transitions to **WAKE WORD DETECTED**, acknowledges with `"Yes?"`, and opens the command window.
7. Say your command:
   ```
   "Open Chrome."
   ```
8. The Windows Local Agent executes and verifies the action, and JARVIS speaks:
   ```
   "Chrome is open."
   ```
9. Test follow-up chaining: immediately say `"Now open YouTube."` within the 8-second window without repeating `"Hey JARVIS"`.
10. Test silence timeout: say `"Hey JARVIS"`, remain silent for 8 seconds, and verify JARVIS says `"I didn't hear a command."` and returns to wake-word listening.

---

## Automated Test Suite

Run the full pytest suite (139 tests covering Steps 1–9.2 & 10):
```powershell
cd jarvis-backend
python -m pytest tests/test_browser_automation.py -v
python -m pytest -v
```

All 139 tests pass with 100% success rate.
Frontend tests (20 tests covering UI routing & wake word state machine):
```powershell
npm test
```
#   J A R V I S -  
 