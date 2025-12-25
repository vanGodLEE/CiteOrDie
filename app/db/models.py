"""
数据库ORM模型

表结构设计：
1. Task - 任务主表
2. TaskLog - 任务日志表（SSE消息）
3. Section - 选中的章节表
4. Requirement - 需求矩阵表
"""

from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.database import Base


class Task(Base):
    """
    任务主表
    
    记录每次分析任务的元数据和状态
    """
    __tablename__ = "tasks"
    
    # 主键
    task_id = Column(String(36), primary_key=True, comment="任务UUID")
    
    # 文件信息
    file_name = Column(String(255), nullable=False, comment="原始文件名")
    file_size = Column(Integer, comment="文件大小（字节）")
    pdf_path = Column(String(500), comment="PDF存储路径")
    minio_url = Column(String(500), comment="MinIO存储URL")
    use_mock = Column(Integer, default=0, comment="是否使用Mock数据 0-否 1-是")
    
    # 任务状态
    status = Column(String(20), nullable=False, default="pending", comment="任务状态")
    progress = Column(Float, default=0.0, comment="进度百分比 0-100")
    current_message = Column(String(500), comment="当前状态消息")
    error_message = Column(Text, comment="错误信息（如果失败）")
    
    # 统计信息
    total_sections = Column(Integer, default=0, comment="筛选出的章节数")
    total_requirements = Column(Integer, default=0, comment="提取的需求总数")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment="任务创建时间")
    started_at = Column(DateTime, comment="开始执行时间")
    completed_at = Column(DateTime, comment="完成时间")
    
    # 关联关系
    logs = relationship("TaskLog", back_populates="task", cascade="all, delete-orphan")
    sections = relationship("Section", back_populates="task", cascade="all, delete-orphan")
    requirements = relationship("Requirement", back_populates="task", cascade="all, delete-orphan")
    
    # 索引
    __table_args__ = (
        Index("idx_task_status", "status"),
        Index("idx_task_created_at", "created_at"),
    )
    
    def __repr__(self):
        return f"<Task {self.task_id} {self.file_name} [{self.status}]>"


class TaskLog(Base):
    """
    任务日志表
    
    记录SSE推送的所有消息，用于复盘和错误排查
    """
    __tablename__ = "task_logs"
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 外键
    task_id = Column(String(36), ForeignKey("tasks.task_id"), nullable=False)
    
    # 日志内容
    log_level = Column(String(10), default="info", comment="日志级别 info/debug/warning/error")
    progress = Column(Float, comment="当时的进度百分比")
    message = Column(Text, nullable=False, comment="日志消息")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment="日志时间")
    
    # 关联关系
    task = relationship("Task", back_populates="logs")
    
    # 索引
    __table_args__ = (
        Index("idx_log_task_id", "task_id"),
        Index("idx_log_created_at", "created_at"),
    )
    
    def __repr__(self):
        return f"<TaskLog {self.task_id} [{self.log_level}] {self.message[:50]}>"


class Section(Base):
    """
    章节表
    
    记录每次分析中筛选出的关键章节
    """
    __tablename__ = "sections"
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 外键
    task_id = Column(String(36), ForeignKey("tasks.task_id"), nullable=False)
    
    # 章节信息
    section_id = Column(String(50), nullable=False, comment="章节编号")
    title = Column(String(500), nullable=False, comment="章节标题")
    reason = Column(Text, comment="为什么选择这个章节")
    priority = Column(Integer, comment="优先级")
    start_page = Column(Integer, comment="起始页码")
    end_page = Column(Integer, comment="结束页码")
    start_index = Column(Integer, comment="在content_list中的起始索引")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    
    # 关联关系
    task = relationship("Task", back_populates="sections")
    
    # 索引
    __table_args__ = (
        Index("idx_section_task_id", "task_id"),
        Index("idx_section_title", "title"),
    )
    
    def __repr__(self):
        return f"<Section {self.section_id} {self.title}>"


class Requirement(Base):
    """
    需求表
    
    存储提取的需求矩阵，支持后续查询和复用
    """
    __tablename__ = "requirements"
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 外键
    task_id = Column(String(36), ForeignKey("tasks.task_id"), nullable=False)
    
    # 需求标识
    matrix_id = Column(String(50), nullable=False, comment="需求唯一ID")
    section_id = Column(String(50), comment="章节编号")
    section_title = Column(String(500), comment="章节标题")
    page_number = Column(Integer, comment="页码")
    
    # 需求内容（8字段模型）
    requirement = Column(Text, nullable=False, comment="需求内容")
    original_text = Column(Text, nullable=False, comment="原文")
    response_suggestion = Column(Text, comment="应答方向")
    risk_warning = Column(Text, comment="风险提示")
    notes = Column(Text, comment="备注")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    
    # 关联关系
    task = relationship("Task", back_populates="requirements")
    
    # 索引（支持全文搜索和多维度查询）
    __table_args__ = (
        Index("idx_req_task_id", "task_id"),
        Index("idx_req_matrix_id", "matrix_id"),
        Index("idx_req_section_id", "section_id"),
    )
    
    def __repr__(self):
        return f"<Requirement {self.matrix_id} {self.requirement[:30]}>"

