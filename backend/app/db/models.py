"""
数据库ORM模型

表结构设计：
1. Task - 任务主表
2. TaskLog - 任务日志表（SSE消息）
3. Section - 选中的章节表
4. Clause - 条款矩阵表
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
    file_hash = Column(String(64), index=True, comment="文件SHA256哈希值，用于幂等性检查")
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
    total_clauses = Column(Integer, default=0, comment="提取的条款总数")
    total_requirements = Column(Integer, default=0, comment="提取的条款总数（向后兼容字段，实际存储条款数）")
    
    # 分析结果（JSON存储）
    document_tree_json = Column(Text, comment="PageIndex文档树结构（JSON格式）")
    quality_report_json = Column(Text, comment="质量报告（JSON格式）：包含解析精度、原文抽取成功率等指标")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment="任务创建时间")
    started_at = Column(DateTime, comment="开始执行时间")
    completed_at = Column(DateTime, comment="完成时间")
    elapsed_seconds = Column(Float, default=0.0, comment="任务耗时（秒）")
    
    # 关联关系
    logs = relationship("TaskLog", back_populates="task", cascade="all, delete-orphan")
    sections = relationship("Section", back_populates="task", cascade="all, delete-orphan")
    clauses = relationship("Clause", back_populates="task", cascade="all, delete-orphan")
    
    # 索引
    __table_args__ = (
        Index("idx_task_status", "status"),
        Index("idx_task_created_at", "created_at"),
        Index("idx_task_file_hash", "file_hash"),
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
    
    # ✅ 新增：位置信息（JSON格式存储bbox坐标列表）
    positions_json = Column(Text, comment="bbox坐标列表（JSON格式）：[[page, x1, y1, x2, y2], ...]")
    
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


class Clause(Base):
    """
    可执行条款表（Actionable Clauses）
    
    支持从多种文档类型中提取结构化条款：招标书、合同、合规制度、SOP、标准规范、政策文件、协议等
    包含条款的结构化字段（type, actor, action, object, condition, deadline, metric）
    以及视觉内容和位置信息
    """
    __tablename__ = "clauses"
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 外键
    task_id = Column(String(36), ForeignKey("tasks.task_id"), nullable=False)
    
    # 条款标识
    matrix_id = Column(String(50), nullable=False, comment="条款唯一ID")
    section_id = Column(String(50), comment="章节编号")
    section_title = Column(String(500), comment="章节标题")
    page_number = Column(Integer, comment="页码")
    
    # 条款结构化字段（新增）
    clause_type = Column(String(20), nullable=False, comment="条款类型：obligation/requirement/prohibition/deliverable/deadline/penalty/definition")
    actor = Column(String(100), comment="执行主体：supplier/buyer/system/organization/role")
    action = Column(String(100), comment="执行动作：submit/provide/ensure/record/comply/禁止...")
    object = Column(String(200), comment="作用对象：document/feature/KPI/material")
    condition = Column(Text, comment="触发条件：if/when/unless等条件描述")
    deadline = Column(String(200), comment="时间要求：具体日期、相对时间、周期性要求")
    metric = Column(String(200), comment="量化指标：具体数值、范围、比较运算符")
    
    # 原文内容
    original_text = Column(Text, nullable=False, comment="条款原文")
    
    # 视觉扩展字段
    image_caption = Column(Text, comment="图片内容描述（视觉模型分析结果）")
    table_caption = Column(Text, comment="表格内容描述（表格结构化数据）")
    
    # 位置信息（JSON格式存储bbox坐标列表）
    positions_json = Column(Text, comment="bbox坐标列表（JSON格式）：[[page, x1, y1, x2, y2], ...]，用于PDF标注")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    
    # 关联关系
    task = relationship("Task", back_populates="clauses")
    
    # 索引（支持全文搜索和多维度查询）
    __table_args__ = (
        Index("idx_clause_task_id", "task_id"),
        Index("idx_clause_matrix_id", "matrix_id"),
        Index("idx_clause_section_id", "section_id"),
        Index("idx_clause_type", "clause_type"),
    )
    
    def __repr__(self):
        return f"<Clause {self.matrix_id} [{self.clause_type}] {self.original_text[:30]}>"



