# Original_Text为空的问题诊断与修复

## 问题描述

用户下载的需求树JSON文件中，所有`original_text`字段都是空字符串`""`，导致enricher节点无法基于精确原文提取需求。

## 问题诊断

### 可能原因

1. **text_filler节点未执行**
   - Graph工作流配置错误
   - 节点之间的边连接问题

2. **text_filler执行但LLM返回空内容**
   - LLM提取失败，返回"无内容"等特殊值被转换为空字符串
   - PDF文本提取失败
   - prompt不够清晰

3. **序列化问题**
   - PageIndexNode的original_text默认值为None
   - JSON序列化时None被转换为空字符串

## 已实施的修复

### 1. 增强日志记录（text_filler.py）

在`fill_text_recursively`函数中添加了详细的日志：

```python
logger.info(f"节点 '{node.title}': 提取PDF文本，页面 [{start_page}, {end_page}]，文本长度: {len(page_text)}")

logger.info(f"节点 '{node.title}': LLM返回原文长度: {len(original_text) if original_text else 0}")

if not original_text:
    logger.warning(f"节点 '{node.title}': LLM返回空原文！")
```

这些日志会帮助我们：
- 确认text_filler是否执行
- 查看PDF文本是否成功提取
- 检查LLM是否返回了空内容

### 2. 确保一致性处理

```python
# 填充到节点（即使为空也填充，保持一致性）
node.original_text = original_text if original_text else ""
```

## 下一步诊断步骤

### 查看日志

1. 重新运行分析任务
2. 查看后台日志，搜索关键词：
   - `"Text Filler节点开始执行"`
   - `"节点 'XXX': 提取PDF文本"`
   - `"LLM返回原文长度"`
   - `"LLM返回空原文"`

### 根据日志结果判断

#### 情况1：没有找到"Text Filler节点开始执行"
**问题**：text_filler节点根本没有执行
**解决方案**：检查graph.py中的工作流连接

#### 情况2：找到"提取PDF文本，文本长度: 0"
**问题**：PDF文本提取失败
**解决方案**：检查pdf_text_extractor.py和PDF文件是否损坏

#### 情况3：找到"LLM返回空原文"警告
**问题**：LLM提取失败
**解决方案**：
- 检查LLM是否正常工作
- 优化prompt（build_text_extraction_prompt）
- 检查LLM是否返回"无内容"等特殊值

## 临时验证方案

如果需要快速验证text_filler是否工作，可以：

1. 在text_filler_node函数开始处添加：
```python
logger.critical("=" * 80)
logger.critical("TEXT_FILLER正在执行！")
logger.critical("=" * 80)
```

2. 运行后检查日志是否有这个醒目的标记

## 长期解决方案

### 方案A：降级策略

如果LLM提取总是失败，可以直接使用PDF文本作为original_text：

```python
# 在extract_original_text_with_llm失败时
if not original_text:
    logger.warning("LLM提取失败，使用完整PDF文本作为降级")
    original_text = page_text[:2000]  # 限制长度
```

### 方案B：增强Prompt

修改`build_text_extraction_prompt`，使其更明确：

```python
## 输出要求

**重要**：请务必输出该标题下的所有内容，即使内容很短。

- 如果找不到该标题，返回"TITLE_NOT_FOUND"
- 如果标题后无内容，返回"NO_CONTENT"
- 否则，输出精确摘录的原文内容（不要省略任何内容）
```

然后在代码中检测这些特殊标记。

### 方案C：禁用LLM提取（最快）

在pageindex_service中启用`add_node_text=True`：

```python
_pageindex_service = PageIndexService(
    model=settings.structurizer_model,
    add_node_text=True  # ← 让PageIndex直接提供文本
)
```

然后在text_filler中直接使用：

```python
# 如果PageIndex已经提供了text字段
if node.text:
    node.original_text = node.text
    logger.info(f"使用PageIndex提供的text字段，长度: {len(node.text)}")
else:
    # 降级到LLM提取
    ...
```

## 推荐行动计划

1. **立即**：重新运行一次分析，查看增强日志的输出
2. **根据日志**：确定是哪个环节出问题
3. **如果是LLM问题**：先尝试方案C（最快），直接使用PageIndex的text字段
4. **如果是PDF提取问题**：检查pymupdf库是否正常工作

## 相关文件

- `app/nodes/text_filler.py` - 原文填充节点
- `app/services/pdf_text_extractor.py` - PDF文本提取
- `app/services/pageindex_service.py` - PageIndex服务配置
- `app/core/graph.py` - 工作流定义

## 测试命令

```bash
# 查看后台日志（如果使用uvicorn运行）
# Windows PowerShell
Get-Content -Path "logs/app.log" -Tail 100 -Wait

# 或直接查看控制台输出
```
