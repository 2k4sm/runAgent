"""Supervisor agent — orchestrates worker agents via an agents-as-tools pattern.

The supervisor exposes each worker agent as a callable tool. When the model
calls one, the supervisor runs that worker, streams its events to the client,
and feeds the worker's output back into its own conversation as the tool
result — so it keeps control and can chain agents (research -> document),
collect generated file links, and write a final synthesized answer.
"""

import json
from collections.abc import AsyncGenerator
from typing import Any

from run_agent.agents.base import BaseAgent
from run_agent.agents.document_agent import DocumentAgent
from run_agent.agents.research_agent import ResearchAgent
from run_agent.config.constants import AGENT_SUPERVISOR
from run_agent.config.logging import get_logger
from run_agent.prompts.supervisor import SUPERVISOR_SYSTEM_PROMPT
from run_agent.schemas.sse import SSEEvent

logger = get_logger(__name__)

# One tool per worker agent. The model calls these like any other tool; the
# supervisor intercepts them in `_handle_tool` and runs the matching worker.
_AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "research_agent",
            "description": (
                "Delegate to the Research Agent to find accurate, current "
                "information via web search. Returns structured findings with "
                "sources. Use for facts, current events, statistics, or "
                "anything you are not certain about."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": (
                            "A specific, self-contained research request. State "
                            "exactly what to find and the shape of the output "
                            "you need back."
                        ),
                    },
                    "context": {
                        "type": "string",
                        "description": (
                            "Relevant background from the conversation (prior "
                            "findings, user constraints, attached-file notes) "
                            "that helps the researcher. Pass an empty string if "
                            "none."
                        ),
                    },
                },
                "required": ["task", "context"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "document_agent",
            "description": (
                "Delegate to the Document Agent to create a file (PDF, DOCX, "
                "XLSX, PPTX, CSV, Markdown, or TXT). Returns the filename and a "
                "download URL. The document agent does NOT do research — give "
                "it all the content it needs in `source_material`."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": (
                            "What document to create: format, structure, "
                            "sections, audience, and tone."
                        ),
                    },
                    "source_material": {
                        "type": "string",
                        "description": (
                            "The complete content to put in the document — e.g. "
                            "the research findings you received earlier. The "
                            "document agent only sees what you pass here."
                        ),
                    },
                },
                "required": ["task", "source_material"],
            },
        },
    },
]

_AGENT_TOOL_NAMES = {"research_agent": "research", "document_agent": "document"}


class SupervisorAgent(BaseAgent):
    """Orchestrates worker agents and synthesizes a final answer."""

    def __init__(self) -> None:
        super().__init__(name=AGENT_SUPERVISOR)
        self.workers: dict[str, BaseAgent] = {
            "research": ResearchAgent(),
            "document": DocumentAgent(),
        }
        # The original conversation (history + current message with attachments);
        # captured in `run()` and forwarded to workers so they inherit context.
        self._conversation_messages: list[dict[str, Any]] = []

    def get_system_prompt(self) -> str:
        return SUPERVISOR_SYSTEM_PROMPT

    def get_tools(self) -> list[dict[str, Any]]:
        return _AGENT_TOOLS

    async def run(
        self,
        messages: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Capture the conversation, then run the standard ReAct loop."""
        self._conversation_messages = messages
        async for event in super().run(messages, context):
            yield event

    async def _handle_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        tool_call_id: str,
        context: dict[str, Any] | None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Run a worker agent when an agent-tool is called; else delegate."""
        worker_name = _AGENT_TOOL_NAMES.get(tool_name)
        if worker_name is None:
            async for event in super()._handle_tool(
                tool_name, args, tool_call_id, context
            ):
                yield event
            return

        worker = self.workers.get(worker_name)
        if worker is None:
            yield SSEEvent(
                type="tool_result",
                agent=AGENT_SUPERVISOR,
                content=f"Error: unknown agent '{worker_name}'",
                metadata={"tool_name": tool_name},
            )
            return

        task = str(args.get("task") or "")
        extra = str(args.get("source_material") or args.get("context") or "")
        instruction = f"Task from supervisor: {task}"
        if extra.strip():
            label = (
                "Source material" if "source_material" in args else "Context"
            )
            instruction += f"\n\n{label}:\n{extra}"

        yield SSEEvent(
            type="handoff",
            agent=AGENT_SUPERVISOR,
            content=f"Delegating to {worker_name} agent",
            metadata={"target_agent": worker_name, "task": task},
        )

        worker_messages = [
            *self._conversation_messages,
            {"role": "system", "content": instruction},
        ]

        # Stream the worker's events, but swallow its terminal `done` (the
        # supervisor emits the run's single `done`). Accumulate its final text
        # and any files it generated.
        answer_chunks: list[str] = []
        files: list[dict[str, Any]] = []
        async for event in worker.run(worker_messages, context):
            if event.type == "done":
                continue
            if event.type == "chunk" and event.content:
                answer_chunks.append(event.content)
            if event.type == "tool_result" and event.content:
                _collect_file(event.content, files)
            yield event

        if files:
            bucket = (context or {}).setdefault("generated_files", [])
            bucket.extend(files)

        answer = "".join(answer_chunks).strip() or "(the agent produced no text)"
        if files:
            listed = "\n".join(
                f"- {f['file_name']}: {f['file_url']}" for f in files
            )
            answer += f"\n\nFiles generated:\n{listed}"

        yield SSEEvent(
            type="tool_result",
            agent=AGENT_SUPERVISOR,
            content=answer,
            metadata={"tool_name": tool_name, "worker": worker_name},
        )


def _collect_file(tool_result: str, files: list[dict[str, Any]]) -> None:
    """Pull a generated-file record out of a worker tool result, if present.

    The record mirrors the attachment shape the frontend uses for uploaded
    files, so generated files render with the same chip component.
    """
    try:
        data = json.loads(tool_result)
    except (ValueError, TypeError):
        return
    if isinstance(data, dict) and data.get("download_url"):
        files.append({
            "id": data.get("asset_id", ""),
            "file_name": data.get("filename", ""),
            "file_type": data.get("file_type", ""),
            "file_size": data.get("file_size", 0),
            "file_url": data["download_url"],
        })
