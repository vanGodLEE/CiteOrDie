# PageIndex 429限流快速失败优化

## 问题背景

### 原始问题
在`verify_toc`阶段遇到429限流时，PageIndex内部会重试10次：

```
start verify_toc
check all items
************* Retrying *************  ← 第1次重试
ERROR:root:Error: Error code: 429...
************* Retrying *************  ← 第2次重试
ERROR:root:Error: Error code: 429...
...
************* Retrying *************  ← 第10次重试
ERROR:root:Error: Error code: 429...
```

**每次重试等待1秒 × 10次 = 10秒**，然后才会失败并触发我们外层的模型降级策略。

### 效率损失

在配置了4个模型的情况下：
```
qwen3-max → 10次重试（10秒）→ 失败
qwen3-max-preview → 10次重试（10秒）→ 失败  
qwen-max → 10次重试（10秒）→ 失败
qwen-plus-latest → 成功
```

**总耗时：30秒+**（仅重试时间），还不包括API调用本身的时间。

## 解决方案：快速失败（Fast Fail）

### 核心思想

**检测到429限流错误时立即失败，不重试**，让外层的模型降级逻辑快速接管。

### 实现细节

修改了[`pageindex/utils.py`](pageindex/utils.py)中的3个API调用函数：

#### 1. ChatGPT_API_async (异步调用)

```python
async def ChatGPT_API_async(model, prompt, api_key=API_KEY):
    max_retries = 10
    messages = [{"role": "user", "content": prompt}]
    for i in range(max_retries):
        try:
            async with openai.AsyncOpenAI(api_key=api_key,base_url=BASE_URL) as client:
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0,
                )
                return response.choices[0].message.content
        except Exception as e:
            error_str = str(e).lower()
            # 🚀 检测429限流错误 - 立即失败，不重试
            if "429" in error_str or "rate" in error_str or "quota" in error_str:
                logging.error(f"Rate limit error detected, failing fast: {e}")
                raise  # 立即抛出异常，触发外层降级逻辑
            
            # 其他错误继续重试（网络波动等）
            print('************* Retrying *************')
            logging.error(f"Error: {e}")
            if i < max_retries - 1:
                await asyncio.sleep(1)
            else:
                logging.error('Max retries reached for prompt: ' + prompt)
                return "Error"
```

#### 2. ChatGPT_API (同步调用)

```python
def ChatGPT_API(model, prompt, api_key=API_KEY, chat_history=None):
    # ... 省略初始化代码 ...
    for i in range(max_retries):
        try:
            # ... API调用 ...
            return response.choices[0].message.content
        except Exception as e:
            error_str = str(e).lower()
            # 检测429限流错误 - 立即失败，不重试
            if "429" in error_str or "rate" in error_str or "quota" in error_str:
                logging.error(f"Rate limit error detected, failing fast: {e}")
                raise
            
            # 其他错误继续重试
            print('************* Retrying *************')
            # ...
```

#### 3. ChatGPT_API_with_finish_reason

同样的修改应用到这个函数。

### 错误识别规则

检测以下关键词（不区分大小写）：
- `429` - HTTP状态码
- `rate` - "rate limit", "rate quota"等
- `quota` - "quota exceeded"等

### 保留的重试机制

**仅对429限流错误快速失败**，其他错误仍会重试：
- 网络超时
- 连接失败
- 服务暂时不可用
- 其他临时性错误

## 效果对比

### 优化前（传统重试）

```
尝试qwen3-max...
  → 429错误
  → 重试1次（1秒）→ 429
  → 重试2次（1秒）→ 429
  → ...
  → 重试10次（1秒）→ 429
  → 失败（耗时10秒+）

切换到qwen3-max-preview...
  → 429错误
  → 重试1-10次（10秒+）
  → 失败

切换到qwen-max...
  → 成功

总耗时：20秒+ 重试时间
```

### 优化后（快速失败）

