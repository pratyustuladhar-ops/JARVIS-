# JARVIS — Autonomous Multimodal AI Agent Backend

**JARVIS** is an Autonomous Multimodal AI Agent designed for intelligent computer interaction, task automation, contextual reasoning, and dynamic systems control.

This backend provides a clean, modular, and production-grade API architecture built with **FastAPI**, **SQLAlchemy**, and **PostgreSQL**, engineered to serve the existing Stitch HUD frontend while providing clear interfaces for future advanced AI/ML capabilities, local Windows agents, and a dynamic CMS Admin Panel.

---

## 1. Architecture Overview

JARVIS implements a multi-stage autonomous reasoning pipeline:

```text
User Input / Voice Buffer
          ↓
  Intent Classifier (Rule-based -> ML/Transformer)
          ↓
  Task Planner (Step breakdown & tool recommendation)
          ↓
  Memory Engine (Preferences, Episodic & Vector lookup)
          ↓
  Tool Registry & Safe Executor (Project analyzer, AST syntax checker, System metrics)
          ↓
  Verifier (Safety audit & status confirmation)
          ↓
  Response Generator (Conversational synthesis)
```

### Key Architectural Tenets:
- **Clean Separation of Concerns**: Normal CRUD/business operations are strictly separated from AI/ML inference and agent pipelines.
- **Dynamic CMS / Admin Panel Ready**: Core system labels, entropy, greetings, AI instructions, and quick actions are served dynamically from the database.
- **Safe Tool Execution**: No arbitrary shell execution or destructive file modifications. All agent tools operate inside an isolated sandbox interface.
- **Vector Search & Embedding Ready**: Memory models are structured with `importance`, `relevance_score`, and `embedding_id` fields ready for `pgvector` or embedding stores.

---

## 2. Directory Structure

```text
jarvis-backend/
├── app/
│   ├── main.py                     # FastAPI entry point, lifespan, CORS, and error handlers
│   │
│   ├── core/
│   │   ├── config.py               # Pydantic v2 Settings & environment variables
│   │   └── database.py             # SQLAlchemy 2.0 engine, sessions, and table init
│   │
│   ├── models/                     # SQLAlchemy Database Models
│   │   ├── user.py                 # Users & operator clearance levels
│   │   ├── task.py                 # Autonomous tasks & queue states
│   │   ├── memory.py               # Knowledge facts, preferences & vector metadata
│   │   ├── project.py              # Tracked repositories & workspaces
│   │   ├── activity.py             # Live activity telemetry & audit stream
│   │   ├── chat.py                 # Multi-turn conversations & messages
│   │   └── cms.py                  # Dynamic CMS & admin panel configs
│   │
│   ├── schemas/                    # Pydantic Schemas (Request / Response validation)
│   │   ├── task.py
│   │   ├── memory.py
│   │   ├── project.py
│   │   ├── chat.py
│   │   ├── agent.py
│   │   └── cms.py
│   │
│   ├── api/                        # API V1 Endpoints
│   │   ├── dashboard.py            # GET /api/v1/dashboard (Stitch HUD telemetry)
│   │   ├── assistant.py            # POST /api/v1/assistant/chat (Agent reasoning)
│   │   ├── tasks.py                # CRUD /api/v1/tasks
│   │   ├── memory.py               # CRUD /api/v1/memory
│   │   ├── projects.py             # CRUD /api/v1/projects
│   │   ├── activity.py             # GET /api/v1/activity (Live audit feed)
│   │   └── cms.py                  # CRUD /api/v1/cms/config & GET /content
│   │
│   ├── services/                   # Business & Orchestration Layer
│   │   ├── dashboard_service.py    # Aggregates live system telemetry
│   │   ├── assistant_service.py    # Multi-turn session & message management
│   │   ├── agent_service.py        # 6-stage autonomous agent execution pipeline
│   │   ├── task_service.py         # Task operations
│   │   ├── memory_service.py       # Memory persistence & retrieval
│   │   ├── project_service.py      # Project tracking
│   │   ├── activity_service.py     # Audit event logging
│   │   └── cms_service.py          # Dynamic configuration manager
│   │
│   ├── ai/                         # Extensible AI / ML Reasoning Components
│   │   ├── intent_classifier.py    # Rule-based / extensible ML classifier
│   │   ├── planner.py              # Multi-step task planner
│   │   ├── memory_engine.py        # Contextual preference & relevance engine
│   │   └── model_service.py        # Unified LLM inference abstraction
│   │
│   ├── tools/                      # Safe Agent Tool Registry
│   │   ├── registry.py             # Discovery, schema validation & safe execution
│   │   ├── project_tool.py         # AST syntax and dependency analyzer
│   │   ├── file_tool.py            # Sandboxed file inspector
│   │   └── system_tool.py          # System diagnostics & task queue scheduler
│   │
│   └── mock/
│       └── seed_data.py            # Realistic initial HUD seed data
│
├── tests/                          # Automated Pytest Suite
│   ├── conftest.py                 # Isolated test database and TestClient
│   ├── test_health.py              # Health check test
│   ├── test_dashboard.py           # Dashboard telemetry endpoint test
│   ├── test_assistant.py           # Assistant chat & reasoning pipeline test
│   ├── test_tasks.py               # Tasks CRUD test
│   ├── test_memory.py              # Memory CRUD test
│   ├── test_projects.py            # Projects CRUD test
│   ├── test_activity.py            # Activity stream test
│   └── test_cms.py                 # CMS config and content map test
│
├── .env.example                    # Template environment variables
├── .env                            # Active environment configuration
├── requirements.txt                # Python dependencies
└── README.md                       # Documentation
```

