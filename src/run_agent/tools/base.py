"""Base tool protocol."""

import copy
from abc import ABC, abstractmethod
from typing import Any

# Display-only argument injected into every tool's schema. The model fills it
# in when it calls a tool so the UI can show what is being done without
# scraping the real arguments. Stripped before execution by the registry.
TASK_ARG_PROPERTIES: dict[str, Any] = {
    "task_summary": {
        "type": "string",
        "description": (
            "A concise one-line summary of what this specific call does, e.g. "
            "'Search for the best pizza in NYC'. Shown in the UI as the "
            "tool-call heading."
        ),
    },
}
TASK_ARG_NAMES: tuple[str, ...] = tuple(TASK_ARG_PROPERTIES)


class BaseTool(ABC):
    """Abstract base class for all agent tools.

    `name` and `description` are set as class attributes by subclasses.
    """

    name: str
    description: str

    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """Return the JSON Schema for this tool's parameters."""
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool and return a string result.

        Tools that produce files receive run context via the `_context`
        keyword argument (a dict with run_id, user_id, conversation_id).
        """
        ...

    def to_openai_tool(self) -> dict[str, Any]:
        """Convert to OpenAI function-calling format.

        Every tool's schema gains the display-only `task_summary` argument
        (see `TASK_ARG_PROPERTIES`) so the model states what it is doing on
        each call. It is stripped before execution.
        """
        schema = copy.deepcopy(self.parameters_schema())
        properties = schema.setdefault("properties", {})
        properties.update(TASK_ARG_PROPERTIES)
        required = schema.setdefault("required", [])
        for name in TASK_ARG_NAMES:
            if name not in required:
                required.append(name)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }
