import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from app.schemas.agent import ToolExecutionResult


class BaseTool(ABC):
    """Abstract base class for all safe JARVIS agent tools."""
    name: str
    description: str
    input_schema: Dict[str, Any]

    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> Any:
        """Executes the tool with given parameters within safe sandbox constraints."""
        pass


class ToolRegistry:
    """Safe tool discovery, inspection, and execution registry."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for name, tool in self._tools.items()
        }

    def execute_tool(self, name: str, params: Dict[str, Any]) -> ToolExecutionResult:
        tool = self.get_tool(name)
        if not tool:
            return ToolExecutionResult(
                tool_name=name,
                status="FAILED",
                output=None,
                error=f"Tool '{name}' not found in registry."
            )

        start_time = time.time()
        try:
            output = tool.execute(params)
            duration = (time.time() - start_time) * 1000
            return ToolExecutionResult(
                tool_name=name,
                status="SUCCESS",
                output=output,
                duration_ms=round(duration, 2)
            )
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ToolExecutionResult(
                tool_name=name,
                status="FAILED",
                output=None,
                duration_ms=round(duration, 2),
                error=str(e)
            )


tool_registry = ToolRegistry()
