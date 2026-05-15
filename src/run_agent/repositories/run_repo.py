"""runs table queries."""

from run_agent.repositories.base import BaseRepository


class RunRepository(BaseRepository):
    table_name = "runs"
