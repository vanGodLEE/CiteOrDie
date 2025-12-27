# LangGraph节点级多模型配置指南

## 概述

TenderAnalysis系统支持为每个LangGraph节点配置独立的LLM模型，实现**精细化的模型选择**，根据不同任务特点选择最合适的模型。

### 核心优势

1. **成本优化**：对简单任务使用便宜模型，复杂任务使用高级模型
2. **性能优化**：根据任务特点选择最合适的模型能力
3. **灵活性**：可以混合使用不同提供商的模型
4. **可维护性**：统一的配置管理，易于调整和优化

## 工作流架构

### LangGraph节点拓扑

```
START 
  ↓
[pageindex_parser] ← structurizer_model (文档解析)
  ↓
[text_filler] ← text_filler_model (原文摘抄) ←┐
  ↓                                          ├─ 并行执行
[text_filler] ← text_filler_model           │
  ↓                                          │
[text_filler] ← text_filler_model          ┘
  ↓
[aggregator] (不使用LLM)
  ↓
[enricher] ← extractor_model (需求提取) ←┐
  ↓                                      ├─ 并行执行
[enricher] ← extractor_model            │
  ↓                                      │
[enricher] ← extractor_model           ┘
  ↓
[auditor] ← auditor_model (目前不使用LLM)
  ↓
END
```

### 节点说明

| 节点 | 配置项 | 功能 | 模型要求 | 推荐模型 |
|------|--------|------|----------|----------|
| **pageindex_parser** | `STRUCTURIZER_MODEL` | 解析PDF文档结构，生成章节树 | 强推理能力 | deepseek-reasoner, gpt-4o |
| **text_filler** | `TEXT_FILLER_MODEL` | 从PDF中精确摘抄原文 | 强遵循指令能力，避免幻觉 | deepseek-chat, gpt-4o-mini |
| **summary** | `SUMMARY_MODEL` | 基于原文生成节点摘要 | 文本理解和生成 | deepseek-chat, gpt-4o-mini |
| **enricher** | `EXTRACTOR_MODEL` | 从章节中提取招标需求 | 理解能力，结构化输出 | deepseek-chat, gpt-4o |
| **auditor** | `AUDITOR_MODEL` | 汇总所有需求（目前不使用LLM） | - | 任意 |

## 配置方式

### 1. 基础配置文件

在`.env`文件中配置：

```bash
# ==================== LLM提供商配置 ====================
LLM_PROVIDER=deepseek

# DeepSeek配置
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

# OpenAI配置（可选）
OPENAI_API_KEY=sk-xxx
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o

# ==================== 节点级模型配置 ====================
# 格式：provider:model 或 model（使用默认provider）

# 文档解析（推理能力要求高）
STRUCTURIZER_MODEL=deepseek:deepseek-reasoner

# 原文摘抄（精确性要求高）
TEXT_FILLER_MODEL=deepseek:deepseek-chat

# 摘要生成（平衡性能和成本）
SUMMARY_MODEL=deepseek:deepseek-chat

# 需求提取（理解能力要求高）
EXTRACTOR_MODEL=deepseek:deepseek-chat

# 汇总节点（目前不使用）
AUDITOR_MODEL=deepseek:deepseek-chat
```

### 2. 模型格式

支持两种格式：

#### 格式A：完整格式（推荐）
```bash
STRUCTURIZER_MODEL=deepseek:deepseek-reasoner
TEXT_FILLER_MODEL=openai:gpt-4o-mini
```

- 明确指定provider和model
- 可以混合使用不同提供商
- 便于理解和维护

#### 格式B：简写格式
```bash
STRUCTURIZER_MODEL=deepseek-chat
```

- 只写模型名，使用`LLM_PROVIDER`指定的默认提供商
- 适合单一提供商的场景

## 配置策略

### 策略1：成本优先（推荐用于开发）

```bash
# 所有节点都使用便宜的DeepSeek
STRUCTURIZER_MODEL=deepseek:deepseek-chat
TEXT_FILLER_MODEL=deepseek:deepseek-chat
SUMMARY_MODEL=deepseek:deepseek-chat
EXTRACTOR_MODEL=deepseek:deepseek-chat
```

**优点**：成本最低  
**缺点**：某些复杂文档可能解析效果不理想

### 策略2：性能优先（推荐用于生产）

