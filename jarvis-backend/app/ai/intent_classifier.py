import re
from enum import Enum
from typing import Dict, Any
from app.schemas.agent import IntentResult


class IntentType(str, Enum):
    GENERAL_CHAT = "GENERAL_CHAT"
    PROJECT_ANALYSIS = "PROJECT_ANALYSIS"
    OPEN_PROJECT = "OPEN_PROJECT"
    CREATE_TASK = "CREATE_TASK"
    SEARCH = "SEARCH"
    FILE_ANALYSIS = "FILE_ANALYSIS"
    SYSTEM_COMMAND = "SYSTEM_COMMAND"
    STUDY_HELP = "STUDY_HELP"
    MEMORY_QUERY = "MEMORY_QUERY"
    UNKNOWN = "UNKNOWN"


class IntentClassifier:
    """
    Initial Rule-based Intent Classifier for JARVIS.
    Designed with a clean interface so it can be swapped with a real ML/NLP model
    (e.g., fine-tuned BERT, Sentence Transformers, or LLM Few-Shot) in the future.
    """

    def __init__(self):
        # Keyword and regex pattern registry for initial rule-based matching
        self.rules: Dict[IntentType, list[re.Pattern]] = {
            IntentType.PROJECT_ANALYSIS: [
                re.compile(r"\b(analyz|check|inspect|audit|scan).*(project|repo|codebase|ast)\b", re.IGNORECASE),
                re.compile(r"\b(find|check for) (errors|bugs|issues|flaws)\b", re.IGNORECASE),
            ],
            IntentType.OPEN_PROJECT: [
                re.compile(r"\b(open|launch|load).*(project|workspace|repo|code)\b", re.IGNORECASE),
                re.compile(r"\b(open vs ?code|launch ide)\b", re.IGNORECASE),
            ],
            IntentType.CREATE_TASK: [
                re.compile(r"\b(create|add|schedule|new).*(task|todo|reminder|job)\b", re.IGNORECASE),
                re.compile(r"\b(remind me to|set a task)\b", re.IGNORECASE),
            ],
            IntentType.FILE_ANALYSIS: [
                re.compile(r"\b(analyz|read|inspect|parse|check).*(file|document|script|source)\b", re.IGNORECASE),
            ],
            IntentType.SYSTEM_COMMAND: [
                re.compile(r"\b(system|diagnostics|status|optimize|cluster|memory usage|cpu)\b", re.IGNORECASE),
                re.compile(r"\b(reboot|sync core|ping|uptime)\b", re.IGNORECASE),
            ],
            IntentType.STUDY_HELP: [
                re.compile(r"\b(study|revise|revision|explain|quiz|flashcards?|learn)\b", re.IGNORECASE),
                re.compile(r"\b(japanese|dbms|java|sql)\b", re.IGNORECASE),
            ],
            IntentType.MEMORY_QUERY: [
                re.compile(r"\b(remember|recall|memory|what do you know about me|preferences?)\b", re.IGNORECASE),
            ],
            IntentType.SEARCH: [
                re.compile(r"\b(search|find|google|look up|web search|browse)\b", re.IGNORECASE),
            ],
            IntentType.GENERAL_CHAT: [
                re.compile(r"\b(hello|hi|hey|good morning|who are you|jarvis|what can you do)\b", re.IGNORECASE),
            ],
        }

    def classify(self, text: str) -> IntentResult:
        """
        Classifies incoming user text into an IntentResult.
        """
        cleaned_text = text.strip()
        entities: Dict[str, Any] = {}

        # Check rules in prioritized order
        for intent_type, patterns in self.rules.items():
            for pattern in patterns:
                match = pattern.search(cleaned_text)
                if match:
                    # Extract rudimentary entities
                    if "java" in cleaned_text.lower():
                        entities["language"] = "Java"
                    if "dbms" in cleaned_text.lower():
                        entities["topic"] = "DBMS"
                    if "n5" in cleaned_text.lower():
                        entities["topic"] = "Japanese N5"

                    return IntentResult(
                        intent=intent_type.value,
                        confidence=0.95,
                        entities=entities,
                        raw_input=cleaned_text,
                    )

        # Fallback to general chat or unknown
        if len(cleaned_text.split()) > 0:
            return IntentResult(
                intent=IntentType.GENERAL_CHAT.value,
                confidence=0.60,
                entities=entities,
                raw_input=cleaned_text,
            )

        return IntentResult(
            intent=IntentType.UNKNOWN.value,
            confidence=0.0,
            entities={},
            raw_input=cleaned_text,
        )


intent_classifier = IntentClassifier()