---

## 3. Requirements

- Python 3.11+
- PostgreSQL 14+ (or local SQLite for zero-config fallback testing)
- PowerShell (Windows) or Bash (macOS/Linux)

---

## 4. Installation & Setup

### Step 1: Create and Activate Virtual Environment

**On Windows (PowerShell):**
```powershell
cd jarvis-backend
python -m venv .venv
.venv\Scripts\activate
```

**On macOS / Linux:**
```bash
cd jarvis-backend
python3 -m venv .venv
source .venv/bin/activate
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: PostgreSQL Database Setup

1. Create a database named `jarvis` in your PostgreSQL instance:
```sql
CREATE DATABASE jarvis;
```
2. Verify or update the credentials in `.env`:
```env
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/jarvis
```
*(Note: If PostgreSQL is not yet running locally, the backend can also use `sqlite:///./jarvis.db` for instant development without changing any application code).*

### Step 4: Run the Server

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

When the application boots:
- It automatically creates all database tables.
- It auto-seeds realistic telemetry matching the Stitch HUD (active tasks, projects, memories, recent activity, and CMS configurations).
- The server will be available at: `http://127.0.0.1:8000`.

---

## 5. API Documentation & Interactive Swagger

Once running, access the interactive API explorers:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc UI**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: `GET http://localhost:8000/health`

---

## 6. Testing

Run the automated test suite with `pytest`:

```bash
pytest
```

All 8 endpoint test modules run against an isolated SQLite test database with pre-seeded test fixtures.

---

## 7. Frontend Integration

A centralized client service has been prepared in `src/services/api.ts` (and `src/services/api.js`).

In your React/Vite frontend:
```bash
# In your frontend .env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

```typescript
import jarvisApi from './services/api';

// Fetch live HUD dashboard telemetry
const telemetry = await jarvisApi.getDashboard();

// Transmit voice/text command to autonomous reasoning agent
const agentResponse = await jarvisApi.sendChatMessage("Analyze my project");
console.log(agentResponse.intent); // "PROJECT_ANALYSIS"
console.log(agentResponse.plan);   // ["Locate active target...", ...]
console.log(agentResponse.tool);   // "project_analyzer"
```

---

## 8. Step 9: Advanced Multimodal Intelligence for JARVIS

Step 9 upgrades JARVIS with controlled, privacy-preserving multimodal intelligence across Text, Voice, Screenshots, Computer Context, and Conversational/Task Memory.

### Pipeline Architecture

```text
USER
 ↓
TEXT / VOICE / IMAGE PAYLOAD
 ↓
INPUT NORMALIZER
 ↓
MULTIMODAL UNDERSTANDING & INTENT DETECTION
 (SCREEN_ANALYSIS, OCR_REQUEST, IMAGE_ANALYSIS, VISION_QUERY, SCREEN_CONTEXT_REQUEST)
 ↓
