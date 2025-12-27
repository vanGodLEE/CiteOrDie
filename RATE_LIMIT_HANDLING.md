# 429限流自动降级策略文档

## 问题背景

在使用阿里云通义千问等API时，经常遇到429 Rate Limit错误：

```
ERROR:root:Error: Error code: 429 - {'error': {'message': 'You have exceeded your current request limit. For details, see: https://help.aliyun.com/zh/model-studio/error-code#rate-limit', 'type': 'limit_requests', 'param': None, 'code': 'limit_requests'}}
```

**问题特点**：
- PageIndex文档解析阶段调用频繁（解析目录、验证结构等）
- qwen3-max等高级模型限流更严格
- 单个任务可能需要几十次API调用
- 传统重试机制无效（越重试越限流）

## 解决方案

### 核心策略：模型轮换降级

当主模型遇到429限流时，**自动切换到备用模型**，而不是无限重试同一个模型。

### 工作原理

```
初始配置：
- 主模型: qwen3-max
- 备用: qwen3-max-preview, qwen-max, qwen-plus-latest

执行流程：
1. 尝试 qwen3-max → 429限流 ❌
2. 自动切换 qwen3-max-preview → 429限流 ❌
3. 自动切换 qwen-max → 成功 ✅
4. 后续请求继续使用 qwen-max
```

### 优势

1. **避免无限重试**：不在同一个被限流的模型上死磕
2. **自动负载均衡**：分散到多个模型，降低单一模型压力
3. **保证可用性**：至少一个模型可用时就能完成任务
4. **配置灵活**：可以随时调整模型列表

## 配置方式

### 1. 在.env文件中配置

```bash
# 主模型（首选）
STRUCTURIZER_MODEL=qwen3-max

# 备用模型（逗号分隔，按优先级排列）
FALLBACK_MODELS=qwen3-max-preview,qwen-max,qwen-plus-latest
```

### 2. 配置说明

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `STRUCTURIZER_MODEL` | 主模型，首先尝试 | `qwen3-max` |
| `FALLBACK_MODELS` | 备用模型列表，逗号分隔 | `qwen3-max-preview,qwen-max` |

**注意**：
- 备用模型按照顺序尝试
- 建议按性能从高到低排列
- 可以留空表示不启用降级

### 3. 推荐配置

#### 配置A：阿里云通义千问（4个模型轮换）

```bash
STRUCTURIZER_MODEL=qwen3-max
FALLBACK_MODELS=qwen3-max-preview,qwen-max,qwen-plus-latest
```

**效果**：
- 总共4个模型可用
- qwen3-max最强但限流最严
- qwen-plus-latest最快且限流最宽松

#### 配置B：混合provider（跨平台）

```bash
# 使用DeepSeek provider
LLM_PROVIDER=deepseek
DEEPSEEK_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1

STRUCTURIZER_MODEL=qwen3-max
FALLBACK_MODELS=qwen-max,deepseek-chat,gpt-4o-mini
```

**效果**：
- 跨平台降级
- 更高的可用性保障
- 需要配置多个provider的API_KEY

#### 配置C：保守策略（2个模型）

```bash
STRUCTURIZER_MODEL=qwen-max
FALLBACK_MODELS=qwen-plus-latest
```

**效果**：
- 主模型用性能较好的qwen-max
- 备用模型用最稳定的qwen-plus
- 降低配置复杂度

## 实现细节

### 代码架构

修改的核心文件：[`app/services/pageindex_service.py`](app/services/pageindex_service.py:46-203)

```python
class PageIndexService:
    def __init__(self, model: str, fallback_models: List[str] = None):
        self.primary_model = model
        self.fallback_models = fallback_models or []
        # 完整模型列表
        self.all_models = [model] + self.fallback_models
        
    def parse_pdf(self, pdf_path: str):
        # 尝试所有模型
        for attempt, model in enumerate(self.all_models):
            try:
                result = page_index(doc=pdf_path, model=model, ...)
                
                # 成功，记录当前模型
                if attempt > 0:
                    logger.info(f"✓ 备用模型成功: {model}")
                
                return result
                
            except Exception as e:
                # 检测是否429限流
                is_rate_limit = "429" in str(e) or "rate" in str(e).lower()
                
                if is_rate_limit and attempt < len(self.all_models) - 1:
                    logger.warning(f"⚠️ 模型 {model} 限流，切换...")
                    continue  # 尝试下一个模型
                else:
                    raise  # 非限流错误或所有模型都失败
```

### 错误识别

系统识别以下情况为429限流：
1. 错误码包含"429"
2. 错误消息包含"rate"或"limit"（不区分大小写）

示例错误消息：
```
Error code: 429 - {'error': {'message': 'You have exceeded your current request limit...
```

### 日志输出

启用降级后的日志示例：

