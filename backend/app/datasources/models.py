"""
SQLAlchemy ORM models.

Tables
------
* **Task**    – analysis task metadata and status.
* **TaskLog** – SSE progress messages (for replay / debugging).
* **Section** – document sections selected during analysis.
* **Clause**  – structured clauses extracted from the document.
"""

from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime

from app.datasources.database import Base


# ===========================================================================
# Task
# ===========================================================================

class Task(Base):
    """Analysis task – tracks file metadata, status, and aggregate results."""

    __tablename__ = "tasks"

    # Primary key
    task_id = Column(String(36), primary_key=True, comment="Task UUID")

    # File information
    file_name = Column(String(255), nullable=False, comment="Original file name")
    file_size = Column(Integer, comment="File size in bytes")
    file_hash = Column(String(64), index=True, comment="SHA-256 hash for idempotency checks")
    pdf_path = Column(String(500), comment="Local PDF storage path")
    minio_url = Column(String(500), comment="MinIO object URL")
    use_mock = Column(Integer, default=0, comment="Use mock data (0=no, 1=yes)")

    # Status
    status = Column(String(20), nullable=False, default="pending", comment="Task status")
    progress = Column(Float, default=0.0, comment="Progress percentage (0-100)")
    current_message = Column(String(500), comment="Current status message")
    error_message = Column(Text, comment="Error detail (on failure)")

    # Statistics
    total_sections = Column(Integer, default=0, comment="Number of selected sections")
    total_clauses = Column(Integer, default=0, comment="Total extracted clauses")
    total_requirements = Column(Integer, default=0, comment="DEPRECATED – alias for total_clauses (kept for backward compat)")

    # Analysis results (JSON blobs)
    document_tree_json = Column(Text, comment="PageIndex document tree (JSON)")
    quality_report_json = Column(Text, comment="Quality report (JSON): parsing accuracy, evidence rate, etc.")

    # Timestamps
    created_at = Column(DateTime, default=datetime.now, comment="Task creation time")
    started_at = Column(DateTime, comment="Execution start time")
    completed_at = Column(DateTime, comment="Completion time")
    elapsed_seconds = Column(Float, default=0.0, comment="Wall-clock duration in seconds")

    # Relationships
    logs = relationship("TaskLog", back_populates="task", cascade="all, delete-orphan")
    sections = relationship("Section", back_populates="task", cascade="all, delete-orphan")
    clauses = relationship("Clause", back_populates="task", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("idx_task_status", "status"),
        Index("idx_task_created_at", "created_at"),
        Index("idx_task_file_hash", "file_hash"),
    )

    def __repr__(self):
        return f"<Task {self.task_id} {self.file_name} [{self.status}]>"


# ===========================================================================
# TaskLog
# ===========================================================================

class TaskLog(Base):
    """SSE message log – stores every progress/status message for replay."""

    __tablename__ = "task_logs"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    task_id = Column(String(36), ForeignKey("tasks.task_id"), nullable=False)

    # Log payload
    log_level = Column(String(10), default="info", comment="Level: info/debug/warning/error")
    progress = Column(Float, comment="Progress percentage at log time")
    message = Column(Text, nullable=False, comment="Log message")

    # Timestamp
    created_at = Column(DateTime, default=datetime.now, comment="Log timestamp")

    # Relationship
    task = relationship("Task", back_populates="logs")

    # Indexes
    __table_args__ = (
        Index("idx_log_task_id", "task_id"),
        Index("idx_log_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<TaskLog {self.task_id} [{self.log_level}] {self.message[:50]}>"


# ===========================================================================
# Section
# ===========================================================================

class Section(Base):
    """Document section selected for clause extraction."""

    __tablename__ = "sections"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    task_id = Column(String(36), ForeignKey("tasks.task_id"), nullable=False)

    # Section metadata
    section_id = Column(String(50), nullable=False, comment="Section identifier (e.g. '3.1.2')")
    title = Column(String(500), nullable=False, comment="Section title")
    reason = Column(Text, comment="Selection rationale")
    priority = Column(Integer, comment="Processing priority")
    start_page = Column(Integer, comment="Start page (1-based)")
    end_page = Column(Integer, comment="End page (1-based)")
    start_index = Column(Integer, comment="Start index in content_list")

    # Positional data (JSON-encoded bbox list)
    positions_json = Column(Text, comment="Bbox list (JSON): [[page, x1, y1, x2, y2], ...]")

    # Timestamp
    created_at = Column(DateTime, default=datetime.now, comment="Record creation time")

    # Relationship
    task = relationship("Task", back_populates="sections")

    # Indexes
    __table_args__ = (
        Index("idx_section_task_id", "task_id"),
        Index("idx_section_title", "title"),
    )

    def __repr__(self):
        return f"<Section {self.section_id} {self.title}>"


# ===========================================================================
# Clause
# ===========================================================================

class Clause(Base):
    """
    Structured clause extracted from a document.

    Contains multi-dimensional fields (type, actor, action, object,
    condition, deadline, metric) plus visual content and positional data.
    """

    __tablename__ = "clauses"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    task_id = Column(String(36), ForeignKey("tasks.task_id"), nullable=False)

    # Clause identity
    matrix_id = Column(String(50), nullable=False, comment="Unique clause ID (e.g. '3.1.2-CLS-001')")
    section_id = Column(String(50), comment="Parent section identifier")
    section_title = Column(String(500), comment="Parent section title")
    page_number = Column(Integer, comment="Page number (1-based)")

    # Structured clause fields
    clause_type = Column(String(20), nullable=False, comment="Type: obligation/requirement/prohibition/deliverable/deadline/penalty/definition")
    actor = Column(String(100), comment="Responsible party: supplier/buyer/system/organization/role")
    action = Column(String(100), comment="Action verb: submit/provide/ensure/record/comply/…")
    object = Column(String(200), comment="Target object: document/feature/KPI/material/…")
    condition = Column(Text, comment="Trigger condition (if/when/unless …)")
    deadline = Column(String(200), comment="Time constraint: date, relative period, or recurrence")
    metric = Column(String(200), comment="Quantitative metric: value, range, or comparison")

    # Original text
    original_text = Column(Text, nullable=False, comment="Verbatim clause text")

    # Visual-content fields
    image_caption = Column(Text, comment="Image description (from vision model)")
    table_caption = Column(Text, comment="Table description (structured table data)")

    # Positional data (JSON-encoded bbox list)
    positions_json = Column(Text, comment="Bbox list (JSON): [[page, x1, y1, x2, y2], …] for PDF highlighting")

    # Timestamp
    created_at = Column(DateTime, default=datetime.now, comment="Record creation time")

    # Relationship
    task = relationship("Task", back_populates="clauses")

    # Indexes
    __table_args__ = (
        Index("idx_clause_task_id", "task_id"),
        Index("idx_clause_matrix_id", "matrix_id"),
        Index("idx_clause_section_id", "section_id"),
        Index("idx_clause_type", "clause_type"),
    )

    def __repr__(self):
        return f"<Clause {self.matrix_id} [{self.clause_type}] {self.original_text[:30]}>"

