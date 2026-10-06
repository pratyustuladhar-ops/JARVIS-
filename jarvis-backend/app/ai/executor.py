import time
import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.ai.tools import agent_tool_registry
from app.ai.planner import PlanStep

logger = logging.getLogger("jarvis.ai.executor")


class ExecutionResult:
    def __init__(
        self,
        tool_name: str,
        status: str,
        output: Any = None,
        duration_ms: float = 0.0,
        error: str = None
    ):
        self.tool_name = tool_name
        self.status = status
        self.output = output
        self.duration_ms = duration_ms
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status,
            "output": self.output,
            "duration_ms": self.duration_ms,
            "error": self.error
        }


class ToolExecutor:
    """
    Safe Tool Execution Engine.
    Executes only verified tools within registered schemas and sandbox bounds.
    """

    def execute_step(self, db: Session, step: PlanStep) -> ExecutionResult:
        tool_name = step.tool_name
        if not tool_name:
            return ExecutionResult(
                tool_name="none",
                status="SUCCESS",
                output=None,
                duration_ms=0.0
            )

        tool = agent_tool_registry.get_tool(tool_name)
        if not tool:
            return ExecutionResult(
                tool_name=tool_name,
                status="FAILED",
                error=f"Tool '{tool_name}' not permitted in registry."
            )

        start = time.time()
        try:
            logger.info(f"[TOOL] Executing '{tool_name}' with params: {step.parameters}")
            output = tool.execute(db, step.parameters)
            duration = round((time.time() - start) * 1000, 2)
            step.status = "COMPLETED"
            return ExecutionResult(
                tool_name=tool_name,
                status="SUCCESS",
                output=output,
                duration_ms=duration
            )
        except Exception as e:
            duration = round((time.time() - start) * 1000, 2)
            step.status = "FAILED"
            logger.error(f"[TOOL] Failed executing '{tool_name}': {e}")
            return ExecutionResult(
                tool_name=tool_name,
                status="FAILED",
                duration_ms=duration,
                error=str(e)
            )


tool_executor = ToolExecutor()
