"""
核心数据模型和State定义

这个模块定义了整个招标分析系统的数据结构，包括：
1. 需求条款模型（RequirementItem）- 核心业务对象
2. 全局状态（TenderAnalysisState）- LangGraph工作流状态
3. 子状态（SectionState）- 并行Worker的输入
4. 辅助模型（ContentBlock, TOCItem等）
"""

from enum import Enum
from typing import Optional, List, Dict, Any, Annotated
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
import operator


# ============================================================================
# 核心业务模型 - 需求条款
# ============================================================================

class RequirementItem(BaseModel):
    """
    需求条款模型 - 简化的需求矩阵
    
    8个字段：
    1. 需求ID - 自动生成
    2. 需求 - 提取的需求内容
    3. 原文 - 对应原文
    4. 章节 - 对应的章节
    5. 页码 - 对应的页码
    6. 应答方向 - AI生成的建议
    7. 风险提示 - AI生成的风险提示
    8. 备注 - AI生成的备注
    """
    
    # 1. 需求ID
    matrix_id: str = Field(..., description="需求唯一ID，格式：{section_id}-REQ-{序号}")
    
    # 2. 需求内容
    requirement: str = Field(..., description="提取的需求内容，简明扼要")
    
    # 3. 原文
    original_text: str = Field(..., description="需求原文，必须是精确摘录")
    
    # 4. 章节
    section_id: str = Field(..., description="章节编号")
    section_title: str = Field(..., description="章节标题")
    
    # 5. 页码
    page_number: int = Field(..., description="PDF页码")
    
    # 6. 应答方向（AI生成）
    response_suggestion: str = Field(..., description="应答方向建议")
    
    # 7. 风险提示（AI生成）
    risk_warning: str = Field(..., description="风险提示")
    
    # 8. 备注（AI生成）
    notes: str = Field(..., description="备注")


# ============================================================================
# MinerU相关模型
# ============================================================================

class ContentBlock(BaseModel):
    """MinerU解析的内容块"""
    type: str = Field(..., description="内容类型：header/text/table/image等")
    text: str = Field(default="", description="文本内容")
    bbox: Optional[List[float]] = Field(None, description="边界框坐标 [x1,y1,x2,y2]")
    page_idx: int = Field(..., description="页面索引（0-based）")
    text_level: Optional[int] = Field(None, description="文本层级，1表示标题")
    
    class Config:
        # 允许接收MinerU的额外字段
        extra = "allow"


class TOCItem(BaseModel):
    """目录项"""
    section_id: str = Field(..., description="章节编号，如 '3.1'")
    title: str = Field(..., description="章节标题")
    page_number: int = Field(..., description="页码")
    level: int = Field(default=1, description="层级（1=一级标题，2=二级标题）")


class ParsedDocument(BaseModel):
    """MinerU解析后的文档结构"""
    content_list: List[ContentBlock] = Field(..., description="内容块列表")
    markdown: str = Field(default="", description="Markdown格式全文")
    toc: List[TOCItem] = Field(default_factory=list, description="目录结构")



# ============================================================================
# Planner相关模型
# ============================================================================

class SectionPlan(BaseModel):
    """Planner输出的章节规划"""
    section_id: str = Field(..., description="章节编号")
    title: str = Field(..., description="章节标题")
    reason: str = Field(..., description="为什么选择这个章节")
    priority: int = Field(..., ge=1, description="优先级（1最高，数字越大优先级越低）")
    start_page: int = Field(..., description="起始页码")
    end_page: Optional[int] = Field(None, description="结束页码（可选）")
    start_index: Optional[int] = Field(None, description="章节在content_list中的起始索引")


# ============================================================================
# LangGraph State定义
# ============================================================================

class TenderAnalysisState(TypedDict):
    """
    全局状态 - LangGraph工作流的核心状态
    
    数据流：
    1. 输入: pdf_path
    2. Planner: 生成 content_list, toc, target_sections
    3. Extractors (并行): 追加 requirements
    4. Auditor: 处理 requirements，生成 final_matrix
    """
    # 输入
    pdf_path: str
    use_mock: bool  # 是否使用Mock数据（开发阶段用）
    task_id: Optional[str]  # 任务ID，用于进度更新
    
    # MinerU解析结果
    content_list: List[Dict[str, Any]]  # MinerU的原始JSON输出
    markdown: str
    toc: List[TOCItem]
    
    # Planner输出
    target_sections: List[SectionPlan]
    
    # Extractors输出（关键：使用operator.add支持并行追加）
    # 这是并发安全的关键！多个Worker可以同时向这个列表追加数据
    requirements: Annotated[List[RequirementItem], operator.add]
    
    # Auditor输出
    final_matrix: List[RequirementItem]
    
    # 元数据
    processing_start_time: Optional[float]
    processing_end_time: Optional[float]
    error_message: Optional[str]



class SectionState(TypedDict):
    """
    子状态 - 传递给并行Worker节点的状态
    
    每个Extractor Worker会收到一个SectionState，包含：
    - 该章节的标识信息
    - 该章节的所有内容块
    """
    section_id: str
    section_title: str
    section_plan: SectionPlan
    task_id: Optional[str]  # 任务ID，用于进度更新
    content_blocks: List[ContentBlock]  # 该章节的所有内容块
    
    # Worker处理完后返回的结果（会被追加到全局State的requirements中）
    requirements: List[RequirementItem]


# ============================================================================
# 工具函数
# ============================================================================

def create_matrix_id(section_id: str, sequence: int) -> str:
    """
    生成需求矩阵ID
    
    Args:
        section_id: 章节编号，如 "3.1.2"
        sequence: 序号（1-based）
        
    Returns:
        格式化的ID，如 "3.1.2-REQ-001"
    """
    return f"{section_id}-REQ-{sequence:03d}"


def calculate_page_number(page_idx: int) -> int:
    """
    将MinerU的page_idx（0-based）转换为用户友好的页码（1-based）
    
    Args:
        page_idx: MinerU的页面索引（0开始）
        
    Returns:
        PDF页码（1开始）
    """
    return page_idx + 1
