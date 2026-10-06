import logging
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple, Optional
import httpx
from app.core.config import settings

logger = logging.getLogger("jarvis.ai.providers")


class BaseAIProvider(ABC):
    """Abstract provider abstraction for LLMs and reasoning models."""

    @abstractmethod
    def generate_response(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Generates conversational or task response from prompt and context."""
        pass

    @abstractmethod
    def classify_intent(self, text: str, candidate_intents: List[str]) -> Tuple[str, float]:
        """Classifies intent using few-shot or zero-shot model reasoning."""
        pass

    @abstractmethod
    def generate_plan(
        self,
        goal: str,
        available_tools: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Decomposes a goal into sequential tool execution steps."""
        pass


class MockAIProvider(BaseAIProvider):
    """
    Deterministic, robust local provider for offline execution, development,
    and fallback when no external LLM credentials exist.
    """

    def generate_response(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        prompt_lower = prompt.lower()
        context = context or {}
        tool_results = context.get("tool_results", [])
        intent = context.get("intent", "CHAT")

        # Contextual synthesis when tools were executed
        if tool_results:
            first_tool = tool_results[0]
            tool_name = first_tool.get("tool_name", "")
            output = first_tool.get("output", {})
            status = first_tool.get("status", "SUCCESS")

            if tool_name == "task_create" and status == "SUCCESS":
                title = output.get("title", "Task")
                task_id = output.get("id", "N/A")
                return f"Task created successfully. '{title}' has been registered in the execution pipeline (Task #{task_id})."

            if tool_name == "task_list" and status == "SUCCESS":
                tasks = output if isinstance(output, list) else []
                if not tasks:
                    return "You currently have no active tasks in your queue."
                task_lines = [f"• Task #{t.get('id')}: {t.get('title')} [{t.get('status', 'PENDING')}]" for t in tasks[:5]]
                return f"Retrieved {len(tasks)} active task(s):\n" + "\n".join(task_lines)

            if tool_name == "task_update" and status == "SUCCESS":
                return f"Task #{output.get('id')} has been updated successfully."

            if tool_name == "task_delete" and status == "SUCCESS":
                return f"Task has been removed from the pipeline."

            if tool_name == "project_create" and status == "SUCCESS":
                return f"Project '{output.get('name')}' created and registered to your workspace (Project #{output.get('id')})."

            if tool_name == "project_list" and status == "SUCCESS":
                projects = output if isinstance(output, list) else []
                if not projects:
                    return "No projects currently indexed in your workspace."
                proj_lines = [f"• Project #{p.get('id')}: {p.get('name')} (Progress: {p.get('progress', 0)}%)" for p in projects[:4]]
                return f"Found {len(projects)} registered project(s):\n" + "\n".join(proj_lines)

            if tool_name == "memory_search" and status == "SUCCESS":
                mems = output if isinstance(output, list) else []
                if not mems:
                    return "No matching memories found in your vector graph."
                lines = [f"• {m.get('content')} [Score: {m.get('relevance_score', 1.0)}]" for m in mems[:3]]
                return "Recalled the following memories:\n" + "\n".join(lines)

            if tool_name == "memory_create" and status == "SUCCESS":
                return f"Memory stored. '{output.get('content')}' is now anchored to your personal knowledge graph."

            if tool_name == "system_status" and status == "SUCCESS":
                return "All autonomous computational subsystems stand synchronized. Telemetry: API Online, Database Connected, AI Swarm Standby (Restricted)."

            # Windows Local Agent Tools
            if tool_name == "local_open_application" and status == "SUCCESS":
                app_name = output.get("application", "Application") if isinstance(output, dict) else "Application"
                return f"{app_name.title()} is open."

            if tool_name == "local_open_url" and status == "SUCCESS":
                url_opened = output.get("url", "") if isinstance(output, dict) else ""
                return f"Opened {url_opened} in your default browser."

            if tool_name == "local_get_system_info" and status == "SUCCESS":
                if isinstance(output, dict):
                    return (
                        f"System Telemetry ({output.get('device_name', 'Windows Host')}):\n"
                        f"• OS: {output.get('os')}\n"
                        f"• CPU: {output.get('cpu_count')} Cores ({output.get('cpu_usage_percent', 0)}% usage)\n"
                        f"• Memory: {output.get('ram_available')} available / {output.get('ram_total')}\n"
                        f"• Host: {output.get('hostname')}"
                    )
                return "Retrieved local Windows system specifications."

            if tool_name == "local_get_current_time" and status == "SUCCESS":
                time_str = output.get("formatted") if isinstance(output, dict) else ""
                tz_str = output.get("timezone", "") if isinstance(output, dict) else ""
                return f"The current time is {time_str} ({tz_str})."

            if tool_name == "local_list_directory" and status == "SUCCESS":
                if isinstance(output, dict):
                    items = output.get("items", [])
                    dir_name = output.get("directory", "Folder")
                    if not items:
                        return f"The {dir_name} folder is empty."
                    item_lines = [f"• {'[DIR] ' if i.get('is_directory') else ''}{i.get('name')}" for i in items[:6]]
                    return f"Found {output.get('total_items', len(items))} item(s) in {dir_name}:\n" + "\n".join(item_lines)
                return "Listed directory contents successfully."

            if tool_name == "local_open_file" and status == "SUCCESS":
                fname = output.get("file", "File") if isinstance(output, dict) else "File"
                return f"Opened '{fname}' with its default Windows application."

            if tool_name == "local_open_folder" and status == "SUCCESS":
                folder_name = output.get("folder", "Folder") if isinstance(output, dict) else "Folder"
                return f"Opened {folder_name} in File Explorer."

            # Windows Local Agent Error / Refusal Handling
            if tool_name.startswith("local_") and (status != "SUCCESS" or (isinstance(output, dict) and output.get("status") == "failed")):
                err_msg = output.get("error") or output.get("reason") or "Action could not be executed"
                err_lower = str(err_msg).lower()
                if "allowlist" in err_lower or "not in the approved allowlist" in err_lower or "permission" in err_lower:
                    return "I don't have permission to open that application. Only pre-approved applications (VS Code, Chrome, Notepad, Calculator, Explorer, Terminal) can be launched."
                if "traversal" in err_lower or "outside approved" in err_lower:
                    return "Access denied. Path traversal and access outside approved user directories (Desktop, Documents, Downloads) is strictly prohibited."
                if "scheme" in err_lower or "url" in err_lower:
                    return "Invalid URL or rejected protocol. Only secure http:// and https:// web addresses are permitted."
                return f"Local agent action failed: {err_msg}"

        if intent == "BLOCKED_COMMAND":
            return "I can't execute arbitrary system commands. Only pre-approved Windows tools from the allowlist are permitted."

        if intent == "CHAT" or "hello" in prompt_lower or "hi" in prompt_lower:
            return "Greetings, Commander. JARVIS OS v4.2 stands ready to execute commands and organize tasks."

        if intent == "QUESTION":
            return f"Regarding your query: '{prompt}'. In JARVIS computing architecture, this represents a core subsystem operation."

        return f"Understood, Commander. JARVIS Core processed your request: '{prompt}'."

    def classify_intent(self, text: str, candidate_intents: List[str]) -> Tuple[str, float]:
        text_lower = text.lower()
        if any(w in text_lower for w in ["task", "todo", "reminder"]):
            if any(w in text_lower for w in ["create", "add", "new", "schedule"]):
                return "CREATE_TASK", 0.92
            if any(w in text_lower for w in ["list", "show", "what", "display", "get"]):
                return "LIST_TASKS", 0.94
            if any(w in text_lower for w in ["update", "mark", "set", "change"]):
                return "UPDATE_TASK", 0.90
            if any(w in text_lower for w in ["delete", "remove", "cancel"]):
                return "DELETE_TASK", 0.91

        if any(w in text_lower for w in ["project", "repo", "codebase"]):
            if any(w in text_lower for w in ["create", "add", "start", "new"]):
                return "CREATE_PROJECT", 0.93
            return "PROJECT_QUERY", 0.88

        if any(w in text_lower for w in ["remember", "memory", "recall", "preference"]):
            if any(w in text_lower for w in ["remember that", "save memory", "store memory"]):
                return "MEMORY_SAVE", 0.95
            return "MEMORY_QUERY", 0.89

        if any(w in text_lower for w in ["status", "diagnostics", "health", "telemetry"]):
            return "SYSTEM_STATUS", 0.95

        return "CHAT", 0.70

    def generate_plan(
        self,
        goal: str,
        available_tools: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        # Deterministic fallback plan generation
        goal_lower = goal.lower()
        steps = []

        if "create task" in goal_lower or "add task" in goal_lower:
            steps.append({
                "step_number": 1,
                "tool_name": "task_create",
                "parameters": {"title": goal.replace("create task", "").replace("add task", "").strip() or "New Task"},
                "risk_level": "LOW_RISK"
            })
        elif "list tasks" in goal_lower:
            steps.append({
                "step_number": 1,
                "tool_name": "task_list",
                "parameters": {},
                "risk_level": "LOW_RISK"
            })
        elif "status" in goal_lower:
            steps.append({
                "step_number": 1,
                "tool_name": "system_status",
                "parameters": {},
                "risk_level": "LOW_RISK"
            })

        return steps


class OpenAICompatibleProvider(BaseAIProvider):
    """
    Provider integrating with OpenAI or OpenAI-compatible endpoints (Ollama, vLLM, LMStudio).
    Uses non-blocking httpx client with fallback to MockAIProvider if network fails.
    """

    def __init__(self):
        self.api_key = settings.AI_API_KEY or ""
        self.model = settings.AI_MODEL or "gpt-4o-mini"
        self.temperature = settings.AI_TEMPERATURE
        self.max_tokens = settings.AI_MAX_TOKENS
        self.fallback = MockAIProvider()

    def generate_response(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not self.api_key:
            return self.fallback.generate_response(prompt, context)

        try:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            system_prompt = (
                "You are JARVIS, an autonomous multimodal AI operating system assistant. "
                "Maintain a concise, tactical, and capable tone. Do not use verbose filler."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens
            }
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    return data["choices"][0]["message"]["content"].strip()
                logger.warning(f"OpenAI API responded with {res.status_code}: {res.text}")
                return self.fallback.generate_response(prompt, context)
        except Exception as e:
            logger.warning(f"OpenAI call failed, falling back to local reasoning: {e}")
            return self.fallback.generate_response(prompt, context)

    def classify_intent(self, text: str, candidate_intents: List[str]) -> Tuple[str, float]:
        if not self.api_key:
            return self.fallback.classify_intent(text, candidate_intents)

        try:
            prompt = (
                f"Classify the following user input into exactly one of these intents: {', '.join(candidate_intents)}.\n"
                f"Input: \"{text}\"\n"
                f"Respond with JSON format: {{\"intent\": \"INTENT_NAME\", \"confidence\": 0.95}}"
            )
            with httpx.Client(timeout=8.0) as client:
                res = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.0
                    }
                )
                if res.status_code == 200:
                    data = res.json()
                    content = json.loads(data["choices"][0]["message"]["content"])
                    return content.get("intent", "CHAT"), float(content.get("confidence", 0.8))
        except Exception as e:
            logger.warning(f"Provider intent classification error: {e}")

        return self.fallback.classify_intent(text, candidate_intents)

    def generate_plan(
        self,
        goal: str,
        available_tools: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        # Defaults to fallback rule-based planner for safety unless specialized
        return self.fallback.generate_plan(goal, available_tools, context)


def get_ai_provider() -> BaseAIProvider:
    """Factory selecting AI provider based on environment configuration."""
    provider_name = (settings.AI_PROVIDER or "mock").lower()
    if provider_name == "openai" and settings.AI_API_KEY:
        return OpenAICompatibleProvider()
    return MockAIProvider()