```bash
# 复杂任务使用高级模型
STRUCTURIZER_MODEL=openai:gpt-4o           # 文档解析需要强推理
TEXT_FILLER_MODEL=deepseek:deepseek-chat   # 摘抄任务相对简单
SUMMARY_MODEL=deepseek:deepseek-chat       # 摘要生成一般即可
EXTRACTOR_MODEL=openai:gpt-4o              # 需求提取需要强理解
```

**优点**：效果最好  
**缺点**：成本较高

### 策略3：混合模式（推荐用于生产，平衡成本和效果）

```bash
# 关键节点用强模型，其他节点用经济模型
STRUCTURIZER_MODEL=deepseek:deepseek-reasoner  # DeepSeek推理模型
TEXT_FILLER_MODEL=deepseek:deepseek-chat       # 简单摘抄任务
SUMMARY_MODEL=deepseek:deepseek-chat           # 摘要生成
EXTRACTOR_MODEL=openai:gpt-4o-mini             # 需求提取用OpenAI
```

**优点**：平衡成本和效果  
**推荐**：这是生产环境的最佳实践

### 策略4：使用阿里云通义千问（中国大陆推荐）

```bash
# 使用阿里云通义千问（兼容OpenAI格式）
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
DEEPSEEK_MODEL=qwen-plus-latest

STRUCTURIZER_MODEL=qwen-plus-latest
TEXT_FILLER_MODEL=qwen-plus-latest
SUMMARY_MODEL=qwen-turbo-latest          # 使用更快的Turbo版本
EXTRACTOR_MODEL=qwen-plus-latest
```

**优点**：
- 国内访问速度快
- 支持多种模型（qwen-plus, qwen-turbo, qwen-max等）
- 兼容OpenAI API格式

## 实现细节

### 代码架构

#### 1. 配置层 ([`app/core/config.py`](app/core/config.py:47-70))

```python
class Settings(BaseSettings):
    # 节点级模型配置
    structurizer_model: str = Field(
        default="deepseek:deepseek-chat",
        description="PageIndex文档解析节点使用的模型"
    )
    
    text_filler_model: str = Field(
        default="deepseek:deepseek-chat",
        description="Text Filler节点使用的模型"
    )
    
    # ... 其他节点配置
```

#### 2. LLM服务层 ([`app/services/llm_service.py`](app/services/llm_service.py:64-166))

支持动态模型选择：

```python
def structured_completion(
    self,
    messages: List[dict],
    response_model: Type[T],
    model: Optional[str] = None  # 可以指定model
) -> T:
    # 解析 provider:model 格式
    if model:
        if ":" in model:
            model_provider, model_name = model.split(":", 1)
        else:
            model_provider = self.provider
            model_name = model
    
    # 使用解析后的模型
    response = self.client.beta.chat.completions.parse(
        model=model_name,
        ...
    )
```

#### 3. 节点层

各节点调用LLM时传入配置的模型：

```python
# text_filler.py
llm_service.text_completion(
    messages=messages,
    model=settings.text_filler_model,  # 使用配置的模型
    temperature=0
)

# pageindex_enricher.py
llm_service.structured_completion(
    messages=messages,
    response_model=RequirementList,
    model=settings.extractor_model,  # 使用配置的模型
    temperature=0.1
)
```

### 模型解析流程

```
配置文件(.env)
    ↓
STRUCTURIZER_MODEL=deepseek:deepseek-reasoner
    ↓
Settings.structurizer_model (Pydantic)
    ↓
llm_service.structured_completion(model=settings.structurizer_model)
    ↓
解析: provider="deepseek", model="deepseek-reasoner"
    ↓
选择对应的client和调用API
```

## 最佳实践

### 1. 开发环境配置

```bash
# 开发环境：全部使用DeepSeek，成本低
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_API_BASE=https://api.deepseek.com/v1

STRUCTURIZER_MODEL=deepseek-chat
TEXT_FILLER_MODEL=deepseek-chat
SUMMARY_MODEL=deepseek-chat
EXTRACTOR_MODEL=deepseek-chat
```

### 2. 生产环境配置

