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
# 核心业务模型 - 可执行条款
# ============================================================================

class ClauseItem(BaseModel):
    """
    可执行条款模型（Actionable Clauses）
    
    适用范围：标书、合同、合规制度、SOP、标准规范、政策文件等
    
    核心结构化字段：
    1. type - 条款类型
    2. actor - 执行主体
    3. action - 执行动作
    4. object - 作用对象
    5. condition - 触发条件
    6. deadline - 时间要求
    7. metric - 量化指标
    
    基础信息字段：
    8. matrix_id - 条款唯一ID
    9. original_text - 原文
    10. section_id - 章节编号
    11. section_title - 章节标题
    12. page_number - 页码
    13. image_caption - 图片描述（视觉内容）
    14. table_caption - 表格描述（表格内容）
    15. positions - PDF位置坐标
    """
    
    # 条款结构化字段（新增）
    type: str = Field(
        ...,
        description="条款类型：obligation(义务)|requirement(需求)|prohibition(禁止)|deliverable(交付物)|deadline(截止时间)|penalty(惩罚)|definition(定义)"
    )
    actor: Optional[str] = Field(
        None,
        description="执行主体：supplier(供应商)|buyer(采购方)|system(系统)|organization(组织)|role(角色名称)|其他"
    )
    action: Optional[str] = Field(
        None,
        description="执行动作：submit(提交)|provide(提供)|ensure(确保)|record(记录)|comply(遵守)|禁止...|其他动词"
    )
    object: Optional[str] = Field(
        None,
        description="作用对象：document(文档)|feature(功能)|KPI(指标)|material(材料)|其他名词"
    )
    condition: Optional[str] = Field(
        None,
        description="触发条件：if/when/unless等条件描述"
    )
    deadline: Optional[str] = Field(
        None,
        description="时间要求：具体日期、相对时间（如'合同签订后30天内'）、周期性要求"
    )
    metric: Optional[str] = Field(
        None,
        description="量化指标：具体数值、范围、比较运算符（>=, <=, range等）"
    )
    
    # 基础信息字段（保留原有硬性字段）
    matrix_id: str = Field(..., description="条款唯一ID，格式：{section_id}-CLS-{序号}")
    original_text: str = Field(..., description="条款原文，精确摘录")
    section_id: str = Field(..., description="章节编号")
    section_title: str = Field(..., description="章节标题")
    page_number: int = Field(..., description="PDF页码")
    
    # 视觉扩展字段
    image_caption: Optional[str] = Field(
        None,
        description="图片内容描述（如果条款来自图片，则包含视觉模型的分析结果）"
    )
    table_caption: Optional[str] = Field(
        None,
        description="表格内容描述（如果条款来自表格，则包含表格结构化数据）"
    )
    img_path: Optional[str] = Field(
        None,
        description="图片/表格的相对路径（如 'images/xxx.jpg'），用于精确定位content_list中的对应项"
    )
    
    # 位置定位字段
    positions: List[List[int]] = Field(
        default_factory=list,
        description="条款对应原文的bbox坐标列表，格式：[[page_idx, x1, y1, x2, y2], ...]（MinerU 0-based索引）"
    )




# ============================================================================
# PageIndex相关模型（条款树）
# ============================================================================

class PageIndexNode(BaseModel):
    """
    PageIndex的节点模型（递归结构） + 条款字段
    
    这是"条款树"的核心模型：
    - 继承PageIndex的原始结构（title, start_index, end_index, summary等）
    - 添加clauses字段，每个节点都可以包含条款
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
    original_text: Optional[str] = Field(None, description="精确提取的原文内容（行级别，用于条款提取）")
    
    # **新增：bbox坐标字段**
    positions: List[List[int]] = Field(
        default_factory=list,
        description="原文内容的bbox坐标列表，格式：[[page_idx, x1, y1, x2, y2], ...]"
    )
    
    # **关键扩展：条款字段**
    clauses: List[ClauseItem] = Field(default_factory=list, description="该节点的条款列表")
    
    
    # 辅助字段
    path: Optional[str] = Field(None, description="节点路径，如 '第一章/1.1 技术要求'")
    
    def is_leaf(self) -> bool:
        """判断是否为叶子节点"""
        return len(self.nodes) == 0
    
    def get_all_clauses_recursive(self) -> List[ClauseItem]:
        """递归获取当前节点及所有子节点的条款"""
        all_clauses = list(self.clauses)
        for child in self.nodes:
            all_clauses.extend(child.get_all_clauses_recursive())
        return all_clauses
    
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
    
    def count_total_clauses(self) -> int:
        """统计该节点及所有子节点的总条款数"""
        return len(self.get_all_clauses_recursive())


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
    
    def count_total_clauses(self) -> int:
        """统计整个文档的总条款数"""
        total = 0
        for root_node in self.structure:
            total += root_node.count_total_clauses()
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
    5. Enricher (并行): 遍历叶子节点，提取条款（文本+视觉）
    6. Auditor: 收集所有节点的条款，生成 final_matrix
    """
    # 输入
    pdf_path: str
    use_mock: bool  # 是否使用Mock数据（开发阶段用）
    task_id: Optional[str]  # 任务ID，用于进度更新
    
    # PageIndex解析结果
    pageindex_document: Optional[PageIndexDocument]  # PageIndex生成的条款树文档
    
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
    clauses: Annotated[List[ClauseItem], operator.add]
    
    # Auditor输出
    final_matrix: List[ClauseItem]
    
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
    clauses: List[ClauseItem]


# ============================================================================
# 工具函数
# ============================================================================

def create_matrix_id(section_id: str, sequence: int) -> str:
    """
    生成条款矩阵ID
    
    Args:
        section_id: 章节编号，如 "3.1.2"
        sequence: 序号（1-based）
        
    Returns:
        格式化的ID，如 "3.1.2-CLS-001"
    """
    return f"{section_id}-CLS-{sequence:03d}"
