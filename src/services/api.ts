/**
 * JARVIS Centralized Frontend API Service Layer
 * Strictly typed against FastAPI backend schemas at http://localhost:8000/api/v1
 */

import type {
  Task,
  TaskCreate,
  TaskUpdate,
  Project,
  ProjectCreate,
  ProjectUpdate,
  Memory,
  MemoryCreate,
  MemoryUpdate,
  Activity,
  ChatRequest,
  ChatResponse,
  CMSConfig,
  CMSConfigCreate,
  CMSConfigUpdate,
  SystemSettings,

  SystemSettingsUpdate,
  TelemetrySummary,
} from "../types";


const API_BASE_URL: string =
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_BASE_URL) ||
  "http://localhost:8000/api/v1";

interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined>;
}

async function apiFetch<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { params, headers, ...rest } = options;
  let url = `${API_BASE_URL}${endpoint}`;

  if (params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined) searchParams.append(k, String(v));
    });
    const qs = searchParams.toString();
    if (qs) url += `?${qs}`;
  }

  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...headers,
    },
    ...rest,
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    const message =
      errorBody?.detail ||
      errorBody?.message ||
      `HTTP ${response.status}: ${response.statusText}`;
    throw new Error(message);
  }

  return response.json();
}

export const jarvisApi = {
  // System Health
  async getHealth(): Promise<{ status: string; service: string }> {
    const rootUrl = API_BASE_URL.replace("/api/v1", "");
    const res = await fetch(`${rootUrl}/health`);
    return res.json();
  },

  // Dashboard Telemetry
  async getDashboard(): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>("/dashboard");
  },

  async sendAssistantMessage(payload: { message: string; conversation_id?: number | null; input_type?: string; image_data?: string | null }): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>("/assistant/message", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // Multimodal Intelligence (Step 9)
  async sendMultimodalMessage(payload: { message?: string; content?: string; input_type?: string; image_data?: string | null; conversation_id?: number | null; metadata?: Record<string, unknown> }): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>("/assistant/multimodal", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async captureScreen(params: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>("/local-agent/execute", {
      method: "POST",
      body: JSON.stringify({
        tool: "capture_screen",
        parameters: params,
      }),
    });
  },

  async sendChatMessage(payload: ChatRequest): Promise<ChatResponse> {
    return apiFetch<ChatResponse>("/assistant/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async getAgentTools(): Promise<Array<Record<string, unknown>>> {
    return apiFetch<Array<Record<string, unknown>>>("/assistant/tools");
  },

  async getConversation(conversationId: number): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>(`/assistant/conversations/${conversationId}`);
  },

  async getSystemStatus(): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>("/assistant/system-status");
  },

  // Tasks CRUD
  async getTasks(skip = 0, limit = 50): Promise<Task[]> {
    return apiFetch<Task[]>("/tasks", { params: { skip, limit } });
  },

  async getTask(id: number): Promise<Task> {
    return apiFetch<Task>(`/tasks/${id}`);
  },

  async createTask(taskData: TaskCreate): Promise<Task> {
    return apiFetch<Task>("/tasks", {
      method: "POST",
      body: JSON.stringify(taskData),
    });
  },

  async updateTask(id: number, taskData: TaskUpdate): Promise<Task> {
    return apiFetch<Task>(`/tasks/${id}`, {
      method: "PUT",
      body: JSON.stringify(taskData),
    });
  },

  async deleteTask(id: number): Promise<{ message: string }> {
    return apiFetch<{ message: string }>(`/tasks/${id}`, { method: "DELETE" });
  },

  // Projects CRUD
  async getProjects(skip = 0, limit = 50): Promise<Project[]> {
    return apiFetch<Project[]>("/projects", { params: { skip, limit } });
  },

  async getProject(id: number): Promise<Project> {
    return apiFetch<Project>(`/projects/${id}`);
  },

  async createProject(projectData: ProjectCreate): Promise<Project> {
    return apiFetch<Project>("/projects", {
      method: "POST",
      body: JSON.stringify(projectData),
    });
  },

  async updateProject(id: number, projectData: ProjectUpdate): Promise<Project> {
    return apiFetch<Project>(`/projects/${id}`, {
      method: "PUT",
      body: JSON.stringify(projectData),
    });
  },

  async deleteProject(id: number): Promise<{ message: string }> {
    return apiFetch<{ message: string }>(`/projects/${id}`, { method: "DELETE" });
  },

  // Memories CRUD
  async getMemories(skip = 0, limit = 50): Promise<Memory[]> {
    return apiFetch<Memory[]>("/memory", { params: { skip, limit } });
  },

  async getMemory(id: number): Promise<Memory> {
    return apiFetch<Memory>(`/memory/${id}`);
  },

  async createMemory(memoryData: MemoryCreate): Promise<Memory> {
    return apiFetch<Memory>("/memory", {
      method: "POST",
      body: JSON.stringify(memoryData),
    });
  },

  async updateMemory(id: number, memoryData: MemoryUpdate): Promise<Memory> {
    return apiFetch<Memory>(`/memory/${id}`, {
      method: "PUT",
      body: JSON.stringify(memoryData),
    });
  },

  async deleteMemory(id: number): Promise<{ message: string }> {
    return apiFetch<{ message: string }>(`/memory/${id}`, { method: "DELETE" });
  },

  // Activities
  async getActivities(limit = 15): Promise<Activity[]> {
    return apiFetch<Activity[]>("/activity", { params: { limit } });
  },

  // CMS
  async getCMSContent(): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>("/cms/content");
  },

  async getCMSConfigs(category?: string): Promise<CMSConfig[]> {
    return apiFetch<CMSConfig[]>("/cms/config", { params: { category } });
  },

  async createCMSConfig(configData: CMSConfigCreate): Promise<CMSConfig> {
    return apiFetch<CMSConfig>("/cms/config", {
      method: "POST",
      body: JSON.stringify(configData),
    });
  },

  async updateCMSConfig(id: number, configData: CMSConfigUpdate): Promise<CMSConfig> {
    return apiFetch<CMSConfig>(`/cms/config/${id}`, {
      method: "PUT",
      body: JSON.stringify(configData),
    });
  },

  async deleteCMSConfig(id: number): Promise<{ message: string }> {
    return apiFetch<{ message: string }>(`/cms/config/${id}`, {
      method: "DELETE",
    });
  },


  // Settings
  async getSettings(): Promise<SystemSettings> {
    return apiFetch<SystemSettings>("/settings");
  },

  async updateSettings(settingsData: SystemSettingsUpdate): Promise<SystemSettings> {
    return apiFetch<SystemSettings>("/settings", {
      method: "PUT",
      body: JSON.stringify(settingsData),
    });
  },

  async saveSettings(settingsData: SystemSettingsUpdate): Promise<SystemSettings> {
    return this.updateSettings(settingsData);
  },

  async getSetting(key: string): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>(`/settings/${key}`);
  },

  async updateSetting(key: string, value: unknown): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>(`/settings/${key}`, {
      method: "PUT",
      body: JSON.stringify({ value }),
    });
  },

  async getSettingsTelemetry(): Promise<TelemetrySummary> {
    return apiFetch<TelemetrySummary>("/settings/status");
  },


  async resetSettings(): Promise<SystemSettings> {
    return apiFetch<SystemSettings>("/settings/reset", {
      method: "POST",
    });
  },

  async purgeVectorCache(): Promise<{ status: string; vectors_cleared: number; message: string }> {
    return apiFetch<{ status: string; vectors_cleared: number; message: string }>("/settings/purge-cache", {
      method: "POST",
    });
  },

  async exportSnapshot(): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>("/settings/export");
  },

  // Windows Local Agent
  async getLocalAgentStatus(): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>("/local-agent/status");
  },

  async getLocalAgentDevices(): Promise<Array<Record<string, unknown>>> {
    return apiFetch<Array<Record<string, unknown>>>("/local-agent/devices");
  },

  async generateLocalAgentToken(): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>("/local-agent/token", {
      method: "POST",
    });
  },

  async executeLocalTool(tool: string, parameters: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>("/local-agent/execute", {
      method: "POST",
      body: JSON.stringify({ tool, parameters }),
    });
  },

  // Step 9: Multimodal Intelligence
  async sendMultimodalMessage(payload: {
    message?: string;
    input_type?: string;
    image_data?: string;
    mime_type?: string;
    filename?: string;
    conversation_id?: number | null;
  }): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>("/assistant/multimodal", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async captureScreen(parameters: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    return this.executeLocalTool("capture_screen", parameters);
  },

  // Step 10: Wake Word & Hands-Free
  async getWakeWordStatus(): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>("/voice/wake-word/status");
  },

  async toggleWakeWord(enabled: boolean): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>(`/voice/wake-word/toggle?enabled=${Boolean(enabled)}`, {
      method: "POST",
    });
  },

  async logWakeWordEvent(eventPayload: {
    event_type: string;
    wake_phrase?: string;
    detail?: string;
    duration_ms?: number;
    metadata?: Record<string, unknown>;
  }): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>("/voice/wake-word/event", {
      method: "POST",
      body: JSON.stringify(eventPayload),
    });
  },
};


export default jarvisApi;

