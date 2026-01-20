"""
异步PDF解析服务

支持进度回调，可以在MinerU解析过程中实时更新进度
"""

import asyncio
import json
from pathlib import Path
from typing import Callable, Optional
from loguru import logger

from app.core.states import ContentBlock, TOCItem, ParsedDocument
from app.core.config import settings


class AsyncPDFParser:
    """异步PDF解析器"""
    
    async def parse_pdf_with_progress(
        self,
        pdf_path: str,
        output_dir: Path,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> ParsedDocument:
        """
        异步解析PDF，支持进度回调
        
        Args:
            pdf_path: PDF文件路径
            output_dir: 输出目录
            progress_callback: 进度回调函数 callback(progress: float, message: str)
            
        Returns:
            ParsedDocument对象
        """
        try:
            # 构建命令
            command = ["mineru", "-p", pdf_path, "-o", str(output_dir)]
            logger.info(f"执行命令: {' '.join(command)}")
            
            if progress_callback:
                progress_callback(10, "正在启动MinerU...")
            
            # 使用asyncio.create_subprocess_exec执行命令
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # 异步读取输出并更新进度
            stdout_lines = []
            stderr_lines = []
            
            async def read_stream(stream, lines_list, is_stderr=False):
                """异步读取流输出"""
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    
                    decoded = line.decode('utf-8', errors='ignore').strip()
                    lines_list.append(decoded)
                    
                    if progress_callback and not is_stderr:
                        # 根据输出判断进度
                        progress = self._estimate_progress(decoded)
                        if progress > 0:
                            progress_callback(progress, decoded[:100])
                    
                    logger.debug(f"MinerU: {decoded}")
            
            # 同时读取stdout和stderr
            await asyncio.gather(
                read_stream(process.stdout, stdout_lines, False),
                read_stream(process.stderr, stderr_lines, True)
            )
            
            # 等待进程完成
            returncode = await process.wait()
            
            if returncode != 0:
                error_msg = '\n'.join(stderr_lines[-10:])  # 最后10行错误
                logger.error(f"MinerU执行失败，返回码: {returncode}")
                logger.error(f"错误信息: {error_msg}")
                raise RuntimeError(f"MinerU解析失败: {error_msg}")
            
            if progress_callback:
                progress_callback(50, "MinerU解析完成，正在读取结果...")
            
            # 读取输出文件
            result = await self._read_mineru_output(pdf_path, output_dir)
            
            if progress_callback:
                progress_callback(60, "结果读取完成")
            
            return result
            
        except asyncio.TimeoutError:
            logger.error("MinerU解析超时")
            raise RuntimeError("PDF解析超时（>30分钟）")
        except Exception as e:
            logger.error(f"异步PDF解析失败: {e}")
            raise
    
    def _estimate_progress(self, line: str) -> float:
        """
        根据MinerU输出估算进度
        
        基于用户提供的日志，MinerU的执行阶段：
        - Layout Predict: 15-20%
        - MFD Predict: 20-30%
        - MFR Predict: 30-40%
        - Table OCR: 40-45%
        - OCR: 45-50%
        """
        line_lower = line.lower()
        
        if 'layout predict' in line_lower:
            if '100%' in line:
                return 20
            return 15
        elif 'mfd predict' in line_lower:
            if '100%' in line:
                return 30
            return 25
        elif 'mfr predict' in line_lower:
            if '100%' in line:
                return 40
            return 35
        elif 'table' in line_lower and 'ocr' in line_lower:
            return 43
        elif 'ocr' in line_lower and 'predict' in line_lower:
            if '100%' in line:
                return 50
            return 48
        
        return 0
    
    async def _read_mineru_output(
        self,
        pdf_path: str,
        output_dir: Path
    ) -> ParsedDocument:
        """读取MinerU输出文件"""
        from app.services.pdf_parser import PDFParserService
        
        pdf_name = Path(pdf_path).stem
        
        # MinerU的输出结构：output_dir/pdf_name/auto/xxx_content_list.json
        auto_dir = output_dir / pdf_name / "auto"
        
        logger.info(f"预期的auto目录: {auto_dir}")
        
        if not auto_dir.exists():
            logger.warning(f"auto目录不存在，尝试递归查找...")
            # 递归查找content_list.json文件
            content_list_files = list(output_dir.rglob("*_content_list.json"))
            if content_list_files:
                content_list_path = content_list_files[0]
                logger.info(f"找到content_list文件: {content_list_path}")
            else:
                raise FileNotFoundError(
                    f"找不到MinerU输出文件。\n"
                    f"预期路径：{auto_dir}\n"
                    f"请检查MinerU是否正确执行"
                )
        else:
            # 在auto目录下查找content_list.json
            content_list_files = list(auto_dir.glob("*_content_list.json"))
            if not content_list_files:
                raise FileNotFoundError(
                    f"在auto目录找不到content_list.json\n"
                    f"auto目录: {auto_dir}\n"
                    f"目录内容: {list(auto_dir.glob('*'))}"
                )
            content_list_path = content_list_files[0]
            logger.info(f"找到content_list文件: {content_list_path}")
        
        # 读取content_list
        with open(content_list_path, "r", encoding="utf-8") as f:
            content_list_raw = json.load(f)
        
        content_blocks = [ContentBlock(**block) for block in content_list_raw]
        
        # 读取markdown
        markdown_path = content_list_path.parent / f"{pdf_name}.md"
        markdown = ""
        if markdown_path and markdown_path.exists():
            with open(markdown_path, "r", encoding="utf-8") as f:
                markdown = f.read()
        
        # 提取TOC
        parser = PDFParserService()
        toc = parser.extract_toc(content_blocks)
        
        logger.info(f"MinerU结果加载成功: {len(content_blocks)}个内容块, {len(toc)}个目录项")
        
        return ParsedDocument(
            content_list=content_blocks,
            markdown=markdown,
            toc=toc
        )

