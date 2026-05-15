"""App-wide constants."""

# Run / message status & roles
RUN_PENDING = "pending"
RUN_RUNNING = "running"
RUN_COMPLETED = "completed"
RUN_FAILED = "failed"

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_SYSTEM = "system"
ROLE_TOOL = "tool"

# Asset sources
SOURCE_UPLOAD = "upload"
SOURCE_GENERATED = "generated"

# Agent names
AGENT_SUPERVISOR = "supervisor"
AGENT_RESEARCH = "research"
AGENT_DOCUMENT = "document"

# MIME types for generated documents
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
MIME_PDF = "application/pdf"
MIME_CSV = "text/csv"
MIME_MD = "text/markdown"
MIME_TXT = "text/plain"
