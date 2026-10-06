import re
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from app.core.config import settings
from app.ai.ml_classifier import ml_intent_classifier
from app.ai.providers import get_ai_provider

logger = logging.getLogger("jarvis.ai.intent")


class IntentDetectionResult(BaseModel):
    intent: str
    confidence: float
    entities: Dict[str, Any] = {}
    strategy_used: str  # "rule", "ml", "llm_fallback"
    raw_input: str


class IntentDetector:
    """
    Hybrid Intent Detection Engine:
    User Input -> Rule / Deterministic Checks -> ML Intent Classifier -> LLM Fallback
    """

    CANDIDATE_INTENTS = [
        "CHAT",
        "QUESTION",
        "PROJECT_ANALYSIS",
        "CREATE_TASK",
        "UPDATE_TASK",
        "DELETE_TASK",
        "LIST_TASKS",
        "CREATE_PROJECT",
        "UPDATE_PROJECT",
        "PROJECT_QUERY",
        "MEMORY_QUERY",
        "MEMORY_SAVE",
        "SYSTEM_STATUS",
        "OPEN_APPLICATION",
        "OPEN_URL",
        "GET_SYSTEM_INFO",
        "GET_CURRENT_TIME",
        "LIST_ALLOWED_DIRECTORY",
        "OPEN_FILE",
        "OPEN_FOLDER",
        "SCREEN_ANALYSIS",
        "OCR_REQUEST",
        "VISION_QUERY",
        "IMAGE_ANALYSIS",
        "VISUAL_EXPLANATION",
        "SCREEN_CONTEXT_REQUEST",
        "BLOCKED_COMMAND",
        "GENERAL_COMMAND",
        "UNKNOWN"
    ]

    @staticmethod
    def normalize_query(text: str) -> str:
        s = text.strip()
        # Remove polite / conversational leading filler phrases
        s = re.sub(
            r"^(?:(?:can|could|would)\s+you\s+(?:please\s+)?|(?:please\s+)|(?:jarvis,?\s*)|(?:hey\s+jarvis,?\s*)|(?:hi\s+jarvis,?\s*)|(?:ok\s+jarvis,?\s*))",
            "",
            s,
            flags=re.I
        ).strip()
        # Strip trailing punctuation
        s = re.sub(r"[?!.]+$", "", s).strip()
        return s

    def __init__(self):
        self.confidence_threshold = settings.INTENT_CONFIDENCE_THRESHOLD

        # Exact and high-confidence deterministic patterns
        self.rules = [
            # Security: Explicitly block arbitrary shell execution attempts
            (re.compile(r"^(?:jarvis,?\s*)?(?:run|execute|eval)\s+(?:this\s+)?(?:powershell|cmd|command|bash|shell|python|script):?\s*(.+)$", re.I), "BLOCKED_COMMAND", 0.99),
            (re.compile(r"^(?:jarvis,?\s*)?(?:powershell|cmd|bash)\s+(.+)$", re.I), "BLOCKED_COMMAND", 0.99),

            # Multimodal Vision & Screen Intelligence (Step 9)
            (re.compile(r"^(?:jarvis,?\s*)?(?:what(?:'s|\s+is)\s+(?:on|currently\s+on)\s+my\s+screen|what\s+am\s+i\s+looking\s+at|what\s+application\s+am\s+i\s+using|what\s+app\s+is\s+open|capture(?:\s+my)?\s+screen|take\s+a\s+screenshot|screenshot)[\s?!.]*$", re.I), "SCREEN_ANALYSIS", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:read\s+.*(?:error|screenshot|text|log)|what\s+does\s+this\s+screenshot\s+say|extract\s+text(?:\s+from\s+(?:this\s+)?image)?|ocr\s+(?:this|image|screenshot)?|read\s+this\s+text)[\s?!.]*$", re.I), "OCR_REQUEST", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:find\s+the\s+error\s+(?:on|in)\s+(?:my\s+screen|this\s+screenshot)|what(?:'s|\s+is)\s+wrong\s+with\s+this\s+error|can\s+you\s+read\s+this\s+error|what\s+(?:is|causes)\s+this\s+error)[\s?!.]*$", re.I), "VISION_QUERY", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:what\s+button\s+should\s+i\s+(?:click|press)(?:\s+to\s+continue)?|what\s+should\s+i\s+click(?:\s+to\s+continue)?|where\s+do\s+i\s+click)[\s?!.]*$", re.I), "SCREEN_CONTEXT_REQUEST", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:explain\s+this\s+(?:image|screenshot|code|webpage)|what\s+(?:is\s+in|does)\s+this\s+(?:image|screenshot)\s*(?:show|say|contain|have)?|what\s+is\s+this\s+(?:image|webpage|diagram)\s*(?:about)?|analyze\s+this\s+(?:image|screenshot|photo)|describe\s+(?:and\s+analyze\s+)?this\s+(?:image|screenshot))[\s?!.]*$", re.I), "IMAGE_ANALYSIS", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:visual\s+explanation|explain\s+visually|describe\s+this\s+image)[\s?!.]*$", re.I), "VISUAL_EXPLANATION", 0.98),

            # Windows Local Agent: Open URL (check before general app open)
            (re.compile(r"^(?:jarvis,?\s*)?(?:open|navigate to|browse to|launch|go to|take me to)\s+(https?://\S+|www\.\S+|youtube(?:\.com)?|google(?:\.com)?|github(?:\.com)?|reddit(?:\.com)?|x(?:\.com)?|twitter(?:\.com)?)$", re.I), "OPEN_URL", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:go to|take me to|open)\s+(youtube|google|github|reddit)[\s?!.]*$", re.I), "OPEN_URL", 0.98),

            # Windows Local Agent: Open Folder
            (re.compile(r"^(?:jarvis,?\s*)?(?:open|launch)\s+(?:my\s+)?(?:folder\s+|directory\s+)?(downloads|documents|desktop)\s+(?:folder|directory)[\s?!.]*$", re.I), "OPEN_FOLDER", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:open|view)\s+(?:my\s+)?(downloads|documents|desktop)\s+folder[\s?!.]*$", re.I), "OPEN_FOLDER", 0.98),

            # Windows Local Agent: Open Application (Allowlisted & candidate apps)
            (re.compile(r"^(?:jarvis,?\s*)?(?:open|launch|start|run|take me to|bring me to|switch to)\s+(?:the\s+)?(?:application\s+|app\s+|program\s+)?(vscode|vs code|visual studio code|code|chrome|google chrome|notepad|calculator|calc|explorer|file explorer|terminal|edge|microsoft edge)$", re.I), "OPEN_APPLICATION", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:open|launch|start)\s+(?:my\s+)?browser[\s?!.]*$", re.I), "OPEN_APPLICATION", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:open|launch|start|run|take me to|bring me to|switch to)\s+(?:the\s+)?(?:application\s+|app\s+|program\s+)?([a-zA-Z0-9_\-\.]+(?:\.exe)?)$", re.I), "OPEN_APPLICATION", 0.95),
            (re.compile(r"^(?:jarvis,?\s*)?(?:open|launch|start|run|take me to)\s+application:?\s+(.+)$", re.I), "OPEN_APPLICATION", 0.98),

            # Windows Local Agent: Get Current Time
            (re.compile(r"^(?:jarvis,?\s*)?(?:what time is it|what is the time|current time|tell me the time|what's the time|what is the current local time|what is the current time|the time)[\s?!.]*$", re.I), "GET_CURRENT_TIME", 0.98),

            # Windows Local Agent: System Info
            (re.compile(r"^(?:jarvis,?\s*)?(?:what are my |show (?:my )?|get (?:my )?|display (?:my )?|tell me about (?:this )?)?(?:system info|system information|computer specs|pc specs|hardware info|system specifications|system specs|local machine specs|windows specs|computer)[\s?!.]*$", re.I), "GET_SYSTEM_INFO", 0.98),

            # Windows Local Agent: List Allowed Directory
            (re.compile(r"^(?:jarvis,?\s*)?(?:list|show|view|display|open)\s+(?:all\s+)?(?:my\s+)?(?:files\s+(?:in|on)\s+|directory\s+|folder:?\s+|contents\s+of\s+)?(desktop|documents|downloads)(?:\s+(?:files|directory|folder))?[\s?!.]*$", re.I), "LIST_ALLOWED_DIRECTORY", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:list|show)\s+(?:my\s+)?(downloads|documents|desktop)[\s?!.]*$", re.I), "LIST_ALLOWED_DIRECTORY", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:open\s+my\s+desktop\s+files)[\s?!.]*$", re.I), "LIST_ALLOWED_DIRECTORY", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:list\s+documents)[\s?!.]*$", re.I), "LIST_ALLOWED_DIRECTORY", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:list|show|view|display)\s+(?:all\s+)?(?:files\s+(?:in|on)\s+|directory\s+|folder:?\s+|contents\s+of\s+)(.+)$", re.I), "LIST_ALLOWED_DIRECTORY", 0.95),

            # Windows Local Agent: Open File
            (re.compile(r"^(?:jarvis,?\s*)?open (?:file|document):?\s+(.+)$", re.I), "OPEN_FILE", 0.95),
            (re.compile(r"^(?:jarvis,?\s*)?open (?:a\s+)?file (?:from|in) (downloads|documents|desktop)[\s?!.]*$", re.I), "OPEN_FILE", 0.95),
            (re.compile(r"^(?:jarvis,?\s*)?open (?:a\s+)?file (.+) (?:from|in) (downloads|documents|desktop)[\s?!.]*$", re.I), "OPEN_FILE", 0.95),

            # Project Analysis
            (re.compile(r"\b(analyz|check|inspect|audit).*(project|repo|codebase)\b", re.I), "PROJECT_ANALYSIS", 0.98),
            # Task listing
            (re.compile(r"^(list|show|display|get|view) (all )?(my )?(active |pending )?(tasks|todo|todos|jobs)", re.I), "LIST_TASKS", 0.98),
            (re.compile(r"^what tasks? (do i have|are pending|are scheduled|are active)", re.I), "LIST_TASKS", 0.98),

            # Task delete
            (re.compile(r"^(delete|remove|cancel|discard) task #?(\d+)", re.I), "DELETE_TASK", 0.98),

            # Task update
            (re.compile(r"^(update|mark|set|change) task #?(\d+)", re.I), "UPDATE_TASK", 0.95),

            # Task create
            (re.compile(r"^(create|add|schedule|new) task:?\s+(.+)", re.I), "CREATE_TASK", 0.95),
            (re.compile(r"^remind me to\s+(.+)", re.I), "CREATE_TASK", 0.95),

            # Project create
            (re.compile(r"^(create|add|start|new) project:?\s+(.+)", re.I), "CREATE_PROJECT", 0.95),
            (re.compile(r"^create a project called\s+(.+)", re.I), "CREATE_PROJECT", 0.98),

            # Project query
            (re.compile(r"^(list|show|display|view) (my |all )?projects", re.I), "PROJECT_QUERY", 0.98),
            (re.compile(r"^what projects? (do i have|am i working on)", re.I), "PROJECT_QUERY", 0.98),

            # Memory Save
            (re.compile(r"^(remember that|remember:|save memory:?|store memory:?)\s+(.+)", re.I), "MEMORY_SAVE", 0.98),

            # Memory Query
            (re.compile(r"^(what do you remember|recall my preferences?|search memories|what are my memories)", re.I), "MEMORY_QUERY", 0.95),

            # System Status
            (re.compile(r"^(system status|run diagnostics|check health|system telemetry|cluster status)", re.I), "SYSTEM_STATUS", 0.98),

            # Greetings / Chat
            (re.compile(r"^(hello|hi|hey|good morning|who are you|what can you do)[\s!.]*$", re.I), "CHAT", 0.98),
        ]

    def extract_entities(self, text: str, intent: str) -> Dict[str, Any]:
        """Extracts task titles, IDs, project names, statuses, and due dates."""
        entities: Dict[str, Any] = {}
        cleaned = text.strip()

        # Task ID extraction
        task_id_match = re.search(r"task #?(\d+)", cleaned, re.I)
        if task_id_match:
            try:
                entities["task_id"] = int(task_id_match.group(1))
            except ValueError:
                pass

        # Project ID extraction
        proj_id_match = re.search(r"project #?(\d+)", cleaned, re.I)
        if proj_id_match:
            try:
                entities["project_id"] = int(proj_id_match.group(1))
            except ValueError:
                pass

        # Status extraction
        if any(w in cleaned.lower() for w in ["completed", "done", "finished"]):
            entities["status"] = "COMPLETED"
        elif any(w in cleaned.lower() for w in ["in progress", "working"]):
            entities["status"] = "AI WORKING"
        elif any(w in cleaned.lower() for w in ["paused", "hold"]):
            entities["status"] = "WAITING FOR INPUT"

        # Priority extraction
        if "critical" in cleaned.lower():
            entities["priority"] = "CRITICAL"
        elif "high" in cleaned.lower():
            entities["priority"] = "HIGH"
        elif "low" in cleaned.lower():
            entities["priority"] = "LOW"
        elif "medium" in cleaned.lower():
            entities["priority"] = "MEDIUM"

        # Task creation title extraction
        if intent == "CREATE_TASK":
            # Match "create a task to finish my DBMS assignment tomorrow"
            m = re.search(r"(?:create|add|schedule|new)\s+(?:a\s+)?task\s+(?:to\s+|called\s+|:\s+)?(.+)", cleaned, re.I)
            if m:
                raw_title = m.group(1).strip()
                # Check for due date suffix like "tomorrow"
                if " tomorrow" in raw_title.lower():
                    entities["due_date"] = "tomorrow"
                    raw_title = re.sub(r"\s+tomorrow.*$", "", raw_title, flags=re.I)
                entities["task_title"] = raw_title.capitalize()
            elif re.search(r"^remind me to\s+(.+)", cleaned, re.I):
                m2 = re.search(r"^remind me to\s+(.+)", cleaned, re.I)
                entities["task_title"] = m2.group(1).strip().capitalize()
            else:
                entities["task_title"] = cleaned

        # Project creation name extraction
        if intent == "CREATE_PROJECT":
            m = re.search(r"(?:create|add|start|new)\s+(?:a\s+)?project\s+(?:called\s+|named\s+|:\s+)?(.+)", cleaned, re.I)
            if m:
                entities["project_name"] = m.group(1).strip().title()
            else:
                entities["project_name"] = "New Project"

        # Memory extraction
        if intent == "MEMORY_SAVE":
            m = re.search(r"(?:remember that|remember:|save memory:?|store memory:?)\s+(.+)", cleaned, re.I)
            if m:
                entities["memory_content"] = m.group(1).strip()
            else:
                entities["memory_content"] = cleaned

        # Windows Local Agent: Application extraction
        if intent == "OPEN_APPLICATION":
            m = re.search(r"(?:open|launch|start|run|take me to|bring me to|switch to|navigate to)\s+(?:the\s+)?(?:application:?\s+)?(.+)", cleaned, re.I)
            if m:
                app_raw = m.group(1).strip().lower().rstrip(".?!,:;")
                # Normalize aliases
                if "vs code" in app_raw or "vscode" in app_raw or "visual studio code" in app_raw:
                    entities["application"] = "vscode"
                elif "chrome" in app_raw:
                    entities["application"] = "chrome"
                elif "notepad" in app_raw:
                    entities["application"] = "notepad"
                elif "calc" in app_raw:
                    entities["application"] = "calculator"
                elif "explorer" in app_raw:
                    entities["application"] = "explorer"
                elif "terminal" in app_raw:
                    entities["application"] = "terminal"
                else:
                    entities["application"] = app_raw
            else:
                entities["application"] = cleaned.strip().lower().rstrip(".?!,:;")

        # Windows Local Agent: URL extraction
        if intent == "OPEN_URL":
            m = re.search(r"(?:open|navigate to|browse to|launch)\s+(\S+)", cleaned, re.I)
            if m:
                target_url = m.group(1).strip()
                if target_url.lower() == "youtube" or target_url.lower() == "youtube.com":
                    target_url = "https://youtube.com"
                elif target_url.lower() == "google" or target_url.lower() == "google.com":
                    target_url = "https://google.com"
                elif target_url.lower() == "github" or target_url.lower() == "github.com":
                    target_url = "https://github.com"
                entities["url"] = target_url
            else:
                entities["url"] = cleaned

        # Windows Local Agent: Directory extraction
        if intent == "LIST_ALLOWED_DIRECTORY":
            lower = cleaned.lower()
            if "download" in lower:
                entities["directory"] = "Downloads"
            elif "document" in lower:
                entities["directory"] = "Documents"
            elif "desktop" in lower:
                entities["directory"] = "Desktop"
            else:
                m = re.search(r"(?:files\s+(?:in|on)\s+|directory\s+|folder:?\s+|contents\s+of\s+)(.+)", cleaned, re.I)
                if m:
                    entities["directory"] = m.group(1).strip()
                else:
                    entities["directory"] = cleaned

        # Windows Local Agent: Open Folder extraction
        if intent == "OPEN_FOLDER":
            lower = cleaned.lower()
            if "download" in lower:
                entities["folder_path"] = "Downloads"
            elif "document" in lower:
                entities["folder_path"] = "Documents"
            else:
                entities["folder_path"] = "Desktop"

        # Windows Local Agent: File path extraction
        if intent == "OPEN_FILE":
            m = re.search(r"(?:open\s+(?:a\s+)?(?:file|document):?\s+)(.+)", cleaned, re.I)
            if m:
                entities["file_path"] = m.group(1).strip()
            elif "download" in cleaned.lower():
                entities["file_path"] = "a file from downloads"
            elif "document" in cleaned.lower():
                entities["file_path"] = "a file from documents"
            elif "desktop" in cleaned.lower():
                entities["file_path"] = "a file from desktop"
            else:
                entities["file_path"] = cleaned

        return entities

    def detect(
        self,
        user_message: str,
        input_type: Optional[str] = None,
        has_image: bool = False
    ) -> IntentDetectionResult:
        cleaned = user_message.strip()
        norm_msg = self.normalize_query(cleaned)
        if not cleaned:
            if has_image:
                return IntentDetectionResult(
                    intent="IMAGE_ANALYSIS",
                    confidence=0.95,
                    entities={"prompt": "Analyze image payload"},
                    strategy_used="multimodal_context",
                    raw_input=""
                )
            return IntentDetectionResult(
                intent="UNKNOWN",
                confidence=0.0,
                entities={},
                strategy_used="rule",
                raw_input=user_message
            )

        # Stage 1: Deterministic Rule Check (tests both normalized and raw input)
        for pattern, rule_intent, rule_conf in self.rules:
            matched_text = None
            if pattern.search(cleaned):
                matched_text = cleaned
            elif norm_msg and pattern.search(norm_msg):
                matched_text = norm_msg

            if matched_text:
                entities = self.extract_entities(matched_text, rule_intent)
                logger.info(f"[INTENT] Rule match: '{rule_intent}' with confidence {rule_conf}")
                return IntentDetectionResult(
                    intent=rule_intent,
                    confidence=rule_conf,
                    entities=entities,
                    strategy_used="rule",
                    raw_input=cleaned
                )

        # Stage 1.5: If an image is explicitly attached and user is asking a question or requesting analysis
        if has_image or input_type == "image":
            lower_msg = cleaned.lower()
            if any(w in lower_msg for w in ["read", "ocr", "text", "error", "log"]):
                return IntentDetectionResult(
                    intent="OCR_REQUEST",
                    confidence=0.96,
                    entities={"prompt": cleaned},
                    strategy_used="multimodal_payload",
                    raw_input=cleaned
                )
            return IntentDetectionResult(
                intent="IMAGE_ANALYSIS",
                confidence=0.95,
                entities={"prompt": cleaned},
                strategy_used="multimodal_payload",
                raw_input=cleaned
            )

        # Stage 2: ML Classifier (TF-IDF + LogisticRegression)
        ml_intent, ml_conf = ml_intent_classifier.predict(cleaned)
        logger.info(f"[INTENT] ML prediction: '{ml_intent}' with confidence {ml_conf}")

        if ml_conf >= self.confidence_threshold and ml_intent in self.CANDIDATE_INTENTS:
            entities = self.extract_entities(cleaned, ml_intent)
            return IntentDetectionResult(
                intent=ml_intent,
                confidence=ml_conf,
                entities=entities,
                strategy_used="ml",
                raw_input=cleaned
            )

        # Stage 3: LLM Provider Fallback (if confidence is below threshold)
        logger.info(f"[INTENT] ML confidence {ml_conf} < threshold {self.confidence_threshold}, falling back to AI provider")
        provider = get_ai_provider()
        llm_intent, llm_conf = provider.classify_intent(cleaned, self.CANDIDATE_INTENTS)
        entities = self.extract_entities(cleaned, llm_intent)

        return IntentDetectionResult(
            intent=llm_intent,
            confidence=llm_conf,
            entities=entities,
            strategy_used="llm_fallback",
            raw_input=cleaned
        )


intent_detector = IntentDetector()
