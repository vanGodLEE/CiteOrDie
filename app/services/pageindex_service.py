"""
PageIndex服务封装
集成PageIndex的文档结构化能力到TenderAnalysis系统

部署说明:
1. 将 PageIndex 代码放在项目根目录或安装为包
2. 确保环境中包含 PageIndex 的所有依赖
3. 配置 .env 中的 API_KEY 和 BASE_URL
"""

import sys
import os
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
from loguru import logger

# 方式1：如果PageIndex在项目根目录的pageindex文件夹
# 方式2：如果PageIndex在其他位置，需要添加路径
# 方式3：如果PageIndex作为包安装，直接导入

try:
    # 尝试直接导入（如果PageIndex已安装为包）
    from pageindex import page_index, config as pageindex_config
    logger.info("✓ PageIndex模块导入成功（已安装）")
except ImportError:
    # 如果未安装，尝试从本地路径导入
    PAGEINDEX_PATH = Path(__file__).parent.parent.parent / "pageindex"
    
    # 如果项目根目录没有，尝试从指定路径
    if not PAGEINDEX_PATH.exists():
        PAGEINDEX_PATH = Path("D:/dev/PageIndex")
    
    if PAGEINDEX_PATH.exists() and str(PAGEINDEX_PATH) not in sys.path:
        sys.path.insert(0, str(PAGEINDEX_PATH))
        logger.info(f"✓ 添加PageIndex路径: {PAGEINDEX_PATH}")
        from pageindex import page_index, config as pageindex_config
    else:
        raise ImportError(
            "无法找到PageIndex模块。请确保:\n"
            "1. PageIndex代码在项目根目录的pageindex文件夹，或\n"
            "2. PageIndex在 D:/dev/PageIndex，或\n"
            "3. PageIndex已通过 pip install -e 安装"
        )

