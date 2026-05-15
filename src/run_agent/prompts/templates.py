"""Shared prompt fragments."""

REACT_FRAMEWORK = """## ReAct Framework

For each step: think about what you need, take an action with a tool, observe
the result, and repeat until you can give a complete final answer.
- **Thought**: What do I need? What is missing?
- **Action**: Call the appropriate tool.
- **Observation**: Analyze the result. Is it enough?

When you have everything you need, respond directly without calling a tool."""
