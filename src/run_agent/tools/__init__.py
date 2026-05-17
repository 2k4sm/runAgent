"""Tool registries for the worker agents."""

from run_agent.tools.documents.create_csv import CreateCsvTool
from run_agent.tools.documents.create_docx import CreateDocxTool
from run_agent.tools.documents.create_md import CreateMdTool
from run_agent.tools.documents.create_pdf import CreatePdfTool
from run_agent.tools.documents.create_pptx import CreatePptxTool
from run_agent.tools.documents.create_txt import CreateTxtTool
from run_agent.tools.documents.create_xlsx import CreateXlsxTool
from run_agent.tools.documents.edit_document import EditDocumentTool
from run_agent.tools.documents.list_documents import ListDocumentsTool
from run_agent.tools.documents.read_document import ReadDocumentTool
from run_agent.tools.registry import ToolRegistry
from run_agent.tools.search.tavily_search import TavilySearchTool
from run_agent.tools.search.web_fetch import WebFetchTool


def build_research_tools() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(TavilySearchTool())
    registry.register(WebFetchTool())
    return registry


def build_document_tools() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(CreateDocxTool())
    registry.register(CreatePdfTool())
    registry.register(CreateXlsxTool())
    registry.register(CreatePptxTool())
    registry.register(CreateCsvTool())
    registry.register(CreateMdTool())
    registry.register(CreateTxtTool())
    registry.register(ListDocumentsTool())
    registry.register(ReadDocumentTool())
    registry.register(EditDocumentTool())
    return registry
