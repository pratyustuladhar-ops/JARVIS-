import re
import logging
from typing import List, Optional

logger = logging.getLogger("jarvis.ai.decomposer")

KNOWN_APPS = {
    "chrome", "google chrome", "edge", "microsoft edge",
    "vscode", "vs code", "visual studio code", "code",
    "notepad", "calculator", "calc", "spotify",
    "explorer", "file explorer", "terminal", "windows terminal"
}

KNOWN_URL_TARGETS = {
    "youtube", "youtube.com", "google", "google.com",
    "github", "github.com", "reddit", "reddit.com",
    "x.com", "twitter.com"
}

KNOWN_FOLDERS = {
    "downloads", "documents", "desktop", "my project", "my project folder", "project folder"
}


class MultiStepDecomposer:
    """
    Intelligent Command Decomposer for JARVIS Agent:
    Decomposes natural language multi-step requests into ordered executable steps
    without naive string splitting.
    """

    EXPLICIT_CONNECTORS_REGEX = re.compile(
        r"(?:,\s*)?(?:\band\s+then\b|\bthen\b|\bafter\s+that\b|\bfollowed\s+by\b|\bonce\s+that\s+is\s+done\b|\bnext\b)\s+",
        re.I
    )

    @staticmethod
    def _is_known_app_or_url(text: str) -> bool:
        norm = text.strip().lower().rstrip(".?!,:;")
        if norm in KNOWN_APPS or norm in KNOWN_URL_TARGETS:
            return True
        if norm.startswith("http://") or norm.startswith("https://") or norm.startswith("www."):
            return True
        return False

    @staticmethod
    def _is_executable_clause(clause: str) -> bool:
        """Determines if a clause looks like a distinct executable command."""
        c = clause.strip().lower()
        if not c:
            return False

        # Starts with recognized action verbs
        action_prefixes = [
            "open ", "launch ", "start ", "run ", "navigate to ", "browse to ", "go to ",
            "create ", "add ", "schedule ", "new ", "remind me to ",
            "list ", "show ", "display ", "view ", "what tasks", "what projects",
            "update ", "mark ", "set ", "change ",
            "delete ", "remove ", "cancel ", "discard ",
            "remember ", "save memory", "recall ", "what do you remember",
            "system status", "run diagnostics", "what time is it", "tell me the time", "current time",
            "powershell ", "cmd ", "bash ", "shell ", "execute "
        ]
        if any(c.startswith(p) for p in action_prefixes):
            return True

        if c in ["system status", "diagnostics", "check health", "current time", "what time is it"]:
            return True

        # Allowlisted single targets
        if MultiStepDecomposer._is_known_app_or_url(c):
            return True

        return False

    def decompose(self, text: str) -> List[str]:
        raw = text.strip()
        if not raw:
            return []

        # Remove polite / conversational prefix
        cleaned = re.sub(
            r"^(?:(?:can|could|would)\s+you\s+(?:please\s+)?|(?:please\s+)|(?:jarvis,?\s*)|(?:hey\s+jarvis,?\s*)|(?:hi\s+jarvis,?\s*)|(?:ok\s+jarvis,?\s*))",
            "",
            raw,
            flags=re.I
        ).strip()
        # Keep unified browser search commands intact (e.g. "Open YouTube and search for...")
        if re.search(r"\b(?:and\s+search|then\s+search)\b", cleaned, re.I) and any(
            site in cleaned.lower() for site in ["youtube", "google", "wikipedia", "github"]
        ):
            return [cleaned]

        # Pattern 0: "first <cmd1> then <cmd2>"
        first_then_match = re.match(
            r"^first\s+(.+?)\s+(?:,\s*)?(?:then|after\s+that|next|followed\s+by)\s+(.+)$",
            cleaned,
            re.I
        )
        if first_then_match:
            c1 = first_then_match.group(1).strip()
            c2 = first_then_match.group(2).strip()
            # Recursively decompose c2 in case there are subsequent steps
            sub_c2 = self.decompose(c2)
            steps = [c1] + (sub_c2 if sub_c2 else [c2])
            return [s for s in steps if s]

        # Pattern 1: Explicit connectors ("then", "and then", "after that", "followed by", "next", "once that is done")
        if self.EXPLICIT_CONNECTORS_REGEX.search(cleaned):
            parts = [p.strip() for p in self.EXPLICIT_CONNECTORS_REGEX.split(cleaned) if p.strip()]
            if len(parts) >= 2:
                # If a part is just an app/url name without verb, expand with "open" if previous was open
                expanded = []
                for idx, p in enumerate(parts):
                    if idx > 0 and self._is_known_app_or_url(p) and not p.lower().startswith(("open", "launch", "start")):
                        expanded.append(f"open {p}")
                    else:
                        expanded.append(p)
                return expanded

        # Pattern 2: Semicolon separated commands ("cmd1; cmd2")
        if ";" in cleaned:
            semi_parts = [p.strip() for p in cleaned.split(";") if p.strip()]
            if len(semi_parts) >= 2 and all(self._is_executable_clause(p) for p in semi_parts):
                return semi_parts

        # Pattern 3: Shared-verb application/URL conjunction
        # e.g. "open Chrome and YouTube", "open Chrome and Edge", "open Notepad and Calculator"
        # e.g. "open Chrome, Edge and Spotify"
        verb_match = re.match(r"^(open|launch|start|run)\s+(.+)$", cleaned, re.I)
        if verb_match:
            action_verb = verb_match.group(1).strip()
            targets_str = verb_match.group(2).strip()

            # Split by comma or "and"
            # Replace ", and " or " and " with a standard delimiter
            norm_targets = re.sub(r",?\s+\band\s+", ",", targets_str, flags=re.I)
            candidate_targets = [t.strip() for t in norm_targets.split(",") if t.strip()]

            if len(candidate_targets) >= 2:
                # Check if all candidate targets are apps, urls, or folders
                all_valid_targets = True
                for t in candidate_targets:
                    t_clean = re.sub(r"^(?:the\s+application\s+|app\s+|the\s+)?", "", t, flags=re.I).strip()
                    # Also strip "open" if user repeated verb like "open Chrome, open Edge"
                    t_clean = re.sub(r"^(?:open|launch|start)\s+", "", t_clean, flags=re.I).strip()
                    if not (self._is_known_app_or_url(t_clean) or t_clean.lower() in KNOWN_FOLDERS):
                        all_valid_targets = False
                        break

                if all_valid_targets:
                    result = []
                    for t in candidate_targets:
                        t_clean = re.sub(r"^(?:open|launch|start)\s+", "", t, flags=re.I).strip()
                        result.append(f"{action_verb} {t_clean}")
                    return result

        # Pattern 4: Conjunction "and" between distinct executable clauses
        # e.g. "create a task to study DBMS and open VS Code"
        # e.g. "open Chrome and open YouTube"
        # e.g. "open VS Code then open my project"
        and_parts = re.split(r",?\s+\band\s+", cleaned, flags=re.I)
        if len(and_parts) >= 2:
            # Check if each part looks like a full command clause
            # (e.g. part 0 is "create a task...", part 1 is "open vs code")
            if all(self._is_executable_clause(p) for p in and_parts):
                expanded = []
                for p in and_parts:
                    p_clean = p.strip()
                    if self._is_known_app_or_url(p_clean) and not p_clean.lower().startswith(("open", "launch", "start")):
                        expanded.append(f"open {p_clean}")
                    else:
                        expanded.append(p_clean)
                return expanded

        # Fallback: Single command
        return [cleaned]

    def is_multi_step(self, text: str) -> bool:
        steps = self.decompose(text)
        return len(steps) > 1


multi_step_decomposer = MultiStepDecomposer()
