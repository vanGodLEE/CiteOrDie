"""
核心数据模型和State定义

基于PageIndex的招标分析系统数据结构
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any, Annotated
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
import operator


# ============================================================================
# 核心业务模型 - 需求条款
# ============================================================================

class RequirementItem(BaseModel):
    """
    需求条款模型（增强版 - 支持视觉内容和位置定位）
    
    核心字段（9个基础字段）：
    1. 需求ID - 自动生成
    2. 需求 - 提取的需求内容
    3. 原文 - 对应原文
    4. 章节 - 对应的章节
    5. 页码 - 对应的页码
    6. 类型 - 需求类型分类
    7. 应答方向 - AI生成的建议
    8. 风险提示 - AI生成的风险提示
    9. 备注 - AI生成的备注
    
    视觉扩展字段（3个字段）：
    10. image_caption - 图片分析描述
    11. table_caption - 表格分析描述
    12. img_path - 图片/表格的文件路径（用于精确定位）
    
    位置定位字段（1个字段）：
    13. positions - 需求原文在PDF中的bbox坐标
    """
    
    # 核心字段
    matrix_id: str = Field(..., description="需求唯一ID，格式：{section_id}-REQ-{序号}")
    requirement: str = Field(..., description="提取的需求内容，简明扼要")
    original_text: str = Field(..., description="需求原文，必须是精确摘录")
    section_id: str = Field(..., description="章节编号")
    section_title: str = Field(..., description="章节标题")
    page_number: int = Field(..., description="PDF页码")
    category: str = Field(
        default="OTHER",
        description="需求类型：SOLUTION(技术/服务方案)|QUALIFICATION(资质)|BUSINESS(商务)|FORMAT(格式)|PROCESS(流程)|OTHER(其他/不确定)"
    )
    response_suggestion: str = Field(..., description="应答方向建议")
    risk_warning: str = Field(..., description="风险提示")
    notes: str = Field(..., description="备注")
    
    # 视觉扩展字段
    image_caption: Optional[str] = Field(
        None,
        description="图片内容描述（如果需求来自图片，则包含视觉模型的分析结果）"
    )
    table_caption: Optional[str] = Field(
        None,
        description="表格内容描述（如果需求来自表格，则包含表格结构化数据）"
    )
    img_path: Optional[str] = Field(
        None,
        description="图片/表格的相对路径（如 'images/xxx.jpg'），用于精确定位content_list中的对应项"
    )
    
    # 位置定位字段
    positions: List[List[int]] = Field(
        default_factory=list,
        description="需求对应原文的bbox坐标列表，格式：[[page_idx, x1, y1, x2, y2], ...]（MinerU 0-based索引）"
    )


# ============================================================================
# PageIndex相关模型（需求树）
# ============================================================================

class PageIndexNode(BaseModel):
    """
    PageIndex的节点模型（递归结构） + 需求字段
    
    这是"需求树"的核心模型：
    - 继承PageIndex的原始结构（title, start_index, end_index, summary等）
    - 添加requirements字段，每个节点都可以包含需求
    """
    # PageIndex原始字段
    node_id: Optional[str] = Field(None, description="PageIndex生成的节点ID，如 '0001', '0002'")
    structure: Optional[str] = Field(None, description="章节序号，如 '2.1', '2.1.1'（用于匹配）")
    title: str = Field(..., description="章节标题（不含序号）")
    start_index: int = Field(..., description="起始页码（1-based）")
    end_index: int = Field(..., description="结束页码（1-based）")
    summary: Optional[str] = Field(None, description="PageIndex生成的节点摘要（页级别，仅供参考）")
    text: Optional[str] = Field(None, description="PageIndex生成的节点全文（可选）")
    
    # 树形结构
    nodes: List[PageIndexNode] = Field(default_factory=list, description="子节点列表")
    
    # **新增：精确原文字段**
    original_text: Optional[str] = Field(None, description="精确提取的原文内容（行级别，用于需求提取）")
    
    # **新增：bbox坐标字段**
    positions: List[List[int]] = Field(
        default_factory=list,
        description="原文内容的bbox坐标列表，格式：[[page_idx, x1, y1, x2, y2], ...]"
    )
    
    # **关键扩展：需求字段**
    requirements: List[RequirementItem] = Field(default_factory=list, description="该节点的需求列表")
    
    # 辅助字段
    path: Optional[str] = Field(None, description="节点路径，如 '第一章/1.1 技术要求'")
    
    def is_leaf(self) -> bool:
        """判断是否为叶子节点"""
        return len(self.nodes) == 0
    
    def get_all_requirements_recursive(self) -> List[RequirementItem]:
        """递归获取当前节点及所有子节点的需求"""
        all_reqs = list(self.requirements)
        for child in self.nodes:
            all_reqs.extend(child.get_all_requirements_recursive())
        return all_reqs
    
    def get_leaf_nodes(self) -> List[PageIndexNode]:
        """递归获取所有叶子节点"""
        if self.is_leaf():
            return [self]
        
        leaves = []
        for child in self.nodes:
            leaves.extend(child.get_leaf_nodes())
        return leaves
    
    def get_all_nodes(self) -> List[PageIndexNode]:
        """递归获取所有节点（包括自己和所有子孙节点）"""
        all_nodes = [self]
        for child in self.nodes:
            all_nodes.extend(child.get_all_nodes())
        return all_nodes
    
    def find_next_sibling(self, siblings: List['PageIndexNode']) -> Optional['PageIndexNode']:
        """在兄弟节点列表中找到下一个兄弟节点"""
        try:
            current_idx = siblings.index(self)
            if current_idx < len(siblings) - 1:
                return siblings[current_idx + 1]
        except ValueError:
            pass
        return None
    
    def count_total_requirements(self) -> int:
        """统计该节点及所有子节点的总需求数"""
        return len(self.get_all_requirements_recursive())


class PageIndexDocument(BaseModel):
    """
    PageIndex解析后的完整文档结构
    """
    doc_name: str = Field(..., description="文档名称")
    doc_description: Optional[str] = Field(None, description="文档整体描述（PageIndex生成）")
    structure: List[PageIndexNode] = Field(..., description="文档树结构（根节点列表）")
    
    def get_all_leaf_nodes(self) -> List[PageIndexNode]:
        """获取所有叶子节点"""
        leaves = []
        for root_node in self.structure:
            leaves.extend(root_node.get_leaf_nodes())
        return leaves
    
    def count_total_requirements(self) -> int:
        """统计整个文档的总需求数"""
        total = 0
        for root_node in self.structure:
            total += root_node.count_total_requirements()
        return total


# ============================================================================
# LangGraph State定义
# ============================================================================

class TenderAnalysisState(TypedDict):
    """
    全局状态 - LangGraph工作流的核心状态
    
    数据流（基于PageIndex + MinerU）：
    1. 输入: pdf_path
    2. PageIndex Parser: 解析生成 pageindex_document（包含树结构）
    3. MinerU Parser: 完整解析PDF，生成 mineru_content_list（包含图片、表格）
    4. Text Filler (并行): 基于content_list为每个节点填充original_text
    5. Enricher (并行): 遍历叶子节点，提取需求（文本+视觉）
    6. Auditor: 收集所有节点的需求，生成 final_matrix
    """
    # 输入
    pdf_path: str
    use_mock: bool  # 是否使用Mock数据（开发阶段用）
    task_id: Optional[str]  # 任务ID，用于进度更新
    
    # PageIndex解析结果
    pageindex_document: Optional[PageIndexDocument]  # PageIndex生成的需求树文档
    
    # MinerU解析结果（新增）
    mineru_result: Optional[Dict[str, Any]]  # MinerU完整解析结果
    mineru_content_list: List[Dict[str, Any]]  # MinerU内容列表（包含图片、表格）
    mineru_output_dir: Optional[str]  # MinerU输出目录路径
    
    # 兼容字段（保留以避免破坏现有代码）
    content_list: List[Dict[str, Any]]
    markdown: str
    toc: List
    toc_tree: Optional[Any]
    target_sections: List
    
    # Extractors输出（使用operator.add支持并行追加）
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
    
    每个Enricher Worker收到一个SectionState，包含：
    - pageindex_node: PageIndex的节点（叶子节点）
    - task_id: 任务ID，用于进度更新
    - mineru_output_dir: MinerU输出目录（用于视觉模型访问图片）
    """
    pageindex_node: Optional[PageIndexNode]  # PageIndex的节点（叶子节点）
    task_id: Optional[str]  # 任务ID，用于进度更新
    mineru_output_dir: Optional[str]  # MinerU输出目录（用于视觉模型访问图片）
    
    # 兼容字段
    section_node: Optional[Any]
    content_blocks: Optional[List]
    section_id: Optional[str]
    section_title: Optional[str]
    section_plan: Optional[Any]
    
    # Worker处理完后返回的结果
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
