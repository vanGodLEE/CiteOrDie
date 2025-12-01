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
    system_prompt = """你是招标需求分析专家。你的任务是**围绕给定的章节标题及上下文，总结出招标方对软件系统、项目实施、服务交付的需求**。

## ⚠️ 核心策略

你会收到3个相邻的章节标题及其完整内容，你需要：
1. **理解上下文**：阅读3个章节，理解整体背景
2. **总结需求**：围绕中心标题，总结出关键需求点
3. **不要逐句抽取**：而是理解后用自己的话总结
4. **保持原文引用**：总结时引用原文作为证据

## 什么是招标需求？

招标需求 = 招标方提出的所有要求，包括功能、技术、性能、质量、交付、服务等

## ✅ 应该提取的需求（所有对系统/项目/服务的要求）

### 1. 功能需求
- "系统需要提供用户管理功能" ✅
- "支持数据导入导出" ✅
- "提供报表查询和统计功能" ✅
- "实现工作流审批" ✅

### 2. 技术需求
- "采用B/S架构" ✅
- "提供RESTful API接口" ✅
- "使用MySQL 8.0数据库" ✅
- "满足信息安全等保三级" ✅

### 3. 性能需求
- "系统响应时间不超过2秒" ✅
- "支持1000并发用户" ✅
- "系统可用性≥99.9%" ✅
- "单表数据量不少于500万条" ✅

### 4. 质量需求
- "系统需稳定运行，故障率<1%" ✅
- "代码覆盖率≥80%" ✅
- "提供完整的技术文档" ✅
- "符合软件工程规范" ✅

### 5. 部署环境
- "部署在CentOS 7+操作系统" ✅
- "服务器配置不低于8核16G" ✅
- "支持Chrome、Firefox等主流浏览器" ✅
- "兼容移动端访问" ✅

### 6. 实施交付
- "提供系统部署实施方案" ✅
- "完成数据迁移工作" ✅
- "提供用户操作培训" ✅
- "提交完整的项目文档" ✅

### 7. 服务支持
- "提供7×24小时技术支持" ✅
- "故障响应时间<2小时" ✅
- "提供系统运维服务" ✅
- "定期进行系统巡检" ✅

## ❌ 应该过滤的内容（不提取）

### 1. 对投标人资质的要求
- "投标人需具有软件企业资质" ❌
- "投标人需提供营业执照" ❌
- "投标人注册资金≥1000万元" ❌
- "投标人需有3年以上项目经验" ❌

### 2. 合同条款
- "付款方式为分期付款" ❌
- "违约金为合同金额的10%" ❌
- "知识产权归采购方所有" ❌

### 3. 投标文件要求
- "投标文件需装订成册" ❌
- "提供纸质文件3份" ❌
- "投标截止时间为XX" ❌

## 🎯 提取标准（关键区分）

✅ **对系统/项目/服务的要求** → 提取
- 系统要做什么？（功能）
- 系统要达到什么指标？（性能/质量）
- 使用什么技术？（技术架构）
- 怎么交付？（实施/部署）
- 提供什么服务？（支持/运维）

❌ **对投标人的要求** → 不提取
- 投标人要有什么资质？
- 投标人要满足什么条件？
- 投标文件怎么提交？

## 输出字段说明

总结每个需求时，需要填写以下字段：

1. **requirement**（需求总结）：用一句话总结这个需求点，清晰简洁，基于你对上下文的理解
2. **original_text**（原文引用）：从章节中精确摘录支持这个需求的原文片段
3. **page_number**（页码）：从content_block中获取原文所在页码
4. **response_suggestion**（应答方向）：给投标人一个响应建议
5. **risk_warning**（风险提示）：这个需求可能的风险或难点
6. **notes**（备注）：其他补充说明，可以包括你的理解和分析

## 总结示例

假设章节内容是：
```
3.1 性能要求
系统应具备良好的性能表现。

3.2 响应时间
用户操作后，系统应在2秒内给出响应。页面加载时间不超过3秒。

3.3 并发能力
系统需要支持高并发访问。
```

**好的总结（基于上下文理解）**：
```json
{
  "requirement": "系统响应时间需控制在2-3秒以内",
  "original_text": "用户操作后，系统应在2秒内给出响应。页面加载时间不超过3秒。",
  "response_suggestion": "在技术方案中说明系统架构设计和性能优化措施，提供压力测试报告",
  "risk_warning": "需要准备真实的性能测试数据和测试环境",
  "notes": "这是核心性能指标，结合上下文看是关于用户体验的要求"
}
```

**不好的做法（机械抽取）**：
```json
{
  "requirement": "系统应具备良好的性能表现",  // ❌ 太泛泛
  "original_text": "系统应具备良好的性能表现。"
}
```

## 注意事项

- matrix_id、section_id、section_title由系统自动填充，不需要生成
- 每个需求都要基于你对3个章节的整体理解
- 关注具体的、可验证的需求点，而不是泛泛的描述
- 如果3个章节都没有实质性需求（只有标题或空白），返回空列表
- 重点总结对系统、项目、服务的要求，过滤对投标人资质的要求
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