```bash
# 生产环境：混合模式，平衡成本和效果
LLM_PROVIDER=deepseek

# DeepSeek配置
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_API_BASE=https://api.deepseek.com/v1

# OpenAI配置
OPENAI_API_KEY=sk-xxx
OPENAI_API_BASE=https://api.openai.com/v1

# 关键节点使用强模型
STRUCTURIZER_MODEL=deepseek:deepseek-reasoner  # 或 openai:gpt-4o
TEXT_FILLER_MODEL=deepseek:deepseek-chat
SUMMARY_MODEL=deepseek:deepseek-chat
EXTRACTOR_MODEL=openai:gpt-4o-mini             # 或 deepseek:deepseek-chat
```

### 3. 模型选择建议

#### PageIndex文档解析 (structurizer_model)
- **推荐**：`deepseek:deepseek-reasoner` 或 `openai:gpt-4o`
- **原因**：需要理解复杂的文档结构，提取章节层级
- **备选**：`qwen-plus-latest` (阿里云)

#### 原文摘抄 (text_filler_model)
- **推荐**：`deepseek:deepseek-chat` 或 `openai:gpt-4o-mini`
- **原因**：需要精确遵循指令，避免幻觉，temperature=0
- **关键**：模型必须有强的指令遵循能力

#### 摘要生成 (summary_model)
- **推荐**：`deepseek:deepseek-chat` 或 `qwen-turbo-latest`
- **原因**：相对简单的文本生成任务
- **可选**：使用更便宜的模型降低成本

#### 需求提取 (extractor_model)
- **推荐**：`deepseek:deepseek-chat` 或 `openai:gpt-4o`
- **原因**：需要深入理解招标需求，结构化输出
- **关键**：模型必须支持Structured Output或JSON mode

## 监控和调试

### 1. 查看日志

每次LLM调用都会记录使用的模型：

```
[INFO] LLM调用配置: provider=deepseek, model=deepseek-chat
[INFO] LLM调用成功 - Token使用: 输入=1234, 输出=567, 总计=1801
```

### 2. 性能对比

建议记录不同模型配置的效果：

| 配置 | 成功率 | 平均耗时 | 成本 | 备注 |
|------|--------|----------|------|------|
| 全DeepSeek | 85% | 15s | ¥0.5 | 开发环境 |
| 混合模式 | 95% | 18s | ¥1.2 | 推荐生产 |
| 全GPT-4o | 98% | 20s | ¥3.5 | 高要求场景 |

### 3. 常见问题

#### Q1: 模型配置不生效？
**A**: 检查环境变量是否正确加载：
```python
from app.core.config import settings
print(settings.text_filler_model)  # 应输出配置的模型
```

#### Q2: 混合使用不同provider时报错？
**A**: 确保两个provider的API key都已配置：
```bash
DEEPSEEK_API_KEY=sk-xxx
OPENAI_API_KEY=sk-xxx
```

#### Q3: 某个节点效果不好？
**A**: 尝试更换该节点的模型：
```bash
# 原配置
EXTRACTOR_MODEL=deepseek:deepseek-chat

# 更换为更强的模型
EXTRACTOR_MODEL=openai:gpt-4o
```

## 扩展支持

### 添加新的Provider

如需支持新的LLM提供商（如Claude、Gemini等），需要：

1. 在 [`app/core/config.py`](app/core/config.py) 添加配置
2. 在 [`app/services/llm_service.py`](app/services/llm_service.py) 添加client初始化
3. 更新模型解析逻辑

示例：添加Claude支持

```python
# config.py
claude_api_key: str = Field(default="", description="Claude API密钥")
claude_model: str = Field(default="claude-3-opus", description="Claude模型")

# llm_service.py
elif self.provider == "anthropic":
    from anthropic import Anthropic
    self.client = Anthropic(api_key=settings.claude_api_key)
```

## 相关文档

- [配置文件示例](.env.example)
- [LLM服务实现](app/services/llm_service.py)
- [节点配置定义](app/core/config.py)
- [文本填充节点](app/nodes/text_filler.py)
- [需求提取节点](app/nodes/pageindex_enricher.py)

## 总结

多模型配置系统提供了：
1. **灵活性**：每个节点可以使用不同模型
2. **经济性**：简单任务用便宜模型，复杂任务用强模型
3. **可维护性**：统一的配置管理
4. **可扩展性**：易于添加新的提供商和模型

**推荐配置**：生产环境使用混合模式，关键节点（structurizer、extractor）使用强模型，其他节点使用经济模型。