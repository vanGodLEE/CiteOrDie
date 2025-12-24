"""
LangGraph工作流定义

构建基于PageIndex的招标分析工作流：
pageindex_parser → Map(Enrichers) → Auditor
"""

import time
import json
import uuid
from pathlib import Path
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
    
    工作流拓扑（修复版）：
    START → pageindex_parser → [text_fillers并行] → aggregator → [enrichers并行] → auditor → END
    
    关键点：
    1. pageindex_parser: 调用PageIndex解析PDF，生成文档树结构
    2. text_fillers (并行): 为每个节点并行填充精确原文
    3. aggregator: 汇聚所有text_filler（避免重复触发enrichers）
    4. enrichers (并行): 为每个叶子节点并行提取需求（基于标题+原文）
    5. auditor: 汇总所有需求，生成最终矩阵
    
    性能优化：
    - text_fillers并行执行，大幅提升原文填充速度
    - enrichers并行执行，充分利用LLM并发能力
    
    重要：aggregator是必须的汇聚节点，防止enrichers被重复触发！
    """
    # 创建状态图
    workflow = StateGraph(TenderAnalysisState)
    
    # 添加节点
    workflow.add_node("pageindex_parser", pageindex_parser_node)
    workflow.add_node("text_filler", text_filler_node)  # 单个节点的填充
    workflow.add_node("aggregator", aggregator_node)  # 汇聚节点（必须！）
    workflow.add_node("enricher", pageindex_enricher_node)
    workflow.add_node("auditor", auditor_node)
    
    # 连接边
    workflow.add_edge(START, "pageindex_parser")
    
    # 动态Map1：为每个节点创建一个Send到text_filler（并行填充原文）
    workflow.add_conditional_edges("pageindex_parser", route_to_text_fillers)
    
    # 所有text_filler完成后，汇聚到aggregator（避免重复）
    workflow.add_edge("text_filler", "aggregator")
    
    # 动态Map2：从aggregator路由到enrichers（只执行一次！）
    workflow.add_conditional_edges("aggregator", route_to_enrichers)
    
    # 所有enricher完成后，汇总到auditor
    workflow.add_edge("enricher", "auditor")
    workflow.add_edge("auditor", END)
    
    # 编译图
    graph = workflow.compile()
    logger.info("招标分析工作流图构建完成（修复重复执行Bug）")
    
    return graph


def route_to_text_fillers(state: TenderAnalysisState):
    """
    动态路由：为每个节点创建一个Send到text_filler（并行填充原文）
    
    策略：处理所有节点（包括父节点和叶子节点）
    
    特殊处理：如果pageindex_parser失败，直接跳转到END
    """
    pageindex_doc = state.get("pageindex_document")
    pdf_path = state.get("pdf_path")
    task_id = state.get("task_id")
    error_message = state.get("error_message")
    
    # 如果有错误消息或pageindex_document为None，说明解析失败，直接终止
    if error_message or not pageindex_doc:
        logger.error(f"PageIndex解析失败，工作流终止: {error_message or '未找到pageindex_document'}")
        return END
    
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


def aggregator_node(state: TenderAnalysisState) -> Dict[str, Any]:
    """
    汇聚节点 - 等待所有text_filler完成
    
    重要：这个节点是必须的！
    如果没有这个节点，route_to_enrichers会被每个text_filler触发，
    导致enrichers被重复执行N次（N=节点数）！
    
    返回：空字典（不修改状态，避免并发冲突）
    """
    pageindex_doc = state.get("pageindex_document")
    pdf_path = state.get("pdf_path")
    
    if pageindex_doc:
        # 统计填充情况（仅用于日志）
        all_nodes = []
        for root in pageindex_doc.structure:
            all_nodes.extend(root.get_all_nodes())
        
        filled_count = sum(1 for node in all_nodes if node.original_text)
        total_count = len(all_nodes)
        
        logger.info(f"✓ Text Filler阶段完成")
        logger.info(f"  - 总节点数: {total_count}")
        logger.info(f"  - 已填充原文: {filled_count}")
        logger.info(f"  - 填充率: {filled_count/total_count*100:.1f}%")
        
        # 保存中间文件（填充了original_text的完整文档）
        if pdf_path:
            _save_middle_json(pageindex_doc, pdf_path)
    
    # 返回空字典，不修改状态
    return {}


def _save_middle_json(pageindex_doc, pdf_path: str):
    """
    保存填充了original_text的中间JSON文件
    
    Args:
        pageindex_doc: PageIndexDocument对象
        pdf_path: 原始PDF路径
    """
    try:
        # 1. 创建middle_json目录
        middle_dir = Path("middle_json")
        middle_dir.mkdir(exist_ok=True)
        
        # 2. 生成文件名：源文件名_唯一ID.json
        pdf_name = Path(pdf_path).stem
        unique_id = str(uuid.uuid4())[:8]
        filename = f"{pdf_name}_{unique_id}.json"
        filepath = middle_dir / filename
        
        # 3. 转换为字典并保存
        json_data = pageindex_doc.dict()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✓ 中间文件已保存: {filepath}")
        
    except Exception as e:
        logger.error(f"保存中间文件失败: {str(e)}")


def route_to_enrichers(state: TenderAnalysisState) -> List[Send]:
    """
    从aggregator路由到enrichers
    
    注意：此函数在aggregator之后执行，确保只执行一次
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