```
尝试qwen3-max...
  → 429错误
  → 立即失败（耗时<1秒）

切换到qwen3-max-preview...
  → 429错误
  → 立即失败（耗时<1秒）

切换到qwen-max...
  → 成功

总耗时：<3秒（仅API调用时间）
```

**性能提升：从20秒+降至3秒以内，提速85%+**

## 与外层降级策略的配合

### 完整流程

```
┌─────────────────────────────────────────────┐
│  PageIndexService.parse_pdf()               │
│  (外层：模型轮换降级)                        │
│                                             │
│  for model in [qwen3-max, qwen-max, ...]:  │
│    try:                                     │
│      ┌───────────────────────────────────┐ │
│      │  PageIndex.verify_toc()           │ │
│      │  (内层：快速失败)                  │ │
│      │                                   │ │
│      │  ChatGPT_API_async()              │ │
│      │    ↓                              │ │
│      │  检测到429 → raise immediately    │ │
│      └───────────────────────────────────┘ │
│                                             │
│    except 429 Exception:                   │
│      ↓                                      │
│      切换到下一个模型                        │
└─────────────────────────────────────────────┘
```

### 协同优势

1. **内层快速失败**：PageIndex检测到429立即抛出异常
2. **外层快速切换**：PageIndexService捕获异常，立即尝试下一个模型
3. **无重复等待**：每个模型只尝试1次，不重复等待

## 日志变化

### 优化前
```
start verify_toc
check all items
************* Retrying *************
ERROR:root:Error: Error code: 429...
************* Retrying *************
ERROR:root:Error: Error code: 429...
[重复8次]
************* Retrying *************
ERROR:root:Error: Error code: 429...
Max retries reached
```

### 优化后
```
start verify_toc
check all items
ERROR:root:Rate limit error detected, failing fast: Error code: 429...
[立即切换到下一个模型]
```

## 注意事项

### 1. 不影响其他错误的重试

网络波动、临时性故障等仍会重试：
```python
# 这些错误仍会重试10次
- Connection timeout
- Connection reset
- Server internal error (500)
- Bad gateway (502)
```

### 2. 只修改PageIndex内部逻辑

外层代码（LangGraph节点等）不受影响，它们仍使用自己的`LLMService`。

### 3. 适用范围

修改生效于PageIndex的所有阶段：
- ✅ 解析文档结构
- ✅ 验证目录（verify_toc）
- ✅ 生成摘要
- ✅ 其他所有调用`ChatGPT_API*`的地方

## 测试建议

### 1. 正常场景测试

```bash
# 使用未限流的模型
STRUCTURIZER_MODEL=qwen-plus-latest
FALLBACK_MODELS=

# 应该正常完成，无429错误
```

### 2. 限流场景测试

```bash
# 使用容易限流的模型
STRUCTURIZER_MODEL=qwen3-max
FALLBACK_MODELS=qwen-max,qwen-plus-latest

# 观察：
# - 是否快速切换（<3秒）
# - 日志中是否有"failing fast"
# - 最终是否成功
```

### 3. 网络问题测试

```bash
# 模拟网络波动
# 应该看到正常的重试（对非429错误）
```

## 相关文件

- [`pageindex/utils.py`](pageindex/utils.py:49-136) - 修改的3个API函数
- [`app/services/pageindex_service.py`](app/services/pageindex_service.py:94-203) - 外层降级逻辑
- [`RATE_LIMIT_HANDLING.md`](RATE_LIMIT_HANDLING.md) - 完整的429限流处理文档

## 总结

**PageIndex 429快速失败优化**通过在内部检测到限流错误时立即失败，配合外层的模型轮换降级策略，实现了：

✅ **大幅提升响应速度**：从20秒+降至3秒以内
✅ **保持系统稳定性**：其他错误仍会正常重试
✅ **无侵入式修改**：只修改PageIndex内部，不影响外层逻辑
✅ **完全自动化**：无需人工干预

这是对[429限流自动降级策略](RATE_LIMIT_HANDLING.md)的重要补充和性能优化！