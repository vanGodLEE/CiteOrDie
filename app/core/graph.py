"""
LangGraph工作流定义

构建招标分析的完整工作流：
Planner → Map(Extractors) → Auditor
"""

import time
from typing import List
from loguru import logger
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from app.core.states import TenderAnalysisState, SectionState
from app.nodes.planner import planner_node
from app.nodes.extractor import extractor_node
from app.nodes.auditor import auditor_node
from app.services.pdf_parser import PDFParserService


def create_tender_analysis_graph():
    """
    创建招标分析工作流图
    
    工作流拓扑：
    START → parse_pdf → planner → [extractor_1, extractor_2, ...] → auditor → END
    
    关键点：
    1. parse_pdf: 解析PDF文档（或读取Mock数据）
    2. planner: 识别关键章节
    3. extractors (并行): 每个章节一个Worker
    4. auditor: 汇总、去重、排序
    """
    # 创建状态图
    workflow = StateGraph(TenderAnalysisState)
    
    # 添加节点
    workflow.add_node("parse_pdf", parse_pdf_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("extractor", extractor_node)
    workflow.add_node("auditor", auditor_node)
    
    # 连接边
    workflow.add_edge(START, "parse_pdf")
    workflow.add_edge("parse_pdf", "planner")
    
    # 动态Map：为每个target_section创建一个Send到extractor
    workflow.add_conditional_edges("planner", route_to_extractors)
    
    # 所有extractor完成后，汇总到auditor
    workflow.add_edge("extractor", "auditor")
    workflow.add_edge("auditor", END)
    
    # 编译图
    graph = workflow.compile()
    logger.info("LangGraph工作流图构建完成")
    
    return graph


def parse_pdf_node(state: TenderAnalysisState) -> dict:
    """
    PDF解析节点
    
    负责调用MinerU解析PDF（或读取Mock数据）
    """
    logger.info("====== PDF解析节点开始执行 ======")
    
    pdf_path = state["pdf_path"]
    use_mock = state.get("use_mock", False)
    
    parser = PDFParserService()
    parsed_doc = parser.parse_pdf(pdf_path, use_mock=use_mock)
    
    logger.info(f"PDF解析完成: {len(parsed_doc.content_list)} 个内容块, {len(parsed_doc.toc)} 个目录项")
    
    return {
        "content_list": [block.dict() for block in parsed_doc.content_list],
        "markdown": parsed_doc.markdown,
        "toc": parsed_doc.toc,
        "processing_start_time": time.time()
    }



def route_to_extractors(state: TenderAnalysisState) -> List[Send]:
    """
    动态路由：为每个target_section创建一个Send对象
    
    这是LangGraph的Map操作核心！
    每个Send对象会启动一个独立的extractor节点实例
    """
    target_sections = state.get("target_sections", [])
    
    if not target_sections:
        logger.warning("Planner没有识别出任何关键章节，跳过提取步骤")
        # 返回空列表，直接进入auditor
        return []
    
    logger.info(f"准备启动 {len(target_sections)} 个并行Extractor Worker")
    
    sends = []
    parser = PDFParserService()
    
    for section_plan in target_sections:
        # 从content_list中提取该章节的内容
        # 注意：content_list在state中是Dict格式，需要转回ContentBlock
        from app.core.states import ContentBlock
        content_blocks = [
            ContentBlock(**block) 
            for block in state["content_list"]
        ]
        
        section_content = parser.get_section_content(
            content_blocks,
            section_plan
        )
        
        # 创建SectionState
        section_state = SectionState(
            section_id=section_plan.section_id,
            section_title=section_plan.title,
            section_plan=section_plan,
            content_blocks=section_content,
            requirements=[],  # 初始化为空列表
            task_id=state.get("task_id")  # 传递task_id用于进度更新
        )
        
        # 创建Send对象
        sends.append(Send("extractor", section_state))
    
    logger.info(f"创建了 {len(sends)} 个Send对象，准备并行执行")
    return sends
