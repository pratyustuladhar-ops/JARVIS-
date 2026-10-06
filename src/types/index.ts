/**
 * JARVIS Core TypeScript Interfaces & Types
 * Strictly mirrors FastAPI / Pydantic schemas in jarvis-backend/app/schemas/
 */

export type TaskStatus =
  | "AI WORKING"
  | "WAITING FOR INPUT"
  | "SCHEDULED"
  | "COMPLETED"
  | "PAUSED"
  | "CANCELLED"
  | "ACTIVE"
  | "PENDING";

export type PriorityLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface Task {
  id: number;
  title: string;
  description?: string | null;
  status: TaskStatus | string;
  priority: PriorityLevel | string;
  due_date?: string | null;
  progress: number;
  eta?: string | null;
  category?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskCreate {
  title: string;
  description?: string | null;
  status?: string;
  priority?: string;
  due_date?: string | null;
  progress?: number;
  eta?: string | null;
  category?: string | null;
}

export interface TaskUpdate {
  title?: string;
  description?: string | null;
  status?: string;
  priority?: string;
  due_date?: string | null;
  progress?: number;
  eta?: string | null;
  category?: string | null;
}

export type ProjectStatus =
  | "ACTIVE"
  | "PAUSED"
  | "COMPLETED"
  | "TRAINING"
  | "LOCKED"
  | "QUEUED";

export interface Project {
  id: number;
  name: string;
  description?: string | null;
  status: ProjectStatus | string;
  progress: number;
  repo_path?: string | null;
  technologies?: string | null;
  file_count?: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  description?: string | null;
  status?: string;
  progress?: number;
  repo_path?: string | null;
  technologies?: string | null;
  file_count?: number;
}

export interface ProjectUpdate {
  name?: string;
  description?: string | null;
  status?: string;
  progress?: number;
  repo_path?: string | null;
  technologies?: string | null;
  file_count?: number;
}

export interface Memory {
  id: number;
  content: string;
  memory_type: "FACT" | "PREFERENCE" | "CODEBASE" | "EPISODIC" | "SEMANTIC" | string;
  importance: number;
  relevance_score?: number | null;
  embedding_id?: string | null;
  tags?: string | null;
  metadata_json?: string | null;
  created_at: string;
  updated_at: string;
}

export interface MemoryCreate {
  content: string;
  memory_type?: string;
  importance?: number;
  relevance_score?: number;
  embedding_id?: string | null;
  tags?: string | null;
  metadata_json?: string | null;
}

export interface MemoryUpdate {
  content?: string;
  memory_type?: string;
  importance?: number;
  relevance_score?: number;
  embedding_id?: string | null;
  tags?: string | null;
  metadata_json?: string | null;
}

export interface Activity {
  id: number;
  event_type: string;
  title: string;
  description: string;
  status: "SUCCESS" | "INFO" | "WARNING" | "ERROR" | string;
  timestamp: string;
  time?: string;
}

export interface ChatRequest {
  message: string;
  conversation_id?: number | null;
  context_token?: string | null;
}

export interface ChatResponse {
  message: string;
  intent: string;
  plan: string[];
  tool?: string | null;
  status: string;
  verified: boolean;
  conversation_id?: number | null;
  context_token?: string | null;
  memory_accessed?: string | null;
  details?: Record<string, unknown> | null;
}

export interface AgentMessageRequest {
  message: string;
  conversation_id?: number | null;
}

export interface AgentMessageResponse {
  response: string;
  intent: string;
  confidence: number;
  plan: Array<{
    step_number: number;
    tool_name?: string | null;
    risk_level: string;
    status: string;
  }>;
  actions: Array<{
    tool_name: string;
    status: string;
    output?: unknown;
    duration_ms?: number;
    error?: string;
  }>;
  verification: Array<{
    status: "VERIFIED" | "FAILED" | "NOT_APPLICABLE" | string;
    tool: string;
    entity_id?: string | number | null;
    detail?: string;
  }>;
  conversation_id?: number | null;
  execution_time_ms: number;
  agent_state: "THINKING" | "EXECUTING" | "VERIFYING" | "RESPONDING" | "ERROR" | string;
  memory_accessed?: string | null;
}

export interface CMSConfig {
  id: number;
  key: string;
  value: string;
  type: "string" | "number" | "boolean" | "json" | "markdown" | string;
  category: string;
  description?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CMSConfigCreate {
  key: string;
  value: string;
  type?: string;
  category?: string;
  description?: string | null;
  is_active?: boolean;
}

export interface CMSConfigUpdate {
  value?: string;
  type?: string;
  category?: string;
  description?: string | null;
  is_active?: boolean;
}


export interface SystemSettings {
  assistant_name: string;
  operator_callsign: string;
  synthesis_language: string;
  system_temporal_clock: string;
  timestamp_notation: string;
  viewport_density: string;
  hud_coordinates_overlay: boolean;
  behavioral_preset: string;
  neural_backbone: string;
  temperature: number;
  context_budget: number;
  auto_verification: boolean;
  multi_turn_reasoning: boolean;
  reasoning_depth: number;
  streaming_token_telemetry: boolean;
  persistent_memory: boolean;
  autonomous_ingestion: boolean;
  similarity_threshold: number;
  notify_task_completion: boolean;
  notify_escalations: boolean;
  notify_telemetry_anomalies: boolean;
  notify_audio_ping: boolean;
  notify_security_broadcast: boolean;
  color_accent: string;
  glow_intensity: number;
  particle_vfx: boolean;
  glassmorphism: boolean;
  isolated_docker_sandbox: boolean;
  tool_execution_policy: string;
  emergency_sandbox: boolean;
  voice_enabled?: boolean;
  voice_name?: string;
  voice_rate?: number;
  voice_pitch?: number;
  voice_volume?: number;
  extra_params?: Record<string, unknown>;
}

export type SystemSettingsUpdate = Partial<SystemSettings>;

export interface TelemetrySummary {
  system_status: string;
  fastapi_backend: string;
  postgresql_cluster: string;
  ai_engine: string;
  kernel_version: string;
  settings_endpoint: string;
  memory_pool: string;
  worker_threads: string;
  latency_ms: number;
  uptime_percentage: number;
  build_version: string;
}

