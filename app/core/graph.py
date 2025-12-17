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
    
    工作流拓扑（并行优化版）：
    START → pageindex_parser → [text_fillers并行] → text_filler_aggregator → [enrichers并行] → auditor → END
    
    关键点：
    1. pageindex_parser: 调用PageIndex解析PDF，生成文档树结构
    2. text_fillers (并行): 为每个节点并行填充精确原文
    3. text_filler_aggregator: 汇聚所有text_filler结果，准备enrichers
    4. enrichers (并行): 为每个叶子节点并行提取需求
    5. auditor: 汇总所有需求，生成最终矩阵
    
    性能优化：
    - text_fillers并行执行，大幅提升原文填充速度
    - enrichers并行执行，充分利用LLM并发能力
    
    注意：text_filler_aggregator是关键汇聚节点，确保所有text_filler完成后才开始enrichers
    """
    # 创建状态图
    workflow = StateGraph(TenderAnalysisState)
    
    # 添加节点
    workflow.add_node("pageindex_parser", pageindex_parser_node)
    workflow.add_node("text_filler", text_filler_node)  # 单个节点的填充
    workflow.add_node("text_filler_aggregator", text_filler_aggregator_node)  # 汇聚节点
    workflow.add_node("enricher", pageindex_enricher_node)
    workflow.add_node("auditor", auditor_node)
    
    # 连接边
    workflow.add_edge(START, "pageindex_parser")
    
    # 动态Map1：为每个节点创建一个Send到text_filler（并行填充原文）
    workflow.add_conditional_edges("pageindex_parser", route_to_text_fillers)
    
    # 所有text_filler完成后，汇聚到aggregator
    workflow.add_edge("text_filler", "text_filler_aggregator")
    
    # 动态Map2：从aggregator路由到enrichers（并行提取需求）
    workflow.add_conditional_edges("text_filler_aggregator", route_to_enrichers)
    
    # 所有enricher完成后，汇总到auditor
    workflow.add_edge("enricher", "auditor")
    workflow.add_edge("auditor", END)
    
    # 编译图
    graph = workflow.compile()
    logger.info("招标分析工作流图构建完成（并行优化版 + 汇聚节点）")
    
    return graph


def route_to_text_fillers(state: TenderAnalysisState) -> List[Send]:
    """
    动态路由：为每个节点创建一个Send到text_filler（并行填充原文）
    
    策略：处理所有节点（包括父节点和叶子节点）
    """
    pageindex_doc = state.get("pageindex_document")
    pdf_path = state.get("pdf_path")
    task_id = state.get("task_id")
    
    if not pageindex_doc:
        logger.warning("未找到pageindex_document，无法路由到text_fillers")
        return []
    
    # 获取所有节点（父节点+叶子节点）
    all_nodes = []
    for root in pageindex_doc.structure:
        all_nodes.extend(root.get_all_nodes())
    
    if not all_nodes:
        logger.warning("未找到任何节点，无法路由到text_fillers")
        return []
    
    logger.info(f"准备并行填充 {len(all_nodes)} 个节点的原文")
    
    # 为每个节点创建一个Send
    sends = []
    for node in all_nodes:
        # 创建TextFiller任务状态
        filler_state = {
            "node": node,
            "pdf_path": pdf_path,
            "task_id": task_id,
            "pageindex_document": pageindex_doc  # 传递完整文档用于计算兄弟节点
        }
        
        sends.append(Send("text_filler", filler_state))
    
    logger.info(f"✓ 路由完成，将并行执行 {len(sends)} 个text_filler任务")
    
    return sends


def text_filler_aggregator_node(state: TenderAnalysisState) -> Dict[str, Any]:
    """
    Text Filler汇聚节点 - 等待所有text_filler完成
    
    这是一个关键的汇聚节点，确保：
    1. 所有text_filler并行任务都已完成
    2. 所有节点的original_text和summary都已填充
    3. 准备好进入enricher阶段
    
    返回：
    - pageindex_document: 更新后的完整文档（所有节点都已填充原文）
    """
    pageindex_doc = state.get("pageindex_document")
    
    if pageindex_doc:
        # 统计填充情况
        all_nodes = []
        for root in pageindex_doc.structure:
            all_nodes.extend(root.get_all_nodes())
        
        filled_count = sum(1 for node in all_nodes if node.original_text)
        total_count = len(all_nodes)
        
        logger.info(f"✓ Text Filler阶段完成")
        logger.info(f"  - 总节点数: {total_count}")
        logger.info(f"  - 已填充原文: {filled_count}")
        logger.info(f"  - 填充率: {filled_count/total_count*100:.1f}%")
    
    return {
        "pageindex_document": pageindex_doc
    }


def route_to_enrichers(state: TenderAnalysisState) -> List[Send]:
    """
    从text_filler_aggregator路由到enrichers
    
    注意：此函数在所有text_filler完成并汇聚后执行一次
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
    
    logger.info(f"准备并行提取 {len(leaf_nodes)} 个叶子节点的需求")
    
    # 为每个叶子节点创建一个Send
    sends = []
    for node in leaf_nodes:
        node.path = f"{node.node_id or 'UNKNOWN'}: {node.title}"
        
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
        
        sends.append(Send("enricher", section_state))
    
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