```
[INFO] PageIndex服务初始化完成
[INFO]   - 主模型: qwen3-max
[INFO]   - 备用模型: qwen3-max-preview, qwen-max, qwen-plus-latest
[INFO]   - 429限流自动降级: 已启用

[INFO] 尝试使用主模型: qwen3-max (第1/4次)
[WARNING] ⚠️ 模型 qwen3-max 遇到429限流错误
[INFO] → 自动切换到下一个备用模型...

[INFO] 尝试使用备用模型: qwen3-max-preview (第2/4次)
[WARNING] ⚠️ 模型 qwen3-max-preview 遇到429限流错误
[INFO] → 自动切换到下一个备用模型...

[INFO] 尝试使用备用模型: qwen-max (第3/4次)
[INFO] ✓ PageIndex解析完成（使用备用模型: qwen-max）
[INFO]   - 文档名称: example.pdf
[INFO]   - 结构节点数: 45
[INFO] ✓ 备用模型成功，切换到: qwen-max
```

## 最佳实践

### 1. 模型选择策略

按性能和限流宽松度排列：

| 模型 | 性能 | 限流严格度 | 推荐位置 |
|------|------|------------|----------|
| qwen3-max | ⭐⭐⭐⭐⭐ | 🔴 很严格 | 主模型（优先尝试） |
| qwen3-max-preview | ⭐⭐⭐⭐ | 🟡 中等 | 第一备用 |
| qwen-max | ⭐⭐⭐ | 🟢 宽松 | 第二备用 |
| qwen-plus-latest | ⭐⭐ | 🟢 很宽松 | 兜底备用 |

### 2. 配置原则

1. **主模型**：选择性能最好的（即使限流严格）
2. **第一备用**：选择性能次优但限流稍宽松的
3. **最后备用**：选择最稳定、限流最宽松的（保底）

### 3. 监控建议

关注日志中的关键信息：
- ✅ 成功使用哪个模型
- ⚠️ 哪些模型被限流
- 📊 降级频率（如果频繁降级，考虑调整主模型）

### 4. 成本优化

如果发现经常降级到低成本模型：
```bash
# 不如直接把低成本模型设为主模型
STRUCTURIZER_MODEL=qwen-plus-latest
FALLBACK_MODELS=qwen-max,qwen3-max
```

## 故障排查

### Q1: 所有模型都被限流了怎么办？

**现象**：
```
ERROR: 所有配置的模型都遇到429限流错误
尝试过的模型: qwen3-max, qwen-max, qwen-plus-latest
```

**解决方案**：
1. **等待一段时间**：API限流通常有时间窗口（1分钟/1小时）
2. **检查API配额**：登录阿里云控制台查看配额
3. **添加更多provider**：
   ```bash
   # 跨平台配置
   OPENAI_API_KEY=sk-xxx
   FALLBACK_MODELS=qwen-max,deepseek-chat,gpt-4o-mini
   ```

### Q2: 降级后性能下降明显？

**解决方案**：
1. **调整模型顺序**：把性能好的模型放前面
2. **移除低性能模型**：
   ```bash
   # 只保留高性能模型
   FALLBACK_MODELS=qwen3-max-preview,qwen-max
   ```
3. **升级API配额**：购买更高的QPM（每分钟请求数）

### Q3: 如何禁用降级功能？

```bash
# 方法1：留空fallback_models
FALLBACK_MODELS=

# 方法2：不配置fallback_models（使用默认值）
# FALLBACK_MODELS=
```

### Q4: 可以动态调整模型列表吗？

**当前不支持**运行时动态调整，需要：
1. 修改`.env`文件
2. 重启应用

**未来可能支持**：
- 热更新配置
- 基于监控自动调整

## 性能影响

### 额外开销

- ✅ **无性能损失**：只有在429限流时才触发降级
- ✅ **快速切换**：切换模型<1秒
- ⚠️ **首次调用**：需要初始化备用provider的client

### 成功率提升

| 配置 | 单模型失败率 | 多模型降级后失败率 |
|------|--------------|-------------------|
| 1个模型 | 30% | 30% |
| 2个模型 | 30% | 9% (0.3 × 0.3) |
| 4个模型 | 30% | 0.81% (0.3^4) |

**结论**：4个模型轮换可将失败率从30%降至<1%

## 相关配置

### 完整配置示例

```bash
# ==================== LLM Provider ====================
LLM_PROVIDER=deepseek

# DeepSeek (兼容阿里云)
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
DEEPSEEK_MODEL=qwen-plus-latest

# OpenAI (可选，用于跨平台降级)
OPENAI_API_KEY=sk-xxx
OPENAI_API_BASE=https://api.openai.com/v1

# ==================== 节点模型配置 ====================
# PageIndex文档解析（支持429自动降级）
STRUCTURIZER_MODEL=qwen3-max
FALLBACK_MODELS=qwen3-max-preview,qwen-max,qwen-plus-latest

# 其他节点（不受429降级影响）
TEXT_FILLER_MODEL=qwen-plus-latest
SUMMARY_MODEL=qwen-turbo-latest
EXTRACTOR_MODEL=qwen-plus-latest
```

## 总结

429限流自动降级策略通过**模型轮换**而非**无限重试**来解决限流问题：

✅ **优点**：
- 自动处理，无需人工干预
- 大幅提升成功率
- 负载分散到多个模型
- 配置灵活，易于调整

⚠️ **注意**：
- 仅对PageIndex文档解析阶段生效
- 需要配置多个可用模型
- 降级到低性能模型可能影响效果

📚 **相关文档**：
- [多模型配置指南](MULTI_MODEL_CONFIGURATION.md)
- [PageIndex服务实现](app/services/pageindex_service.py)
- [配置示例](.env.example)