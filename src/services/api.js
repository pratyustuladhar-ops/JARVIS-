/**
 * JARVIS Centralized Frontend API Service Layer (Vanilla JS / Browser Module)
 * Direct bridge to FastAPI backend at http://localhost:8000/api/v1
 */

const API_BASE_URL =
  (typeof window !== "undefined" && window.__JARVIS_API_URL__) ||
  "http://localhost:8000/api/v1";

async function apiFetch(endpoint, options = {}) {
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
  // Health
  async getHealth() {
    const rootUrl = API_BASE_URL.replace("/api/v1", "");
    const res = await fetch(`${rootUrl}/health`);
    return res.json();
  },

  // Dashboard Telemetry
  async getDashboard() {
    return apiFetch("/dashboard");
  },

  async sendAssistantMessage(message, conversationId) {
    const payload = typeof message === "object" ? message : { message, conversation_id: conversationId };
    return apiFetch("/assistant/message", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // Multimodal Intelligence (Step 9)
  async sendMultimodalMessage(payload) {
    return apiFetch("/assistant/multimodal", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async captureScreen(params = {}) {
    return apiFetch("/local-agent/execute", {
      method: "POST",
      body: JSON.stringify({
        tool: "capture_screen",
        parameters: params,
      }),
    });
  },

  async sendChatMessage(message, conversationId, contextToken) {
    return apiFetch("/assistant/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        context_token: contextToken,
      }),
    });
  },

  async getAgentTools() {
    return apiFetch("/assistant/tools");
  },

  async getConversation(conversationId) {
    return apiFetch(`/assistant/conversations/${conversationId}`);
  },

  async getSystemStatus() {
    return apiFetch("/assistant/system-status");
  },

  // Tasks CRUD
  async getTasks(skip = 0, limit = 50) {
    return apiFetch("/tasks", { params: { skip, limit } });
  },

  async getTask(id) {
    return apiFetch(`/tasks/${id}`);
  },

  async createTask(taskData) {
    return apiFetch("/tasks", {
      method: "POST",
      body: JSON.stringify(taskData),
    });
  },

  async updateTask(id, taskData) {
    return apiFetch(`/tasks/${id}`, {
      method: "PUT",
      body: JSON.stringify(taskData),
    });
  },

  async deleteTask(id) {
    return apiFetch(`/tasks/${id}`, { method: "DELETE" });
  },

  // Projects CRUD
  async getProjects(skip = 0, limit = 50) {
    return apiFetch("/projects", { params: { skip, limit } });
  },

  async getProject(id) {
    return apiFetch(`/projects/${id}`);
  },

  async createProject(projectData) {
    return apiFetch("/projects", {
      method: "POST",
      body: JSON.stringify(projectData),
    });
  },

  async updateProject(id, projectData) {
    return apiFetch(`/projects/${id}`, {
      method: "PUT",
      body: JSON.stringify(projectData),
    });
  },

  async deleteProject(id) {
    return apiFetch(`/projects/${id}`, { method: "DELETE" });
  },

  // Memories CRUD
  async getMemories(skip = 0, limit = 50) {
    return apiFetch("/memory", { params: { skip, limit } });
  },

  async getMemory(id) {
    return apiFetch(`/memory/${id}`);
  },

  async createMemory(memoryData) {
    return apiFetch("/memory", {
      method: "POST",
      body: JSON.stringify(memoryData),
    });
  },

  async updateMemory(id, memoryData) {
    return apiFetch(`/memory/${id}`, {
      method: "PUT",
      body: JSON.stringify(memoryData),
    });
  },

  async deleteMemory(id) {
    return apiFetch(`/memory/${id}`, { method: "DELETE" });
  },

  // Activities
  async getActivities(limit = 15) {
    return apiFetch("/activity", { params: { limit } });
  },

  // CMS & Admin Panel Configuration
  async getCMSContent() {
    return apiFetch("/cms/content");
  },

  async getCMSConfigs(category) {
    return apiFetch("/cms/config", { params: { category } });
  },

  async createCMSConfig(configData) {
    return apiFetch("/cms/config", {
      method: "POST",
      body: JSON.stringify(configData),
    });
  },

  async updateCMSConfig(id, configData) {
    return apiFetch(`/cms/config/${id}`, {
      method: "PUT",
      body: JSON.stringify(configData),
    });
  },

  async deleteCMSConfig(id) {
    return apiFetch(`/cms/config/${id}`, {
      method: "DELETE",
    });
  },


  // Settings
  async getSettings() {
    return apiFetch("/settings");
  },

  async updateSettings(settingsData) {
    return apiFetch("/settings", {
      method: "PUT",
      body: JSON.stringify(settingsData),
    });
  },

  async saveSettings(settingsData) {
    return this.updateSettings(settingsData);
  },

  async getSetting(key) {
    return apiFetch(`/settings/${key}`);
  },

  async updateSetting(key, value) {
    return apiFetch(`/settings/${key}`, {
      method: "PUT",
      body: JSON.stringify({ value }),
    });
  },

  async getSystemStatus() {
    return apiFetch("/system/status");
  },

  async getSettingsTelemetry() {
    return apiFetch("/settings/status");
  },

  async resetSettings() {
    return apiFetch("/settings/reset", {
      method: "POST",
    });
  },

  async purgeVectorCache() {
    return apiFetch("/settings/purge-cache", {
      method: "POST",
    });
  },

  async exportSnapshot() {
    return apiFetch("/settings/export");
  },

  // Windows Local Agent
  async getLocalAgentStatus() {
    return apiFetch("/local-agent/status");
  },

  async getLocalAgentDevices() {
    return apiFetch("/local-agent/devices");
  },

  async generateLocalAgentToken() {
    return apiFetch("/local-agent/token", {
      method: "POST",
    });
  },

  async executeLocalTool(tool, parameters = {}) {
    return apiFetch("/local-agent/execute", {
      method: "POST",
      body: JSON.stringify({ tool, parameters }),
    });
  },

  // Step 9: Multimodal Intelligence
  async sendMultimodalMessage(payload) {
    return apiFetch("/assistant/multimodal", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async captureScreen(parameters = {}) {
    return this.executeLocalTool("capture_screen", parameters);
  },

  // Step 10: Wake Word & Hands-Free
  async getWakeWordStatus() {
    return apiFetch("/voice/wake-word/status");
  },

  async toggleWakeWord(enabled) {
    return apiFetch(`/voice/wake-word/toggle?enabled=${Boolean(enabled)}`, {
      method: "POST",
    });
  },

  async logWakeWordEvent(eventPayload) {
    return apiFetch("/voice/wake-word/event", {
      method: "POST",
      body: JSON.stringify(eventPayload),
    });
  },
};


if (typeof window !== "undefined") {
  window.jarvisApi = jarvisApi;
}

export default jarvisApi;