CONTEXT RETRIEVAL (Tasks, Projects, Relevant Memories, System Context, Visual Context)
 ↓
AI PLANNER (Decomposes complex requests into chained tool execution steps)
 ↓
TOOL REGISTRY (local_capture_screen, vision_analysis, vision_ocr, local agent tools)
 ↓
TOOL EXECUTOR (Isolated execution enclave with intermediate buffer propagation)
 ↓
VERIFIER (Confirms image presence, non-empty OCR, valid structured analysis)
 ↓
MEMORY MANAGER (Stores concise textual scene summaries; raw images never stored in DB)
 ↓
RESPONSE GENERATOR (Synthesizes natural language answer and speech-ready text for TTS)
```

### Vision Provider Configuration

JARVIS utilizes a pluggable provider abstraction (`BaseVisionProvider`) so the vision intelligence engine can be switched via environment variables without changing agent code:

- `VISION_PROVIDER=mock`: Deterministic, high-fidelity local provider for offline execution, development, and testing.
- `VISION_PROVIDER=gemini`: Google Gemini 1.5 Flash / Pro multimodal vision API.
- `VISION_PROVIDER=openai`: OpenAI GPT-4o / GPT-4-Turbo vision API.

Configure in `.env`:
```bash
VISION_ENABLED=true
VISION_PROVIDER=mock
GEMINI_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
SCREEN_CAPTURE_ENABLED=true
OCR_ENABLED=true
VISUAL_CONTEXT_ENABLED=true
MAX_IMAGE_SIZE_MB=10
PRIVACY_MODE=true
```

### Screenshot Privacy Model

1. **Zero Continuous Capture**: Screenshots are captured ONLY upon explicit user command or permitted user-initiated tool action. Continuous background capture or surveillance is strictly prohibited.
2. **Zero Raw Image Database Persistence**: PostgreSQL tables (`memories`, `activities`, `conversations`) never store base64 data URIs or binary image buffers. Only metadata (`resolution`, `provider_used`, `duration_ms`) and concise textual scene summaries are persisted.
3. **Activity Logging Redaction**: Activity logs record `IMAGE_ANALYSIS_STARTED`, `SCREEN_CAPTURED`, and `IMAGE_ANALYSIS_COMPLETED` without logging sensitive visual payloads.
4. **Resolution Downscaling**: Large screens are automatically scaled to a safe max dimension (1920px) and compressed using Pillow before transmission.

### Controlled Tools (Tool Registry)

- `local_capture_screen`:
  - **Permission**: `USER_INITIATED`
  - **Purpose**: Captures a desktop screen frame via authenticated Windows Local Agent.
  - **Verification**: Verifies valid base64 PNG data URI and non-empty resolution.
- `vision_analysis`:
  - **Permission**: `AUTONOMOUS`
  - **Purpose**: Visual reasoning, screen description, and UI element detection.
  - **Verification**: Validates non-empty structured summary/description.
- `vision_ocr`:
  - **Permission**: `AUTONOMOUS`
  - **Purpose**: Optical character recognition for error dialogs, logs, and code.
  - **Verification**: Verifies extracted text character length > 0.

### Dedicated Multimodal API Endpoint

`POST /api/v1/assistant/multimodal`
```json
{
  "message": "What is on my screen?",
  "input_type": "voice",
  "image_data": "data:image/png;base64,...",
  "metadata": {
    "filename": "screenshot.png",
    "mime_type": "image/png"
  },
  "conversation_id": 1
}
```

*Note: `POST /api/v1/assistant/message` remains 100% backward compatible.*

### Security Controls & Limitations

- **No Arbitrary Shell Execution**: Commands like `powershell`, `cmd`, or shell scripts are blocked.
- **No Path Traversal**: Rejects arbitrary image write paths or file resolution outside approved user folders.
- **No Unrestricted Automation**: No arbitrary mouse clicking or keyboard typing is permitted in Step 9.
- **No Surveillance / Background Recording**: Screenshots are single-shot and user-consented.

### Example Commands to Test

1. **"What is on my screen?"**
   → Intent: `SCREEN_ANALYSIS`
   → Plan: `local_capture_screen` → `vision_analysis`
   → Synthesized answer describing active applications.
2. **"Read this error"**
   → Intent: `OCR_REQUEST`
   → Plan: `local_capture_screen` → `vision_ocr`
   → Extracts and explains error text.
3. **"Explain this code"**
   → Analyzes code visible in active IDE window.
4. **"What application am I using?"**
   → Identifies primary foreground application from screen buffer.
5. **"What button should I click to continue?"**
   → Identifies UI action controls and explains their locations.

### Running Step 9 Tests

```bash
cd jarvis-backend
python -m pytest tests/test_multimodal.py -v
python -m pytest -v
```

---

## 7.1 Step 9.1 — Multi-Step AI Agent Planner

Step 9.1 upgrades JARVIS from individual command execution to safe, structured, sequential multi-step task planning and execution.

### Architecture Flow:
```text
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

