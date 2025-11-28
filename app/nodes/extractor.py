"""
Extractor节点 - 并行需求提取Worker

每个Worker负责分析一个章节，提取所有需求条款
这是系统的"人海战术"
"""

from typing import List
from pydantic import BaseModel
from loguru import logger

from app.core.states import SectionState, RequirementItem, ContentBlock, create_matrix_id
from app.services.llm_service import llm_service


# Pydantic模型用于Structured Output
class RequirementList(BaseModel):
    """需求列表"""
    requirements: List[RequirementItem]


def extractor_node(state: SectionState) -> dict:
    """
    Extractor节点 - 需求提取Worker
    
    业务逻辑：
    1. 接收一个章节的内容
    2. 使用LLM识别所有需求条款
    3. 对每个需求判断重要性级别（CRITICAL/SCORING/NORMAL）
    4. 提取原文作为证据
    5. 生成唯一的matrix_id
    
    Args:
        state: 章节状态（SectionState）
        
    Returns:
        包含需求列表的字典
    """
    section_id = state["section_id"]
    section_title = state["section_title"]
    content_blocks = state["content_blocks"]
    task_id = state.get("task_id")
    
    logger.info(f"====== Extractor开始处理章节: {section_id} {section_title} ======")
    
    # 更新进度：开始提取某个章节
    if task_id:
        from app.api.async_tasks import TaskManager
        TaskManager.update_task(task_id, progress=40, message=f"正在提取章节需求: {section_title[:30]}...")
    logger.debug(f"章节包含 {len(content_blocks)} 个内容块")
    
    # 将内容块转换为文本
    section_text = _format_content_blocks(content_blocks)
    logger.debug(f"章节文本长度: {len(section_text)} 字符")
    logger.debug(f"章节文本预览: {section_text[:200]}...")
    
    # 构造Prompt
    system_prompt = """你是技术需求分析专家。你的任务是从章节内容中提取**技术需求**（技术指标、参数、规格、标准）。

## ⚠️ 什么是技术需求？

技术需求 = 具体的、可量化的、可验证的技术指标、参数、规格、标准

**技术需求 vs 功能描述**：
- ✅ "响应时间不超过2秒" → 技术需求（可量化）
- ❌ "系统要快" → 不是技术需求（泛泛描述）
- ✅ "支持1000并发用户" → 技术需求（有指标）
- ❌ "需要用户管理功能" → 不是技术需求（功能描述）
- ✅ "使用MySQL 8.0数据库" → 技术需求（具体技术）
- ❌ "需要数据库" → 不是技术需求（太宽泛）

## ✅ 应该提取的内容（技术需求）

### 1. 性能指标类
- 响应时间、处理时间（"<2秒"、"平均响应时间<500ms"）
- 并发能力（"支持1000并发用户"、"TPS≥5000"）
- 吞吐量（"处理能力≥10万笔/天"）
- 可用性（"系统可用性≥99.9%"、"年停机时间<8.76小时"）

### 2. 技术规范类
- 技术架构（"采用微服务架构"、"B/S架构"、"前后端分离"）
- 接口规范（"提供RESTful API"、"支持SOAP协议"、"HTTP/HTTPS"）
- 安全标准（"满足等保三级"、"支持TLS 1.2+"、"AES-256加密"）
- 开发规范（"遵循阿里巴巴Java开发规范"、"代码覆盖率≥80%"）

### 3. 技术环境类
- 操作系统（"支持CentOS 7+"、"Windows Server 2019"）
- 数据库（"MySQL 8.0"、"Oracle 19c"、"Redis 6.0集群"）
- 中间件（"Nginx 1.18"、"Tomcat 9.0"）
- 服务器配置（"8核16G内存"、"带宽≥100Mbps"）
- 浏览器兼容（"支持Chrome 90+、Firefox 88+、IE11"）

### 4. 技术能力类
- 扩展性（"支持横向扩展"、"单表≤500万条记录需分库分表"）
- 容灾备份（"支持双机热备"、"数据实时同步"、"RPO<30分钟"）
- 集成能力（"支持对接XX系统"、"提供标准接口"）

## ❌ 应该过滤的内容（不提取）

### 1. 纯功能描述（无技术指标）
- "需要用户管理功能" → 没有技术要求
- "支持数据导入导出" → 太宽泛
- "提供报表功能" → 没有技术细节

### 2. 商务资质类
- 营业执照、企业资质、业绩证明、人员证书

### 3. 服务方案类
- 培训计划、售后服务、质保期限、运维承诺

### 4. 合同条款类
- 付款方式、违约责任、验收标准

## 🎯 提取标准

每提取一个需求，问自己：
1. ❓ 这个需求包含具体的技术指标或参数吗？
2. ❓ 这个需求可以量化验证吗？
3. ❓ 这个需求有明确的技术规范或标准吗？

如果答案是"是"，就提取；如果只是泛泛的功能描述，就过滤。

## 输出字段说明

提取每个需求后，需要填写以下字段：

1. **requirement**（需求）：用一句话概括技术需求，必须包含具体的指标或规范
2. **original_text**（原文）：从章节中精确摘录的原文，不要改写
3. **page_number**（页码）：从content_block中获取
4. **response_suggestion**（应答方向）：给投标人一个技术响应建议
5. **risk_warning**（风险提示）：这个技术需求可能的风险或难点
6. **notes**（备注）：其他技术补充说明

## 注意事项

- matrix_id、section_id、section_title由系统自动填充，不需要生成
- 如果整个章节没有技术需求（只有功能描述），返回空列表
- 不要合并多个需求，每个需求单独一条
- 不要提取泛泛的功能描述，要有具体的技术细节
"""
    
    user_prompt = f"""请分析以下章节内容，提取所有需求条款：

章节：{section_id} {section_title}

内容：
{section_text}

请按照规则提取需求，每个需求必须包含完整的字段信息。
注意：matrix_id字段请留空，将由系统自动生成。
"""
    
    # 调用LLM进行结构化输出
    try:
        result = llm_service.structured_completion(
            messages=[
                llm_service.create_system_message(system_prompt),
                llm_service.create_user_message(user_prompt)
            ],
            response_model=RequirementList,
            temperature=0.1
        )
        
        requirements = result.requirements
        
        # 后处理：生成matrix_id
        for i, req in enumerate(requirements, start=1):
            if not req.matrix_id or req.matrix_id == "":
                req.matrix_id = create_matrix_id(section_id, i)
        
        logger.info(f"章节 {section_id} 提取到 {len(requirements)} 条需求")
        
        # 显示前3个需求预览
        for i, req in enumerate(requirements[:3]):
            logger.debug(f"  需求{i+1}: {req.requirement[:60]}...")
        
        # 返回结果（会被LangGraph追加到全局state的requirements中）
        return {"requirements": requirements}
        
    except Exception as e:
        logger.error(f"Extractor处理章节 {section_id} 失败: {e}")
        # 返回空列表而不是抛出异常，避免影响其他Worker
        return {"requirements": []}


def _format_content_blocks(content_blocks: List[ContentBlock]) -> str:
    """
    将内容块格式化为LLM易读的文本
    
    包含页码信息，便于后续溯源
    """
    lines = []
    
    for block in content_blocks:
        page_num = block.page_idx + 1
        
        if block.type == "header":
            lines.append(f"\n### {block.text} (第{page_num}页)")
        elif block.type == "text":
            lines.append(f"{block.text} (第{page_num}页)")
        elif block.type == "table":
            lines.append(f"\n表格 (第{page_num}页):\n{block.text}\n")
        elif block.type == "image":
            lines.append(f"[图片] (第{page_num}页)")
        
        lines.append("")  # 空行
    
    return "\n".join(lines)
