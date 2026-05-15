"""Research agent — web search and content extraction."""

from run_agent.agents.base import BaseAgent
from run_agent.config.constants import AGENT_RESEARCH
from run_agent.prompts.research import RESEARCH_SYSTEM_PROMPT
from run_agent.tools import build_research_tools


class ResearchAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name=AGENT_RESEARCH, tool_registry=build_research_tools())

    def get_system_prompt(self) -> str:
        return RESEARCH_SYSTEM_PROMPT