### Supported Examples:
1. `"Open Chrome and open YouTube."` → Step 1: `LOCAL_OPEN_APPLICATION(chrome)` → Verify → Step 2: `LOCAL_OPEN_URL(https://youtube.com)` → Verify
2. `"Open Notepad and Calculator."` → Step 1: `LOCAL_OPEN_APPLICATION(notepad)` → Verify → Step 2: `LOCAL_OPEN_APPLICATION(calculator)` → Verify
3. `"Open Chrome and Edge."` → Step 1: `LOCAL_OPEN_APPLICATION(chrome)` → Verify → Step 2: `LOCAL_OPEN_APPLICATION(edge)` → Verify
4. `"Open Chrome, then open YouTube, then open Spotify."` → 3 sequential verified steps
5. `"Create a task to study DBMS and open VS Code."` → Step 1: `TASK_CREATE` → Verify → Step 2: `LOCAL_OPEN_APPLICATION(vscode)` → Verify
6. `"Open VS Code then open my project folder."` → Step 1: `LOCAL_OPEN_APPLICATION(vscode)` → Verify → Step 2: `LOCAL_OPEN_FOLDER(Documents)` → Verify

### Safety Model & Execution Guarantees:
- **No Arbitrary Shell Execution**: Rejects `powershell`, `cmd`, `bash`, `python`, `shell`, `exec`.
- **Immediate Failure Halting**: Step 2 depends on Step 1 (`depends_on: [1]`). If Step 1 fails, Step 2 is marked `SKIPPED` and NEVER executed.
- **Truthful Failure Reporting**: `"I couldn't open Chrome, so I didn't continue with the next step."`
- **Loop Protection**: Strict `MAX_PLAN_STEPS = 10` boundary.
- **Granular Activity Auditing**: `PLAN_CREATED`, `STEP_STARTED`, `STEP_COMPLETED`, `STEP_VERIFIED`, `STEP_FAILED`, `PLAN_COMPLETED`, `PLAN_FAILED` with credential scrubbing.

### Running Step 9.1 Tests:
```bash
cd jarvis-backend
python -m pytest tests/test_multi_step_planner.py -v
python -m pytest -v
```

---

## 8. Step 10 — Hands-Free Wake Word & Voice State Machine

Step 10 introduces hands-free voice interaction so the operator can say **"Hey JARVIS"**, wake the assistant locally without clicking a button, issue a command, and receive a verified audio response via TTS.

### Voice State Machine

```text
IDLE
 ↓
WAKE_WORD_LISTENING
 ↓
WAKE_WORD_DETECTED
 ↓
LISTENING (Command Window, 8s timeout)
 ↓
PROCESSING
 ↓
ANALYZING / EXECUTING
 ↓
VERIFYING
 ↓
RESPONDING (TTS Synthesized, Wake Detector Paused)
 ↓
FOLLOW-UP WINDOW (8s)
 ↓
WAKE_WORD_LISTENING
```

### Endpoints
- `GET /api/v1/voice/wake-word/status`: Returns current state machine status, active wake phrase, timeouts, and provider info.
- `POST /api/v1/voice/wake-word/toggle`: Enables or disables hands-free wake word listening mode.
- `POST /api/v1/voice/wake-word/event`: Records wake detection, command execution, or timeout events in the audit log (zero raw audio stored).

### Running Step 10 Tests
```bash
cd jarvis-backend
python -m pytest tests/test_wake_word.py -v
python -m pytest -v
```
All 87 tests run and pass in ~4 seconds.