class PageIndexService:
    """
    PageIndex服务封装类
    
    职责：
    1. 调用PageIndex解析PDF，生成文档树结构
    2. 处理Unicode编码问题（中文标题转换）
    3. 提供统一的接口供LangGraph调用
    4. 处理429限流错误，自动轮换备用模型
    """
    
    def __init__(
        self,
        model: str = "deepseek-chat",
        fallback_models: Optional[List[str]] = None,
        toc_check_pages: int = 10,
        max_pages_per_node: int = 10,
        max_tokens_per_node: int = 8000,
        add_node_id: bool = True,
        add_node_summary: bool = False,
        add_doc_description: bool = False,
        add_node_text: bool = False
    ):
        """
        初始化PageIndex服务
        
        Args:
            model: LLM模型名称（主模型）
            fallback_models: 备用模型列表（当主模型429限流时使用）
            toc_check_pages: 检查目录的页数范围
            max_pages_per_node: 每个节点最大页数
            max_tokens_per_node: 每个节点最大Token数
            add_node_id: 是否添加节点ID
            add_node_summary: 是否添加节点摘要
            add_doc_description: 是否添加文档描述
            add_node_text: 是否添加节点文本
        """
        self.primary_model = model
        self.fallback_models = fallback_models or []
        
        # 构建完整模型列表：[主模型, 备用模型1, 备用模型2, ...]
        self.all_models = [model] + self.fallback_models
        self.current_model_index = 0  # 当前使用的模型索引
        
        self.toc_check_pages = toc_check_pages
        self.max_pages_per_node = max_pages_per_node
        self.max_tokens_per_node = max_tokens_per_node
        self.add_node_id = add_node_id
        self.add_node_summary = add_node_summary
        self.add_doc_description = add_doc_description
        self.add_node_text = add_node_text
        
        logger.info(f"PageIndex服务初始化完成")
        logger.info(f"  - 主模型: {self.primary_model}")
        if self.fallback_models:
            logger.info(f"  - 备用模型: {', '.join(self.fallback_models)}")
            logger.info(f"  - 429限流自动降级: 已启用")
        else:
            logger.info(f"  - 429限流自动降级: 未启用")

    def parse_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        解析PDF文件，生成文档树结构（支持429限流自动降级）
        
        Args:
            pdf_path: PDF文件路径
            
        Returns:
            包含文档树的字典，格式：
            {
                "doc_name": "xxx.pdf",
                "structure": [TreeNode, ...],
                "doc_description": "..." (可选)
            }
        """
        logger.info(f"开始使用PageIndex解析PDF: {pdf_path}")
        
        # 验证文件存在
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")
        
        if not pdf_path.lower().endswith('.pdf'):
            raise ValueError("文件必须是PDF格式")
        
        # 尝试所有可用模型（主模型 + 备用模型）
        for attempt, model in enumerate(self.all_models):
            try:
                is_fallback = attempt > 0
                status = "备用模型" if is_fallback else "主模型"
                
                logger.info(f"尝试使用{status}: {model} (第{attempt + 1}/{len(self.all_models)}次)")
                logger.info(f"  - 目录检查页数: {self.toc_check_pages}")
                logger.info(f"  - 每节点最大页数: {self.max_pages_per_node}")
                
                # 调用PageIndex主函数
                result = page_index(
                    doc=pdf_path,
                    model=model,
                    toc_check_page_num=self.toc_check_pages,
                    max_page_num_each_node=self.max_pages_per_node,
                    max_token_num_each_node=self.max_tokens_per_node,
                    if_add_node_id="yes" if self.add_node_id else "no",
                    if_add_node_summary="yes" if self.add_node_summary else "no",
                    if_add_doc_description="yes" if self.add_doc_description else "no",
                    if_add_node_text="yes" if self.add_node_text else "no"
                )
                
                logger.info(f"PageIndex返回结果类型: {type(result)}")
                
                if not result:
                    raise ValueError("PageIndex返回结果为空")
                
                # 处理Unicode编码问题
                result = self._decode_unicode_recursively(result)
                print(result)
                
                structure_count = len(result.get('structure', []))
                logger.info(f"✓ PageIndex解析完成（使用{status}: {model}）")
                logger.info(f"  - 文档名称: {result.get('doc_name', '未知')}")
                logger.info(f"  - 结构节点数: {structure_count}")
                
                if structure_count == 0:
                    logger.warning("⚠️ PageIndex未解析出任何结构节点")
                
                # 成功，更新当前模型索引（下次从这个模型开始）
                if is_fallback:
                    self.current_model_index = attempt
                    logger.info(f"✓ 备用模型成功，切换到: {model}")
                
                return result
                
            except Exception as e:
                error_msg = str(e)
                is_rate_limit = "429" in error_msg or "rate" in error_msg.lower() or "limit" in error_msg.lower()
                
                if is_rate_limit:
                    logger.warning(f"⚠️ 模型 {model} 遇到429限流错误")
                    
                    # 如果还有备用模型，继续尝试
                    if attempt < len(self.all_models) - 1:
                        logger.info(f"→ 自动切换到下一个备用模型...")
                        continue
                    else:
                        # 所有模型都失败了
                        logger.error(f"❌ 所有模型（共{len(self.all_models)}个）都遇到429限流")
                        raise Exception(
                            f"所有配置的模型都遇到429限流错误。\n"
                            f"尝试过的模型: {', '.join(self.all_models)}\n"
                            f"建议：\n"
                            f"1. 稍后重试\n"
                            f"2. 检查API配额\n"
                            f"3. 添加更多备用模型"
                        )
                else:
                    # 非429错误，直接抛出
                    logger.error(f"PageIndex解析失败（模型: {model}）: {error_msg}")
                    logger.error(f"错误类型: {type(e).__name__}")
                    import traceback
                    logger.error(traceback.format_exc())
                    raise

    def _decode_unicode_recursively(self, obj: Any) -> Any:
        """
        递归处理Unicode编码，将\\uXXXX格式的字符串转换为真实的中文
        
        Args:
            obj: 任意Python对象（dict, list, str等）
            
        Returns:
            处理后的对象
        """
        if isinstance(obj, dict):
            return {key: self._decode_unicode_recursively(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._decode_unicode_recursively(item) for item in obj]
        elif isinstance(obj, str):
            # 处理\\uXXXX格式的Unicode字符串
            try:
                # 只处理包含\uXXXX格式的字符串
                if '\\u' in obj:
                    # 使用codecs.decode处理Unicode转义
                    import codecs
                    return codecs.decode(obj, 'unicode_escape')
                else:
                    # 如果没有Unicode转义，直接返回原字符串
                    return obj
            except Exception as e:
                logger.warning(f"Unicode解码失败: {e}, 返回原字符串")
                return obj
        else:
            return obj

    def flatten_tree_to_nodes(self, structure: List[Dict]) -> List[Dict]:
        """
        将树状结构扁平化为节点列表（便于后续并行处理）
        
        Args:
            structure: PageIndex生成的树状结构
            
        Returns:
            扁平化的节点列表
        """
        nodes = []
        
        def traverse(node_list: List[Dict], parent_path: str = ""):
            for node in node_list:
                # 构建节点路径（用于标识层级）
                current_path = f"{parent_path}/{node.get('title', 'Unknown')}" if parent_path else node.get('title', 'Unknown')
                
                # 添加当前节点
                flat_node = {
                    "node_id": node.get("node_id"),
                    "title": node.get("title"),
                    "start_index": node.get("start_index"),
                    "end_index": node.get("end_index"),
                    "summary": node.get("summary"),
                    "text": node.get("text"),  # 如果配置了add_node_text
                    "path": current_path,
                    "has_children": bool(node.get("nodes"))
                }
                nodes.append(flat_node)
                
                # 递归处理子节点
                if node.get("nodes"):
                    traverse(node["nodes"], current_path)
        
        traverse(structure)
        logger.info(f"树结构扁平化完成，共 {len(nodes)} 个节点")
        return nodes

    def get_leaf_nodes(self, structure: List[Dict]) -> List[Dict]:
        """
        获取所有叶子节点（没有子节点的节点）
        
        Args:
            structure: PageIndex生成的树状结构
            
        Returns:
            叶子节点列表
        """
        leaf_nodes = []
        
        def traverse(node_list: List[Dict], parent_path: str = ""):
            for node in node_list:
                current_path = f"{parent_path}/{node.get('title', 'Unknown')}" if parent_path else node.get('title', 'Unknown')
                
                if not node.get("nodes"):  # 叶子节点
                    leaf_node = {
                        "node_id": node.get("node_id"),
                        "title": node.get("title"),
                        "start_index": node.get("start_index"),
                        "end_index": node.get("end_index"),
                        "summary": node.get("summary"),
                        "text": node.get("text"),
                        "path": current_path
                    }
                    leaf_nodes.append(leaf_node)
                else:
                    # 递归处理子节点
                    traverse(node["nodes"], current_path)
        
        traverse(structure)
        logger.info(f"提取叶子节点完成，共 {len(leaf_nodes)} 个")
        return leaf_nodes


# 全局单例
_pageindex_service: Optional[PageIndexService] = None

def get_pageindex_service() -> PageIndexService:
    """
    获取PageIndex服务单例（支持429限流自动降级）
    """
    global _pageindex_service
    if _pageindex_service is None:
        from app.core.config import settings
        
        # 解析fallback_models（逗号分隔的字符串 → 列表）
        fallback_models = []
        if settings.fallback_models and settings.fallback_models.strip():
            fallback_models = [
                m.strip()
                for m in settings.fallback_models.split(',')
                if m.strip()
            ]
        
        _pageindex_service = PageIndexService(
            model=settings.structurizer_model,  # 主模型
            fallback_models=fallback_models,    # 备用模型列表
            toc_check_pages=20,
            max_pages_per_node=10,
            max_tokens_per_node=20000,
            add_node_id=True,
            add_node_summary=False,  # 禁用PageIndex的summary，改为从original_text生成
            add_doc_description=False,
            add_node_text=False  # 默认不添加，需要时再启用
        )
    return _pageindex_service
