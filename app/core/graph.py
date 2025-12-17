"""
LangGraph工作流定义

构建基于PageIndex的招标分析工作流：
pageindex_parser → Map(Enrichers) → Auditor
"""

import time
from typing import List, Dict, Any
from loguru import logger
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from app.core.states import TenderAnalysisState, SectionState, PageIndexNode
from app.nodes.pageindex_parser import pageindex_parser_node
from app.nodes.text_filler import text_filler_node
from app.nodes.pageindex_enricher import pageindex_enricher_node
from app.nodes.auditor import auditor_node


def create_tender_analysis_graph():
    """
    创建招标分析工作流图
    
    工作流拓扑（重构后）：
    START → pageindex_parser → text_filler → [enricher_1, enricher_2, ...] → auditor → END
    
    关键点：
    1. pageindex_parser: 调用PageIndex解析PDF，生成文档树结构
    2. text_filler: 递归遍历树，为每个节点填充精确原文（行级别）
    3. enrichers (并行): 基于精确原文为每个叶子节点提取需求
    4. auditor: 汇总所有需求，生成最终矩阵（无需复杂去重）
    """
    # 创建状态图
    workflow = StateGraph(TenderAnalysisState)
    
    # 添加节点
    workflow.add_node("pageindex_parser", pageindex_parser_node)
    workflow.add_node("text_filler", text_filler_node)
    workflow.add_node("enricher", pageindex_enricher_node)
    workflow.add_node("auditor", auditor_node)
    
    # 连接边
    workflow.add_edge(START, "pageindex_parser")
    workflow.add_edge("pageindex_parser", "text_filler")
    
    # 动态Map：为每个叶子节点创建一个Send到enricher
    workflow.add_conditional_edges("text_filler", route_to_enrichers)
    
    # 所有enricher完成后，汇总到auditor
    workflow.add_edge("enricher", "auditor")
    workflow.add_edge("auditor", END)
    
    # 编译图
    graph = workflow.compile()
    logger.info("招标分析工作流图构建完成（重构后：PageIndex + TextFiller架构）")
    
    return graph


def route_to_enrichers(state: TenderAnalysisState) -> List[Send]:
    """
    动态路由：为每个需要处理的节点创建一个Send对象
    
    策略：处理所有叶子节点（最细粒度）
    """
    pageindex_doc = state.get("pageindex_document")
    task_id = state.get("task_id")
    
    if not pageindex_doc:
        logger.warning("未找到pageindex_document，无法路由到enrichers")
        return []
    
    # 获取所有叶子节点
    leaf_nodes = pageindex_doc.get_all_leaf_nodes()
    
    if not leaf_nodes:
        logger.warning("未找到叶子节点，无法路由到enrichers")
        return []
    
    logger.info(f"准备并行处理 {len(leaf_nodes)} 个叶子节点")
    
    # 为每个叶子节点创建一个Send
    sends = []
    for node in leaf_nodes:
        # 构建节点路径
        node.path = f"{node.node_id or 'UNKNOWN'}: {node.title}"
        
        # 创建SectionState
        section_state = SectionState(
            pageindex_node=node,
            task_id=task_id,
            section_node=None,
            content_blocks=None,
            section_id=node.node_id,
            section_title=node.title,
            section_plan=None,
            requirements=[]
        )
        
        # 创建Send对象
        sends.append(Send("enricher", section_state))
        
        logger.debug(f"  - 路由节点: {node.path} (页码: {node.start_index}-{node.end_index})")
    
    logger.info(f"✓ 路由完成，将并行执行 {len(sends)} 个enricher任务")
    
    return sends


def run_analysis(pdf_path: str, task_id: str = None) -> Dict[str, Any]:
    """
    执行分析工作流
    
    Args:
        pdf_path: PDF文件路径
        task_id: 任务ID（用于进度更新）
        
    Returns:
        分析结果字典
    """
    logger.info(f"开始分析: {pdf_path}")
    
    # 创建工作流图
    graph = create_tender_analysis_graph()
    
    # 初始化状态
    initial_state: TenderAnalysisState = {
        "pdf_path": pdf_path,
        "use_mock": False,
        "task_id": task_id,
        "pageindex_document": None,
        "content_list": [],
        "markdown": "",
        "toc": [],
        "toc_tree": None,
        "target_sections": [],
        "requirements": [],
        "final_matrix": [],
        "processing_start_time": time.time(),
        "processing_end_time": None,
        "error_message": None
    }
    
    try:
        # 执行工作流
        final_state = graph.invoke(initial_state)
        
        # 记录结果
        processing_time = final_state.get("processing_end_time", time.time()) - final_state.get("processing_start_time", 0)
        requirements_count = len(final_state.get("final_matrix", []))
        
        logger.info(f"✓ 分析完成")
        logger.info(f"  - 处理时间: {processing_time:.2f}秒")
        logger.info(f"  - 需求总数: {requirements_count}条")
        
        return {
            "status": "success",
            "requirements_count": requirements_count,
            "matrix": final_state.get("final_matrix", []),
            "processing_time": processing_time,
            "pageindex_document": final_state.get("pageindex_document")
        }
        
    except Exception as e:
        logger.error(f"分析失败: {str(e)}")
        return {
            "status": "error",
            "error_message": str(e),
            "requirements_count": 0,
            "matrix": [],
            "processing_time": 0
        }
