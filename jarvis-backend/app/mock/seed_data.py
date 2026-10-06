import json
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.task import Task
from app.models.memory import Memory
from app.models.project import Project
from app.models.activity import Activity
from app.models.chat import Conversation, Message
from app.models.cms import CMSConfig

logger = logging.getLogger("jarvis.mock")


def seed_database(db: Session) -> None:
    """
    Seeds initial realistic data matching the Stitch frontend UI telemetry
    into PostgreSQL/database so that the system operates immediately without empty screens.
    """
    # 1. Seed User
    if db.query(User).count() == 0:
        commander = User(
            email="commander@jarvis.os",
            username="Commander",
            full_name="Chief Operator",
            role="commander",
            security_level="SEC_L4",
            is_active=True
        )
        db.add(commander)
        logger.info("Seeded primary Commander user.")

    # 2. Seed Tasks (Matching UI Bento Grid: 3 in flight)
    if db.query(Task).count() == 0:
        tasks = [
            Task(
                title="Prepare DBMS revision",
                description="Comprehensive database management systems flashcard & theory synthesis",
                status="AI WORKING",
                priority="HIGH",
                progress=72,
                eta="~14m",
                category="Study"
            ),
            Task(
                title="Analyze Java project",
                description="AST syntax tree error check across compilation units",
                status="WAITING FOR INPUT",
                priority="CRITICAL",
                progress=34,
                eta="Thread: PAUSED",
                category="Engineering"
            ),
            Task(
                title="Japanese N5 revision",
                description="Vocabulary and grammar matrix review",
                status="SCHEDULED",
                priority="MEDIUM",
                progress=58,
                eta="Queue: 18:00 UTC",
                category="Language"
            ),
        ]
        db.add_all(tasks)
        logger.info(f"Seeded {len(tasks)} active tasks.")

    # 3. Seed Projects
    if db.query(Project).count() == 0:
        projects = [
            Project(
                name="Java Core Engine",
                description="Enterprise backend services built on Spring Boot and JDK 21 LTS",
                status="ACTIVE",
                progress=68,
                repo_path="/workspace/java-core-engine",
                technologies="Java, Spring Boot 3.2, PostgreSQL, Gradle",
                file_count=24
            ),
            Project(
                name="DBMS Revision Matrix",
                description="Relational database query planner and normalization synthesizer",
                status="ACTIVE",
                progress=72,
                repo_path="/workspace/dbms-revision",
                technologies="SQL, PostgreSQL, Python",
                file_count=18
            ),
            Project(
                name="Japanese N5 Flashcards",
                description="Interactive spaced repetition flashcard pipeline",
                status="PAUSED",
                progress=58,
                repo_path="/workspace/nihongo-n5",
                technologies="HTML5, CSS3, JS",
                file_count=12
            )
        ]
        db.add_all(projects)
        logger.info(f"Seeded {len(projects)} projects.")

    # 4. Seed Memories (Matching UI: User prefers Java [Relevance 98.4%])
    if db.query(Memory).count() == 0:
        memories = [
            Memory(
                content="User prefers Java for backend systems and AST parsing",
                memory_type="PREFERENCE",
                importance=0.98,
                relevance_score=0.984,
                tags="java, preference, programming",
                metadata_json=json.dumps({"id": "#MEM-209-JVA", "source": "user_observation"})
            ),
            Memory(
                content="Operator routinely studies Japanese N5 language vocabulary at 18:00 UTC",
                memory_type="EPISODIC",
                importance=0.85,
                relevance_score=0.850,
                tags="japanese, study, schedule",
                metadata_json=json.dumps({"id": "#MEM-114-JPN", "frequency": "daily"})
            ),
            Memory(
                content="Current workspace directory defaults to /workspace/java-core-engine",
                memory_type="CODEBASE",
                importance=0.90,
                relevance_score=0.912,
                tags="workspace, directory, java",
                metadata_json=json.dumps({"id": "#MEM-042-DIR", "type": "environment"})
            )
        ]
        db.add_all(memories)
        logger.info(f"Seeded {len(memories)} memories.")

    # 5. Seed Activities (Matching UI Live Activity Feed)
    if db.query(Activity).count() == 0:
        now = datetime.utcnow()
        activities = [
            Activity(
                event_type="ANALYSIS_EVENT",
                title="Analysis Event",
                description="JARVIS analyzed Java project repository AST trees.",
                status="SUCCESS",
                timestamp=now - timedelta(minutes=15)
            ),
            Activity(
                event_type="EXECUTION_SUCCESS",
                title="Execution Success",
                description="Task completed: DBMS flashcard synthesis matrix.",
                status="SUCCESS",
                timestamp=now - timedelta(minutes=24)
            ),
            Activity(
                event_type="VECTOR_SYNC",
                title="Vector Sync",
                description="Memory updated: 14 new embeddings anchored to graph.",
                status="INFO",
                timestamp=now - timedelta(minutes=38)
            ),
            Activity(
                event_type="VOICE_AUDIO_IN",
                title="Voice Audio In",
                description="Voice command processed: Audio transcribed at 99.7% SNR.",
                status="INFO",
                timestamp=now - timedelta(minutes=55)
            )
        ]
        db.add_all(activities)
        logger.info(f"Seeded {len(activities)} recent activities.")

    # 6. Seed Conversations & Messages
    if db.query(Conversation).count() == 0:
        conv = Conversation(
            title="Java Project Analysis Session",
            context_token="#CTX-78440"
        )
        db.add(conv)
        db.flush()

        messages = [
            Message(
                conversation_id=conv.id,
                role="user",
                content="Open my Java project and check for errors.",
                intent="PROJECT_ANALYSIS"
            ),
            Message(
                conversation_id=conv.id,
                role="assistant",
                content="I found your Java project. I'm analyzing the project structure before checking for errors.",
                intent="PROJECT_ANALYSIS",
                tool_calls_json=json.dumps({"tool": "project_analyzer", "status": "completed"})
            )
        ]
        db.add_all(messages)
        logger.info("Seeded initial conversation and messages.")

    # 7. Seed CMS Configurations (For future Admin Panel / Dynamic CMS)
    if db.query(CMSConfig).count() == 0:
        cms_configs = [
            CMSConfig(
                key="system.quantum_state",
                value="COHERENT 99.4%",
                type="string",
                category="system_status",
                description="Quantum coherence state indicator on top HUD"
            ),
            CMSConfig(
                key="system.entropy",
                value="0.0028 Δ",
                type="string",
                category="system_status",
                description="System entropy reading on greeting banner"
            ),
            CMSConfig(
                key="dashboard.greeting",
                value="Good morning, Commander.",
                type="string",
                category="dashboard",
                description="Main dashboard greeting banner header"
            ),
            CMSConfig(
                key="dashboard.subgreeting",
                value="What can I help you accomplish? All autonomous computational subsystems stand synchronized.",
                type="string",
                category="dashboard",
                description="Dashboard greeting subtext"
            ),
            CMSConfig(
                key="dashboard.insight.title",
                value="Your Java practice has increased significantly this week.",
                type="string",
                category="dashboard",
                description="Cognitive ML insight title"
            ),
            CMSConfig(
                key="dashboard.insight.description",
                value="Autonomous heuristic tracking detected a 24% surge in codebase comprehension sessions. JARVIS suggests compiling a targeted concurrency revision module before tomorrow's scheduled sprint.",
                type="string",
                category="dashboard",
                description="Cognitive ML insight description"
            ),
            CMSConfig(
                key="dashboard.insight.trend",
                value="+24% activity trend",
                type="string",
                category="dashboard",
                description="Insight trend badge"
            ),
            CMSConfig(
                key="ai.personality.name",
                value="JARVIS",
                type="string",
                category="ai",
                description="Autonomous Agent Personality Identifier"
            ),
            CMSConfig(
                key="ai.personality.instruction",
                value="You are JARVIS, an autonomous multimodal AI agent. Maintain concise, highly capable, telemetry-conscious responses.",
                type="markdown",
                category="ai",
                description="System instruction for assistant responses"
            ),
            CMSConfig(
                key="quick_actions.list",
                value=json.dumps([
                    {"title": "Start Focus Session", "subtitle": "POMODORO 45M", "icon": "filter_center_focus"},
                    {"title": "Analyze File", "subtitle": "AST PARSE", "icon": "file_open"},
                    {"title": "Open Project", "subtitle": "JAVA / DBMS", "icon": "folder_managed"},
                    {"title": "Create Task", "subtitle": "NEW INTAKE", "icon": "add_task"},
                    {"title": "Ask JARVIS", "subtitle": "NATURAL QUERY", "icon": "smart_toy"},
                    {"title": "View Memory", "subtitle": "VECTOR GRAPH", "icon": "memory"}
                ]),
                type="json",
                category="quick_actions",
                description="Configurable Quick Action button definitions"
            )
        ]
        db.add_all(cms_configs)
        logger.info(f"Seeded {len(cms_configs)} CMS dynamic configurations.")

    db.commit()
    logger.info("Database seeding successfully completed.")
