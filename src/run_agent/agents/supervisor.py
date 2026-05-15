"""Supervisor agent — routes requests to worker agents."""

from collections.abc import AsyncGenerator
from typing import Any

from run_agent.agents.base import BaseAgent
from run_agent.agents.document_agent import DocumentAgent
from run_agent.agents.research_agent import ResearchAgent
from run_agent.config.constants import AGENT_SUPERVISOR
from run_agent.prompts.supervisor import SUPERVISOR_SYSTEM_PROMPT
from run_agent.schemas.sse import SSEEvent

_ROUTE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "route_to_agent",
        "description": "Route the user's request to a specialized agent.",
        "parameters": {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "enum": ["research", "document"],
                    "description": "Which agent to route to.",
                },
                "task": {
                    "type": "string",
                    "description": "Clear task description for the worker agent.",
                },
            },
            "required": ["agent", "task"],
        },
    },
}


class SupervisorAgent(BaseAgent):
    """Decides whether to answer directly or delegate to a worker agent."""

    def __init__(self) -> None:
        super().__init__(name=AGENT_SUPERVISOR)
        self.workers: dict[str, BaseAgent] = {
            "research": ResearchAgent(),
            "document": DocumentAgent(),
        }

    def get_system_prompt(self) -> str:
        return SUPERVISOR_SYSTEM_PROMPT

    def get_tools(self) -> list[dict[str, Any]]:
        return [_ROUTE_TOOL]

    async def run(
        self,
        messages: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Run the base loop; intercept route_to_agent and hand off to a worker."""
        async for event in super().run(messages, context):
            if event.type == "tool_call" and event.metadata:
                if event.metadata.get("tool_name") != "route_to_agent":
                    yield event
                    continue

                args = event.metadata.get("tool_args", {}) or {}
                agent_name = str(args.get("agent") or "")
                task = args.get("task", "")

                yield SSEEvent(
                    type="handoff",
                    agent=AGENT_SUPERVISOR,
                    content=f"Routing to {agent_name} agent",
                    metadata={"target_agent": agent_name, "task": task},
                )

                worker = self.workers.get(agent_name)
                if not worker:
                    yield SSEEvent(
                        type="error",
                        agent=AGENT_SUPERVISOR,
                        content=f"Unknown agent: {agent_name}",
                    )
                    return

                worker_messages = [
                    *messages,
                    {"role": "system", "content": f"Task from supervisor: {task}"},
                ]
                async for worker_event in worker.run(worker_messages, context):
                    yield worker_event
                return

            # thought events tied to the routing call are noise — drop them.
            if event.type == "thought":
                continue
            yield event
