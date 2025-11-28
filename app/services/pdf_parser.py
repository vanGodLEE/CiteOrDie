"""
PDF解析服务

负责调用MinerU解析PDF文档，提取结构化内容
支持Mock模式用于开发和测试
"""

import json
import subprocess
import uuid
from pathlib import Path
from typing import List, Dict, Any
from loguru import logger

from app.core.states import ContentBlock, TOCItem, ParsedDocument
from app.core.config import settings


class PDFParserService:
    """PDF解析服务"""
    
    def __init__(self):
        self.mock_data_path = Path("tests/mock_data/sample_tender.json")
    
    def parse_pdf(self, pdf_path: str, use_mock: bool = False) -> ParsedDocument:
        """
        解析PDF文档
        
        Args:
            pdf_path: PDF文件路径
            use_mock: 是否使用Mock数据（开发阶段）
            
        Returns:
            ParsedDocument对象，包含content_list、markdown、toc
        """
        if use_mock:
            logger.info("使用Mock数据进行开发测试")
            return self._parse_mock()
        else:
            logger.info(f"调用MinerU解析PDF: {pdf_path}")
            return self._parse_real(pdf_path)
    
    def _parse_mock(self) -> ParsedDocument:
        """使用Mock数据"""
        try:
            with open(self.mock_data_path, "r", encoding="utf-8") as f:
                content_list_raw = json.load(f)
            
            # 转换为ContentBlock对象
            content_blocks = [
                ContentBlock(**block) for block in content_list_raw
            ]
            
            # 提取TOC
            toc = self.extract_toc(content_blocks)
            
            # 生成简单的markdown（实际MinerU会生成更完整的）
            markdown = self._generate_markdown_from_blocks(content_blocks)
            
            logger.info(f"Mock数据加载成功: {len(content_blocks)}个内容块, {len(toc)}个目录项")
            
            return ParsedDocument(
                content_list=content_blocks,
                markdown=markdown,
                toc=toc
            )
        except Exception as e:
            logger.error(f"加载Mock数据失败: {e}")
            raise
    
    def _parse_real(self, pdf_path: str) -> ParsedDocument:
        """
        调用真实的MinerU解析PDF
        
        使用subprocess调用magic-pdf命令
        """
        try:
            # 创建输出目录
            output_dir = Path(settings.mineru_output_dir) / uuid.uuid4().hex[:8]
            output_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"开始调用MinerU解析PDF: {pdf_path}")
            logger.info(f"输出目录: {output_dir}")
            
            # 调用MinerU命令行（正确的命令是mineru，不是magic-pdf）
            command = [
                "mineru",  # 固定使用mineru命令
                "-p", pdf_path,
                "-o", str(output_dir),
                "--source", "modelscope"
            ]
            logger.info(f"执行命令: {' '.join(command)}")
            
            # 将输出重定向到文件，避免缓冲区阻塞
            log_file = output_dir / "mineru_output.log"
            error_file = output_dir / "mineru_error.log"
            
            with open(log_file, "w", encoding="utf-8") as stdout_f, \
                 open(error_file, "w", encoding="utf-8") as stderr_f:
                
                result = subprocess.run(
                    command,
                    stdout=stdout_f,  # 重定向到文件，不阻塞
                    stderr=stderr_f,  # 错误也写入文件
                    text=True,
                    timeout=1800  # 30分钟超时
                )
            
            # 读取错误日志（如果有）
            if error_file.exists():
                with open(error_file, "r", encoding="utf-8", errors="ignore") as f:
                    error_content = f.read()
                    if error_content.strip():
                        logger.warning(f"MinerU stderr:\n{error_content[:500]}")  # 只显示前500字符
            
            if result.returncode != 0:
                logger.error(f"MinerU执行失败，返回码: {result.returncode}")
                # 读取完整错误信息
                error_msg = "MinerU执行失败"
                if error_file.exists():
                    with open(error_file, "r", encoding="utf-8", errors="ignore") as f:
                        error_msg = f.read()
                raise RuntimeError(f"MinerU解析失败: {error_msg}")
            
            logger.info("MinerU解析完成，开始读取结果")
            
            # 调试：列出输出目录的所有文件
            logger.info(f"输出目录内容：")
            if output_dir.exists():
                for item in output_dir.rglob("*"):
                    if item.is_file():
                        logger.info(f"  - {item.relative_to(output_dir)}")
            
            # 读取MinerU输出
            # MinerU的输出结构：output_dir/pdf_name/auto/xxx_content_list.json
            pdf_name = Path(pdf_path).stem
            
            # MinerU实际输出路径（根据用户提供的日志）
            auto_dir = output_dir / pdf_name / "auto"
            
            logger.info(f"预期的auto目录: {auto_dir}")
            
            # 递归查找content_list.json文件（MinerU的输出可能在不同位置）
            content_list_files = list(output_dir.rglob("*_content_list.json"))
            
            if not content_list_files:
                raise FileNotFoundError(
                    f"找不到MinerU输出文件。\n"
                    f"预期路径：{auto_dir}\n"
                    f"输出目录内容：{list(output_dir.rglob('*'))}\n"
                    f"请检查MinerU是否正确执行"
                )
            
            content_list_path = content_list_files[0]
            logger.info(f"找到content_list文件: {content_list_path}")
            
            # 查找对应的markdown文件
            markdown_path = content_list_path.parent / f"{pdf_name}.md"
            if not markdown_path.exists():
                # 尝试其他可能的名称
                md_files = list(content_list_path.parent.glob("*.md"))
                markdown_path = md_files[0] if md_files else None
            
            # 读取content_list
            with open(content_list_path, "r", encoding="utf-8", errors="ignore") as f:
                content_list_raw = json.load(f)
            
            content_blocks = [ContentBlock(**block) for block in content_list_raw]
            
            # 读取markdown
            markdown = ""
            if markdown_path and markdown_path.exists():
                with open(markdown_path, "r", encoding="utf-8", errors="ignore") as f:
                    markdown = f.read()
            else:
                logger.warning(f"未找到Markdown文件，跳过")
            
            # 提取TOC
            toc = self.extract_toc(content_blocks)
            
            logger.info(f"MinerU结果加载成功: {len(content_blocks)}个内容块, {len(toc)}个目录项")
            
            return ParsedDocument(
                content_list=content_blocks,
                markdown=markdown,
                toc=toc
            )
            
        except subprocess.TimeoutExpired:
            logger.error("MinerU解析超时")
            raise RuntimeError("PDF解析超时（>10分钟）")
        except Exception as e:
            logger.error(f"MinerU解析过程出错: {e}")
            raise
    
    def extract_toc(self, content_blocks: List[ContentBlock]) -> List[TOCItem]:
        """
        从content_list中提取目录结构
        
        逻辑：
        1. 找到所有type='header'的块
        2. 根据文本内容判断是否为章节标题（包含"章"或"节"）
        3. 根据文本格式推断层级（如"第X章"是1级，"X.X"是2级）
        
        Args:
            content_blocks: 内容块列表
            
        Returns:
            TOC项列表
        """
        toc_items = []
        
        for block in content_blocks:
            if block.type != "header":
                continue
            
            text = block.text.strip()
            
            # 过滤掉非章节标题（如文档标题、附件等）
            if not self._is_section_header(text):
                continue
            
            # 提取章节编号和标题
            section_id, title, level = self._parse_header(text)
            
            if section_id:
                toc_items.append(TOCItem(
                    section_id=section_id,
                    title=title,
                    page_number=block.page_idx + 1,  # 转换为1-based页码
                    level=level
                ))
        
        logger.debug(f"提取到 {len(toc_items)} 个目录项")
        return toc_items
    
    def _is_section_header(self, text: str) -> bool:
        """判断是否为章节标题"""
        # 包含"章"或以数字开头的标题（如"3.1"）
        keywords = ["章", "节", "第"]
        if any(kw in text for kw in keywords):
            return True
        
        # 检查是否以"数字."开头（如"3.1 系统架构"）
        import re
        if re.match(r'^\d+(\.\d+)*\s+', text):
            return True
        
        return False
    
    def _parse_header(self, text: str) -> tuple[str, str, int]:
        """
        解析标题，提取章节编号、标题和层级
        
        Returns:
            (section_id, title, level)
        """
        import re
        
        # 模式1: "第X章 标题"
        match = re.match(r'^第([一二三四五六七八九十\d]+)章\s+(.+)$', text)
        if match:
            chapter_num = match.group(1)
            title = match.group(2)
            # 转换中文数字为阿拉伯数字（简单处理）
            chinese_nums = {'一': '1', '二': '2', '三': '3', '四': '4', '五': '5'}
            section_id = chinese_nums.get(chapter_num, chapter_num)
            return section_id, title, 1
        
        # 模式2: "X.Y 标题" 或 "X.Y.Z 标题"
        match = re.match(r'^(\d+(?:\.\d+)*)\s+(.+)$', text)
        if match:
            section_id = match.group(1)
            title = match.group(2)
            level = section_id.count('.') + 1
            return section_id, title, level
        
        # 无法解析，返回原文
        return "", text, 1
    
    def _generate_markdown_from_blocks(self, content_blocks: List[ContentBlock]) -> str:
        """
        从内容块生成简单的Markdown
        
        注意：这是简化版本，真实MinerU会生成更完整的Markdown
        """
        lines = []
        
        for block in content_blocks:
            if block.type == "header":
                # 根据文本判断标题级别
                if "第" in block.text and "章" in block.text:
                    lines.append(f"# {block.text}")
                elif block.text[0].isdigit():
                    level = block.text.count('.') + 2  # 二级标题开始
                    lines.append(f"{'#' * level} {block.text}")
                else:
                    lines.append(f"## {block.text}")
            elif block.type == "text":
                lines.append(f"{block.text}")
            elif block.type == "table":
                lines.append(f"\n{block.text}\n")
            elif block.type == "image":
                lines.append(f"![图片](image_{block.page_idx}.png)")
            
            lines.append("")  # 空行
        
        return "\n".join(lines)
    
    def get_section_content(
        self,
        content_blocks: List[ContentBlock],
        section_plan
    ) -> List[ContentBlock]:
        """
        获取指定章节的内容块
        
        新逻辑（基于标题索引）：
        从start_index开始，收集所有内容块，直到遇到下一个text_level=1的标题
        
        Args:
            content_blocks: 所有内容块
            section_plan: SectionPlan对象（包含start_index）
            
        Returns:
            该章节的内容块列表
        """
        start_index = section_plan.start_index
        
        if start_index is None:
            # 降级：如果没有start_index，使用旧逻辑
            logger.warning(f"章节 {section_plan.section_id} 没有start_index，使用页码范围提取")
            result = []
            for block in content_blocks:
                page_num = block.page_idx + 1
                if page_num < section_plan.start_page:
                    continue
                if section_plan.end_page and page_num > section_plan.end_page:
                    break
                result.append(block)
            return result
        
        # 新逻辑：从start_index开始，收集到下一个标题
        result = []
        for i in range(start_index, len(content_blocks)):
            block = content_blocks[i]
            
            # 如果是标题且不是起始标题，停止
            # 使用getattr安全访问text_level字段
            text_level = getattr(block, 'text_level', None)
            if i > start_index and text_level == 1:
                break
            
            result.append(block)
        
        logger.debug(f"章节 {section_plan.section_id} ({section_plan.title}) 提取到 {len(result)} 个内容块")
        return result
