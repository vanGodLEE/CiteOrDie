"""
PageIndex解析节点
使用PageIndex解析PDF并生成条款树结构
"""

from typing import Dict, Any
from loguru import logger
from app.core.states import TenderAnalysisState, PageIndexDocument, PageIndexNode
from app.services.pageindex_service import get_pageindex_service
from app.api.async_tasks import TaskManager
from app.utils.progress_helper import update_progress, log_step


def pageindex_parser_node(state: TenderAnalysisState) -> Dict[str, Any]:
    """
    PageIndex解析节点 - 替代MinerU
    
    输入：
    - state.pdf_path: PDF文件路径
    
    输出：
    - state.pageindex_document: PageIndex生成的条款树文档
    
    工作流程：
    1. 调用PageIndex服务解析PDF
    2. 生成包含层级结构的文档树
    3. 每个节点包含title, start_index, end_index, summary
    4. 初始化每个节点的requirements字段为空列表（后续由enricher填充）
    """
    logger.info("=" * 60)
    logger.info("PageIndex解析节点开始执行")
    logger.info("=" * 60)
    
    pdf_path = state["pdf_path"]
    task_id = state.get("task_id")
    
    # 更新任务进度
    update_progress(task_id, 5, "📄 准备解析文档结构...")
    log_step(task_id, "初始化文档解析器")
    
    try:
        # 获取PageIndex服务
        pageindex_service = get_pageindex_service()
        log_step(task_id, "PageIndex服务已加载")
        
        # 解析PDF
        logger.info(f"调用文档解析器: {pdf_path}")
        update_progress(task_id, 10, "📖 正在识别文档目录结构...")
        log_step(task_id, "扫描PDF页面，识别标题层级")
        
        result = pageindex_service.parse_pdf(pdf_path)
        
        log_step(task_id, "文档解析完成，构建章节树")
        print(f"文档解析器返回结果:{result} ")
        
        # 验证返回结果
        if not isinstance(result, dict):
            raise ValueError(f"文档解析器返回结果类型错误: {type(result)}")
        
        logger.debug(f"文档解析器返回结果键: {list(result.keys())}")
        
        structure = result.get("structure", [])
        logger.info(f"获取到 {len(structure)} 个顶层节点")
        
        if not structure:
            logger.warning("⚠️ 文档解析器未返回任何结构节点，可能文档无法解析目录")
            # 创建一个默认的根节点
            structure = [{
                "node_id": "0",
                "title": "全文档",
                "level": 0,
                "start_index": 1,
                "end_index": 999,
                "summary": "完整文档内容",
                "nodes": []
            }]
        
        # 转换为PageIndexDocument模型
        try:
            pageindex_doc = PageIndexDocument(
                doc_name=result.get("doc_name", "未知文档"),
                doc_description=result.get("doc_description"),
                structure=[PageIndexNode(**node) for node in structure]
            )
        except Exception as parse_error:
            logger.error(f"转换文档解析器输出内容时出错: {parse_error}")
            logger.error(f"问题节点数据: {structure[0] if structure else '无数据'}")
            raise
        
        # 统计信息
        total_nodes = len(pageindex_service.flatten_tree_to_nodes(result.get("structure", [])))
        leaf_nodes = pageindex_doc.get_all_leaf_nodes()
        
        logger.info(f"✓ 文档解析器解析完成")
        logger.info(f"  - 文档名称: {pageindex_doc.doc_name}")
        logger.info(f"  - 总节点数: {total_nodes}")
        logger.info(f"  - 叶子节点数: {len(leaf_nodes)}")
        
        # 更新任务进度
        update_progress(task_id, 18, "🔍 分析文档层级结构")
        log_step(task_id, f"发现{total_nodes}个节点，其中{len(leaf_nodes)}个章节可提取条款")
        update_progress(task_id, 20, f"✅ 文档结构解析完成", f"{len(leaf_nodes)}个章节待处理")
        
        return {
            "pageindex_document": pageindex_doc
        }
        
    except Exception as e:
        error_msg = f"文档解析器解析失败: {str(e)}"
        logger.error(error_msg)
        
        if task_id:
            TaskManager.log_progress(
                task_id,
                f"✗ {error_msg}",
                0
            )
        
        return {
            "error_message": error_msg,
            "pageindex_document": None
        }

