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
    strategy_used: str  # "rule", "ml", "llm_fallback", "context"
    raw_input: str
    action: Optional[str] = None
    slots: Dict[str, Any] = {}
    context_reference: Optional[str] = None
    requires_clarification: bool = False
    clarification_question: Optional[str] = None
    execution_plan: Optional[List[Dict[str, Any]]] = None


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
        "MULTI_STEP_COMMAND",
        # Step 9.2 Browser Automation Intents
        "BROWSER_SEARCH",
        "BROWSER_NAVIGATE",
        "BROWSER_PAGE_INFO",
        "BROWSER_CLICK_ELEMENT",
        "BROWSER_CLOSE",
        # Music & Spotify Intents
        "MUSIC_PLAY",
        "MUSIC_PAUSE",
        "MUSIC_RESUME",
        "MUSIC_NEXT",
        "MUSIC_PREVIOUS",
        "MUSIC_SEARCH",
        "MUSIC_VOLUME",
        "MUSIC_STOP",
        "UNKNOWN"
    ]

    @staticmethod
    def normalize_query(text: str) -> str:
        s = text.strip()
        # Remove polite / conversational leading filler phrases and 'now'
        s = re.sub(
            r"^(?:(?:can|could|would)\s+you\s+(?:please\s+)?|(?:please\s+)|(?:jarvis,?\s*)|(?:hey\s+jarvis,?\s*)|(?:hi\s+jarvis,?\s*)|(?:ok\s+jarvis,?\s*)|(?:now\s+))",
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

            # Step 9.2 Browser Automation: YouTube / Google / Web Search (Priority over general navigation)
            (re.compile(r"^(?:jarvis,?\s*)?search\s+youtube\s+for\s+(.+?\b(?:music|song|track|album|soundtrack)\b.*)$", re.I), "MUSIC_SEARCH", 0.995),
            (re.compile(r"^(?:jarvis,?\s*)?(?:open\s+(?:the\s+)?(?:website\s+)?|go\s+to\s+)?(youtube|google|wikipedia|github|chrome|edge|browser)\s*(?:,\s*|\s+and\s+|\s+then\s+|\s+)search(?:\s+for)?\s+(.+)$", re.I), "BROWSER_SEARCH", 0.99),
            (re.compile(r"^(?:jarvis,?\s*)?search\s+(youtube|google|wikipedia|github)\s+for\s+(.+)$", re.I), "BROWSER_SEARCH", 0.99),
            (re.compile(r"^(?:jarvis,?\s*)?search\s+for\s+(.+)\s+on\s+(youtube|google|wikipedia|github|chrome|web)$", re.I), "BROWSER_SEARCH", 0.99),
            (re.compile(r"^(?:jarvis,?\s*)?(?:search\s+the\s+web\s+for|search\s+web\s+for|search\s+google\s+for|google)\s+(.+)$", re.I), "BROWSER_SEARCH", 0.98),

            # Music & Streaming: Dedicated Controls & Variations (Priority over generic commands)
            (re.compile(r"^(?:jarvis,?\s*)?(?:set|turn|change)\s+(?:the\s+)?(?:spotify\s+)?volume\s+(?:to\s+)?(\d+)\s*%?[\s?!.]*$", re.I), "MUSIC_VOLUME", 0.99),
            (re.compile(r"^(?:jarvis,?\s*)?(?:turn\s+(?:the\s+)?(?:music|volume)\s+(?:up|down)(?:\s+to\s+(\d+)\s*%?)?)[\s?!.]*$", re.I), "MUSIC_VOLUME", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:pause(?:\s+(?:the\s+)?(?:music|playback|song|track|spotify|it))?|hold\s+on\s+the\s+music)[\s?!.]*$", re.I), "MUSIC_PAUSE", 0.99),
            (re.compile(r"^(?:jarvis,?\s*)?(?:resume(?:\s+(?:the\s+)?(?:music|playback|playing|song|track|spotify|what\s+i\s+was\s+listening\s+to|it))?|continue\s+playing|unpause)[\s?!.]*$", re.I), "MUSIC_RESUME", 0.99),
            (re.compile(r"^(?:jarvis,?\s*)?(?:skip(?:\s+(?:this\s+)?(?:song|track|one))?|play\s+(?:the\s+)?next\s+(?:track|song)|next\s+(?:song|track)|skip\s+to\s+next)[\s?!.]*$", re.I), "MUSIC_NEXT", 0.99),
            (re.compile(r"^(?:jarvis,?\s*)?(?:play\s+(?:the\s+)?previous\s+(?:track|song)|previous\s+(?:song|track)|go\s+back\s+(?:to\s+)?(?:the\s+)?previous\s+(?:song|track)|play\s+(?:the\s+)?last\s+track)[\s?!.]*$", re.I), "MUSIC_PREVIOUS", 0.99),
            (re.compile(r"^(?:jarvis,?\s*)?(?:stop\s+(?:the\s+)?(?:music|playback|song|track|spotify)|stop\s+playing)[\s?!.]*$", re.I), "MUSIC_STOP", 0.99),
            (re.compile(r"^(?:jarvis,?\s*)?(?:search\s+spotify\s+for\s+|find\s+on\s+spotify\s+)(.+)$", re.I), "MUSIC_SEARCH", 0.99),
            (re.compile(r"^(?:jarvis,?\s*)?(?:search\s+for|find)\s+(.+?)\s+by\s+(.+)$", re.I), "MUSIC_SEARCH", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:search\s+for|find)\s+(?:song|track|music):?\s*(.+)$", re.I), "MUSIC_SEARCH", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:search\s+for|find)\s+(?!the\s+web\b|web\b|google\b|youtube\b|wikipedia\b|github\b|all\b)(.+)$", re.I), "MUSIC_SEARCH", 0.96),
            (re.compile(r"^(?:jarvis,?\s*)?(?:play|put\s+on|listen\s+to|spin)\s+(?:some\s+|that\s+)?(.+?)\s+(?:by|from)\s+(.+)$", re.I), "MUSIC_PLAY", 0.99),
            (re.compile(r"^(?:jarvis,?\s*)?(?:play|put\s+on|listen\s+to|spin)\s+(?:some\s+)?([a-zA-Z\s]+?)\s+music[\s?!.]*$", re.I), "MUSIC_PLAY", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:play|put\s+on|listen\s+to|spin)\s+(?:some\s+)?(green day|queen|the beatles|linkin park|coldplay|eminem|taylor swift|ed sheeran|nirvana|metallica|ac/dc|pink floyd|radiohead|daft punk|drake)[\s?!.]*$", re.I), "MUSIC_PLAY", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:play|put\s+on|listen\s+to|spin)\s+(?:their\s+)?(?:other\s+)?(?:popular\s+)?(?:song|track)[\s?!.]*$", re.I), "MUSIC_PLAY", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:play|put\s+on|listen\s+to|spin)\s+(.+)$", re.I), "MUSIC_PLAY", 0.95),

            # Step 9.2 Browser Automation: Page Info & Title
            (re.compile(r"^(?:jarvis,?\s*)?(?:what(?:'s|\s+is)\s+(?:the\s+)?(?:current\s+|active\s+)?(?:title|page\s+title|webpage\s+title)(?:\s+of\s+(?:this|the|the\s+current|the\s+active)?\s*(?:webpage|page|website|tab))?|what\s+is\s+(?:this|the\s+current|the)\s+webpage\s+title|what\s+page\s+is\s+open|what\s+webpage\s+is\s+open|get\s+(?:current\s+)?page\s+info|get\s+current\s+webpage\s+title|read\s+(?:the\s+)?(?:current\s+)?(?:page\s+)?title)[\s?!.]*$", re.I), "BROWSER_PAGE_INFO", 0.99),

            # Step 9.2 Browser Automation: Click Element
            (re.compile(r"^(?:jarvis,?\s*)?(?:click|press|tap)\s+(?:on\s+)?(?:the\s+)?(?:element|button|link|control)?\s*(?:named|called|titled|with text|selector)?\s*[:\"']?([^\"']+)[\"']?$", re.I), "BROWSER_CLICK_ELEMENT", 0.98),

            # Step 9.2 Browser Automation: Close Browser
            (re.compile(r"^(?:jarvis,?\s*)?(?:close\s+(?:the\s+)?(?:automated\s+|controlled\s+)?browser(?:\s+session)?|close\s+the\s+browser\s+window)[\s?!.]*$", re.I), "BROWSER_CLOSE", 0.98),

            # Step 9.2 Browser Automation: Explicit Browser Navigation & Security Test URIs
            (re.compile(r"^(?:jarvis,?\s*)?(?:open|navigate to|browse to|go to)\s+(.+?)\s+in\s+(?:the\s+)?(?:automated|controlled|isolated|current|active)?\s*browser$", re.I), "BROWSER_NAVIGATE", 0.99),
            (re.compile(r"^(?:jarvis,?\s*)?(?:open|navigate to|browse to)\s+(?:the\s+)?(?:website|url|webpage|page|link)\s+(.+)$", re.I), "BROWSER_NAVIGATE", 0.99),
            (re.compile(r"^(?:jarvis,?\s*)?(?:navigate to|browse to|go to|open)\s+(javascript[:(].*|data:.*|file:.*|vbscript:.*|https?://127\.0\.0\.1\S*|https?://localhost\S*|127\.0\.0\.1\S*|localhost\S*)$", re.I), "BROWSER_NAVIGATE", 0.99),

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
            (re.compile(r"^(?:jarvis,?\s*)?(?:open|launch)\s+(?:my\s+)?(?:folder\s+|directory\s+)?(downloads|documents|desktop|project|project folder|my project)\s*(?:folder|directory)?[\s?!.]*$", re.I), "OPEN_FOLDER", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:open|view)\s+(?:my\s+)?(downloads|documents|desktop|project|my project)\s+folder[\s?!.]*$", re.I), "OPEN_FOLDER", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?open\s+(?:my\s+)?project(?:\s+folder)?[\s?!.]*$", re.I), "OPEN_FOLDER", 0.98),

            # Windows Local Agent: Open Application (Allowlisted & candidate apps)
            (re.compile(r"^(?:jarvis,?\s*)?(?:open|launch|start|run|take me to|bring me to|switch to)\s+(?:the\s+)?(?:application\s+|app\s+|program\s+)?(vscode|vs code|visual studio code|code|chrome|google chrome|notepad|calculator|calc|explorer|file explorer|terminal|windows terminal|edge|microsoft edge|spotify)$", re.I), "OPEN_APPLICATION", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:open|launch|start)\s+(?:my\s+)?browser[\s?!.]*$", re.I), "OPEN_APPLICATION", 0.98),
            (re.compile(r"^(?:jarvis,?\s*)?(?:open|launch|start|run|take me to|bring me to|switch to)\s+(?:(?:an?|the)\s+)?(?:(?:application|app|program)(?::|\b))\s*(?:named\s+|called\s+|titled\s+|:\s*)?(.+)$", re.I), "OPEN_APPLICATION", 0.98),
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
            (re.compile(r"^(?:create|add|schedule|new)\s+(?:a\s+)?task\s+(?:to\s+|called\s+|named\s+|:\s+)?(.+)", re.I), "CREATE_TASK", 0.98),
            (re.compile(r"^(?:create|add|schedule|new)\s+task:?\s*(.+)", re.I), "CREATE_TASK", 0.98),
            (re.compile(r"^remind me to\s+(.+)", re.I), "CREATE_TASK", 0.98),

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
            m = re.search(r"(?:open|launch|start|run|take me to|bring me to|switch to|navigate to)\s+(?:(?:an?|the)\s+)?(?:(?:application|app|program)(?::|\b))?\s*(?:named\s+|called\s+|titled\s+|:\s*)?(.+)", cleaned, re.I)
            if m:
                app_raw = m.group(1).strip().lower().rstrip(".?!,:;")
                # Normalize aliases
                if "vs code" in app_raw or "vscode" in app_raw or "visual studio code" in app_raw:
                    entities["application"] = "vscode"
                elif "chrome" in app_raw:
                    entities["application"] = "chrome"
                elif "edge" in app_raw:
                    entities["application"] = "edge"
                elif "spotify" in app_raw:
                    entities["application"] = "spotify"
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
            elif "project" in lower:
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

        # Step 9.2 Browser Automation: Search entity extraction
        if intent == "BROWSER_SEARCH":
            site = "youtube" if "youtube" in cleaned.lower() else ("google" if "google" in cleaned.lower() else "web")
            if "wikipedia" in cleaned.lower():
                site = "wikipedia"
            elif "github" in cleaned.lower():
                site = "github"

            # Match: "open youtube and search for X", "search youtube for X", "search for X on youtube", "search google for X"
            query = ""
            m1 = re.search(r"(?:and\s+search|then\s+search|search)(?:\s+for)?\s+(.+)$", cleaned, re.I)
            m2 = re.search(r"search\s+(?:for\s+)?(.+?)\s+on\s+(?:youtube|google|wikipedia|github)", cleaned, re.I)
            if m2:
                query = m2.group(1).strip()
            elif m1:
                query = m1.group(1).strip()
            else:
                query = cleaned

            # Strip leading site prefix and 'for' (e.g. 'google for Java interview questions' -> 'Java interview questions')
            query = re.sub(r"^(?:youtube|google|wikipedia|github)\s+for\s+", "", query, flags=re.I).strip()
            query = re.sub(r"^(?:youtube|google|wikipedia|github)\s+", "", query, flags=re.I).strip()
            query = re.sub(r"^for\s+", "", query, flags=re.I).strip()
            query = re.sub(r"\s+on\s+(?:youtube|google|wikipedia|github).*$", "", query, flags=re.I).strip()
            # Strip trailing verification or action clauses (e.g. ", and verify the results", "and open the results")
            query = re.sub(r",?\s*(?:and\s+|then\s+)?(?:verify|check|show|open|display)\s+(?:the\s+)?results?.*$", "", query, flags=re.I).strip()
            query = query.strip("\"'.,?!")

            base_urls = {
                "youtube": "https://www.youtube.com",
                "google": "https://www.google.com",
                "wikipedia": "https://www.wikipedia.org",
                "github": "https://github.com",
                "web": "https://www.google.com"
            }
            entities["site"] = site
            entities["query"] = query
            entities["url"] = base_urls.get(site, "https://www.google.com")

        # Step 9.2 Browser Automation: Explicit navigation entity extraction
        if intent == "BROWSER_NAVIGATE":
            m = re.search(r"(?:open|navigate to|browse to|go to)\s+(?:(?:the\s+)?(?:website|url|webpage|page|link)\s+)?(.+?)(?:\s+in\s+(?:the\s+)?(?:automated|controlled|isolated|current|active)?\s*browser)?$", cleaned, re.I)
            target = m.group(1).strip() if m else cleaned
            target_clean = target.lower().rstrip(".?!,:;")
            if "youtube" in target_clean and not target_clean.startswith(("http", "www")):
                entities["url"] = "https://www.youtube.com"
            elif "google" in target_clean and not target_clean.startswith(("http", "www")):
                entities["url"] = "https://www.google.com"
            elif "github" in target_clean and not target_clean.startswith(("http", "www")):
                entities["url"] = "https://github.com"
            else:
                entities["url"] = target

        # Step 9.2 Browser Automation: Click element entity extraction
        if intent == "BROWSER_CLICK_ELEMENT":
            m = re.search(r"(?:click|press|tap)\s+(?:on\s+)?(?:the\s+)?(?:element|button|link|control)?\s*(?:named|called|titled|with text|selector)?\s*[:\"']?([^\"']+)[\"']?", cleaned, re.I)
            raw_target = m.group(1).strip() if m else cleaned
            raw_target = re.sub(r"^(?:an?\s+)?(?:element|button|link|control)\s+(?:named|called|titled)\s+", "", raw_target, flags=re.I).strip()
            entities["target"] = raw_target
            entities["selector"] = raw_target

        # Step 9.2 Browser Automation: Page Info
        if intent == "BROWSER_PAGE_INFO":
            entities["action"] = "get_page_info"

        # Step 9.2 Browser Automation: Close
        if intent == "BROWSER_CLOSE":
            entities["action"] = "close"

        # Music & Streaming Intents
        if intent == "MUSIC_PLAY":
            entities["action"] = "play"
            if "spotify" in cleaned.lower() and "youtube" not in cleaned.lower():
                entities["music_service"] = "spotify"
            elif "youtube" in cleaned.lower() and "spotify" not in cleaned.lower():
                entities["music_service"] = "youtube"

            m_by = re.search(r"(?:play|put\s+on|listen\s+to|spin)\s+(?:some\s+|that\s+)?(.+?)\s+(?:by|from)\s+(.+)$", cleaned, re.I)
            m_genre = re.search(r"(?:play|put\s+on|listen\s+to|spin)\s+(?:some\s+)?([a-zA-Z\s]+?)\s+music[\s?!.]*$", cleaned, re.I)
            m_pronoun = re.search(r"(?:play|put\s+on)\s+(?:their|his|her)\s+(?:other\s+)?(?:popular\s+)?(?:song|track)", cleaned, re.I)

            if m_pronoun:
                entities["context_reference"] = "previous_artist"
                entities["track"] = "popular song"
            elif m_by:
                t = m_by.group(1).strip().strip("\"'")
                a = m_by.group(2).strip().strip("\"'.,?!")
                t = re.sub(r"^(?:that|the)\s+", "", t, flags=re.I).strip()
                entities["track"] = t
                entities["artist"] = a
            elif m_genre:
                g = m_genre.group(1).strip().lower()
                entities["genre"] = g
            else:
                m_direct = re.search(r"(?:play|put\s+on|listen\s+to|spin)\s+(?:some\s+)?(.+)$", cleaned, re.I)
                target = m_direct.group(1).strip().strip("\"'.,?!") if m_direct else cleaned
                known_artists = ["green day", "queen", "the beatles", "linkin park", "coldplay", "nirvana", "metallica", "ac/dc", "pink floyd", "radiohead", "daft punk", "drake", "eminem", "taylor swift", "ed sheeran"]
                if target.lower() in known_artists:
                    entities["artist"] = target
                elif "music" in target.lower() or target.lower() in ["rock", "pop", "jazz", "classical", "hip hop", "lofi", "study", "metal", "electronic"]:
                    entities["genre"] = re.sub(r"\s+music$", "", target, flags=re.I).strip()
                else:
                    entities["track"] = target

        elif intent == "MUSIC_SEARCH":
            entities["action"] = "search"
            if "spotify" in cleaned.lower() and "youtube" not in cleaned.lower():
                entities["music_service"] = "spotify"
            elif "youtube" in cleaned.lower() and "spotify" not in cleaned.lower():
                entities["music_service"] = "youtube"
            m_yt = re.search(r"(?:search\s+youtube\s+for|search\s+for)\s+(.+?)(?:\s+on\s+youtube)?[\s?!.]*$", cleaned, re.I)
            m_by = re.search(r"(?:search\s+for|find|look\s+up)\s+(.+?)\s+by\s+(.+?)(?:\s+on\s+(?:spotify|youtube))?[\s?!.]*$", cleaned, re.I)
            if m_by:
                t = m_by.group(1).strip().strip("\"'")
                a = m_by.group(2).strip().strip("\"'.,?!")
                t = re.sub(r"^(?:the\s+)?(?:official\s+)?(?:music\s+)?video\s+(?:for|of)\s+", "", t, flags=re.I).strip()
                entities["track"] = t
                entities["artist"] = a
                entities["query"] = f"{t} {a}"
            elif "youtube" in cleaned.lower() and m_yt:
                q = m_yt.group(1).strip().strip("\"'.,?!")
                entities["query"] = q
                entities["track"] = q
            else:
                m_q = re.search(r"(?:search\s+(?:spotify|youtube)\s+for|search\s+for|find|look\s+up)\s+(?:song\s+|track\s+|music\s+)?(.+?)(?:\s+on\s+(?:spotify|youtube))?[\s?!.]*$", cleaned, re.I)
                q = m_q.group(1).strip().strip("\"'.,?!") if m_q else cleaned
                entities["query"] = q
                entities["track"] = q

        elif intent in ["MUSIC_PAUSE", "MUSIC_STOP"]:
            entities["action"] = "pause"
            entities["context_reference"] = "active_playback"

        elif intent == "MUSIC_RESUME":
            entities["action"] = "resume"
            entities["context_reference"] = "active_playback"

        elif intent == "MUSIC_NEXT":
            entities["action"] = "next"
            entities["context_reference"] = "active_playback"

        elif intent == "MUSIC_PREVIOUS":
            entities["action"] = "previous"
            entities["context_reference"] = "active_playback"

        elif intent == "MUSIC_VOLUME":
            entities["action"] = "volume"
            m_vol = re.search(r"(\d+)", cleaned)
            if m_vol:
                entities["volume_percent"] = int(m_vol.group(1))
            elif "up" in cleaned.lower():
                entities["volume_direction"] = "up"
                entities["volume_percent"] = 70
            elif "down" in cleaned.lower():
                entities["volume_direction"] = "down"
                entities["volume_percent"] = 30
            else:
                entities["volume_percent"] = 50

        return entities

    def _build_result(
        self,
        intent: str,
        confidence: float,
        entities: Dict[str, Any],
        strategy_used: str,
        raw_input: str,
        context: Optional[Any] = None
    ) -> IntentDetectionResult:
        """Constructs rich structured IntentDetectionResult with slots and context resolution."""
        action = entities.get("action")
        slots = {k: v for k, v in entities.items() if k not in ["command", "prompt", "sub_commands"]}
        context_ref = entities.get("context_reference")
        requires_clarif = False
        clarif_q = None

        # Context-aware follow-up resolution
        if context_ref == "previous_artist" and not entities.get("artist"):
            resolved_artist = None
            if context:
                # Check recent memories or visual context or conversation
                if hasattr(context, "relevant_memories") and context.relevant_memories:
                    for m in context.relevant_memories:
                        text = m.get("content", "").lower()
                        for band in ["green day", "queen", "the beatles", "linkin park", "coldplay", "nirvana"]:
                            if band in text:
                                resolved_artist = band.title()
                                break
            if resolved_artist:
                entities["artist"] = resolved_artist
                slots["artist"] = resolved_artist
            else:
                requires_clarif = True
                clarif_q = "Which artist's songs would you like me to play?"

        # Clarification if intent has no target
        if intent == "MUSIC_PLAY" and not any(k in entities for k in ["track", "artist", "genre", "context_reference"]):
            requires_clarif = True
            clarif_q = "What song, artist, or genre would you like me to play?"

        return IntentDetectionResult(
            intent=intent,
            confidence=confidence,
            entities=entities,
            strategy_used=strategy_used,
            raw_input=raw_input,
            action=action,
            slots=slots,
            context_reference=context_ref,
            requires_clarification=requires_clarif,
            clarification_question=clarif_q
        )

    def detect(
        self,
        user_message: str,
        input_type: Optional[str] = None,
        has_image: bool = False,
        context: Optional[Any] = None
    ) -> IntentDetectionResult:
        cleaned = user_message.strip()
        norm_msg = self.normalize_query(cleaned)
        if not cleaned:
            if has_image:
                return self._build_result(
                    intent="IMAGE_ANALYSIS",
                    confidence=0.95,
                    entities={"prompt": "Analyze image payload"},
                    strategy_used="multimodal_context",
                    raw_input=""
                )
            return self._build_result(
                intent="UNKNOWN",
                confidence=0.0,
                entities={},
                strategy_used="rule",
                raw_input=user_message
            )

        # Stage 0: Security check for explicit arbitrary shell execution attempts
        for pattern, rule_intent, rule_conf in self.rules[:2]:
            if pattern.search(cleaned) or (norm_msg and pattern.search(norm_msg)):
                logger.warning(f"[INTENT] Security block triggered: '{rule_intent}'")
                return self._build_result(
                    intent="BLOCKED_COMMAND",
                    confidence=0.99,
                    entities={"command": cleaned},
                    strategy_used="rule",
                    raw_input=cleaned
                )

        # Stage 0.5: Multi-Step Agent Command Decomposition (Step 9.1)
        from app.ai.decomposer import multi_step_decomposer
        sub_commands = multi_step_decomposer.decompose(norm_msg or cleaned)
        if len(sub_commands) > 1:
            logger.info(f"[INTENT] Multi-step command detected ({len(sub_commands)} steps): {sub_commands}")
            return self._build_result(
                intent="MULTI_STEP_COMMAND",
                confidence=0.98,
                entities={"sub_commands": sub_commands, "steps_count": len(sub_commands)},
                strategy_used="multi_step_decomposition",
                raw_input=cleaned
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
                return self._build_result(
                    intent=rule_intent,
                    confidence=rule_conf,
                    entities=entities,
                    strategy_used="rule",
                    raw_input=cleaned,
                    context=context
                )

        # Stage 1.5: If an image is explicitly attached and user is asking a question or requesting analysis
        if has_image or input_type == "image":
            lower_msg = cleaned.lower()
            if any(w in lower_msg for w in ["read", "ocr", "text", "error", "log"]):
                return self._build_result(
                    intent="OCR_REQUEST",
                    confidence=0.96,
                    entities={"prompt": cleaned},
                    strategy_used="multimodal_payload",
                    raw_input=cleaned
                )
            return self._build_result(
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
            return self._build_result(
                intent=ml_intent,
                confidence=ml_conf,
                entities=entities,
                strategy_used="ml",
                raw_input=cleaned,
                context=context
            )

        # Stage 3: LLM Provider Fallback (if confidence is below threshold)
        logger.info(f"[INTENT] ML confidence {ml_conf} < threshold {self.confidence_threshold}, falling back to AI provider")
        provider = get_ai_provider()
        llm_intent, llm_conf = provider.classify_intent(cleaned, self.CANDIDATE_INTENTS)
        entities = self.extract_entities(cleaned, llm_intent)

        return self._build_result(
            intent=llm_intent,
            confidence=llm_conf,
            entities=entities,
            strategy_used="llm_fallback",
            raw_input=cleaned,
            context=context
        )


intent_detector = IntentDetector()
