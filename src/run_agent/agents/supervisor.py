"""Supervisor agent — orchestrates worker agents via an agents-as-tools pattern.

The supervisor exposes each worker agent as a callable tool. When the model
calls one, the supervisor runs that worker, streams its events to the client,
and feeds the worker's output back into its own conversation as the tool
result — so it keeps control and can chain agents (research -> document),
collect generated file links, and write a final synthesized answer.

When the user has connected MCP servers, the supervisor also offers an
`mcp_agent` tool that spins up a dynamically-built agent loaded with only the
tools of the server(s) relevant to the request.
"""

import json
from collections.abc import AsyncGenerator
from typing import Any

from run_agent.agents.base import BaseAgent
from run_agent.agents.document_agent import DocumentAgent
from run_agent.agents.mcp_agent import MCPAgent, open_mcp_tools
from run_agent.agents.research_agent import ResearchAgent
from run_agent.config.constants import AGENT_MCP, AGENT_SUPERVISOR
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

# Offered only when the user has connected MCP servers.
_MCP_AGENT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "mcp_agent",
        "description": (
            "Delegate to a dynamically-built MCP agent that uses tools from the "
            "user's connected MCP servers. Use this when the request needs an "
            "external integration available via a connected MCP server (see the "
            "'Connected MCP servers' list in your instructions)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "A specific, self-contained task for the MCP agent.",
                },
                "server_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "The id(s) of the connected MCP server(s) whose tools "
                        "are needed for this task."
                    ),
                },
            },
            "required": ["task", "server_ids"],
        },
    },
}

_AGENT_TOOL_NAMES = {"research_agent": "research", "document_agent": "document"}
_MCP_TOOL_NAME = "mcp_agent"


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
        # Catalog of the user's connected MCP servers, set from `context`.
        self._mcp_catalog: list[dict[str, Any]] = []

    def get_system_prompt(self) -> str:
        if not self._mcp_catalog:
            return SUPERVISOR_SYSTEM_PROMPT
        lines = [
            "## Connected MCP servers",
            "",
            "The user has connected the MCP servers below. When a request needs "
            "one of these integrations, call `mcp_agent` with the relevant "
            "server id(s):",
            "",
        ]
        for server in self._mcp_catalog:
            tools = ", ".join(
                t.get("name", "") for t in (server.get("tools") or [])
            )
            desc = server.get("description") or ""
            lines.append(
                f"- id={server['id']} | {server['name']}"
                + (f" — {desc}" if desc else "")
                + (f" | tools: {tools}" if tools else "")
            )
        return f"{SUPERVISOR_SYSTEM_PROMPT}\n\n" + "\n".join(lines)

    def get_tools(self) -> list[dict[str, Any]]:
        if self._mcp_catalog:
            return [*_AGENT_TOOLS, _MCP_AGENT_TOOL]
        return _AGENT_TOOLS

    async def run(
        self,
        messages: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Capture the conversation + MCP catalog, then run the ReAct loop."""
        self._conversation_messages = messages
        self._mcp_catalog = (context or {}).get("mcp_servers") or []
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
        if tool_name == _MCP_TOOL_NAME:
            async for event in self._handle_mcp_agent(tool_name, args, context):
                yield event
            return

        worker_name = _AGENT_TOOL_NAMES.get(tool_name)
        if worker_name is None:
            async for event in super()._handle_tool(
                tool_name, args, tool_call_id, context
            ):
                yield event
            return

        worker = self.workers[worker_name]
        task = str(args.get("task") or "")
        extra = str(args.get("source_material") or args.get("context") or "")
        label = "Source material" if "source_material" in args else "Context"
        instruction = f"Task from supervisor: {task}"
        if extra.strip():
            instruction += f"\n\n{label}:\n{extra}"

        yield SSEEvent(
            type="handoff",
            agent=AGENT_SUPERVISOR,
            content=f"Delegating to {worker_name} agent",
            metadata={"target_agent": worker_name, "task": task},
        )
        async for event in self._relay_worker(
            worker, worker_name, instruction, tool_name, context
        ):
            yield event

    async def _handle_mcp_agent(
        self,
        tool_name: str,
        args: dict[str, Any],
        context: dict[str, Any] | None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Build an MCP agent for the requested servers and run it."""
        task = str(args.get("task") or "")
        server_ids = [str(s) for s in (args.get("server_ids") or [])]
        user_id = str((context or {}).get("user_id") or "")

        yield SSEEvent(
            type="handoff",
            agent=AGENT_SUPERVISOR,
            content="Delegating to MCP agent",
            metadata={"target_agent": AGENT_MCP, "task": task},
        )

        if not server_ids:
            yield _error_result(tool_name, "No MCP server ids were provided.")
            return

        async with open_mcp_tools(server_ids, user_id) as (registry, summaries, errors):
            if not registry.get_schemas():
                detail = "; ".join(errors) or "no tools were available"
                yield _error_result(
                    tool_name, f"Could not load any MCP tools: {detail}"
                )
                return
            instruction = f"Task from supervisor: {task}"
            agent = MCPAgent(registry, summaries)
            async for event in self._relay_worker(
                agent, AGENT_MCP, instruction, tool_name, context
            ):
                yield event

    async def _relay_worker(
        self,
        worker: BaseAgent,
        worker_label: str,
        instruction: str,
        tool_name: str,
        context: dict[str, Any] | None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Run a worker, stream its events, and emit its result as a tool result.

        The worker's terminal `done` is swallowed (the supervisor emits the
        run's single `done`); its final text and any generated files become the
        tool result the supervisor's loop sees.
        """
        worker_messages = [
            *self._conversation_messages,
            {"role": "system", "content": instruction},
        ]
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
            metadata={"tool_name": tool_name, "worker": worker_label},
        )


def _error_result(tool_name: str, message: str) -> SSEEvent:
    return SSEEvent(
        type="tool_result",
        agent=AGENT_SUPERVISOR,
        content=f"Error: {message}",
        metadata={"tool_name": tool_name},
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
