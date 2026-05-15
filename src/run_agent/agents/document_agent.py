"""Document agent — file creation."""

from run_agent.agents.base import BaseAgent
from run_agent.config.constants import AGENT_DOCUMENT
from run_agent.prompts.document import DOCUMENT_SYSTEM_PROMPT
from run_agent.tools import build_document_tools


class DocumentAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name=AGENT_DOCUMENT, tool_registry=build_document_tools())

    def get_system_prompt(self) -> str:
        return DOCUMENT_SYSTEM_PROMPT
