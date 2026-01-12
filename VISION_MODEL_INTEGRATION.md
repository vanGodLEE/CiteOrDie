# 视觉模型集成说明

## 概述

本文档说明阶段5：视觉模型配置与集成的实现细节。系统现已支持Qwen-VL（通义千问视觉模型）用于图片和表格的智能分析。

## 实现内容

### 1. 配置扩展 ([`app/core/config.py`](app/core/config.py))

#### 新增配置项

```python
# Qwen-VL基础配置
qwen_api_key: str           # Qwen API密钥
qwen_api_base: str          # API基础URL（默认：阿里云DashScope）
qwen_vl_model: str          # 视觉模型名称（默认：qwen-vl-max-latest）

# 节点级配置
vision_model: str           # 视觉模型配置，格式：provider:model
                           # 默认：qwen:qwen-vl-max-latest
```

#### 环境变量配置 ([`.env.example`](.env.example))

```bash
# Qwen-VL配置
QWEN_API_KEY=your_qwen_api_key_here
QWEN_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_VL_MODEL=qwen-vl-max-latest

# 视觉模型节点配置
VISION_MODEL=qwen:qwen-vl-max-latest
```

### 2. LLM服务增强 ([`app/services/llm_service.py`](app/services/llm_service.py))

#### 新增Provider支持

- **Qwen Provider**: 支持阿里云通义千问系列模型
- **动态Client管理**: 自动创建和缓存Qwen client
- **统一接口**: 使用OpenAI兼容的API格式

#### 核心方法

##### `vision_completion()` - 视觉模型调用

```python
def vision_completion(
    self,
    text_prompt: str,                    # 文本提示词
    image_inputs: List[Union[str, Path]],  # 图片输入（支持路径或base64）
    temperature: float = 0.3,
    max_tokens: int = 2000,
    model: Optional[str] = None           # 可选模型覆盖
) -> str:
    """
    视觉模型调用，支持图文混合输入
    
    Returns:
        模型生成的文本描述
    """
```

**特性**:
- ✅ 支持本地文件路径自动转换base64
- ✅ 支持多张图片同时输入
- ✅ 支持已编码的data URI直接输入
- ✅ 自动识别图片MIME类型
- ✅ 详细的token使用统计

##### `encode_image_to_base64()` - 图片编码

```python
@staticmethod
def encode_image_to_base64(image_path: Union[str, Path]) -> str:
    """
    将本地图片编码为base64 data URI
    
    支持格式: .png, .jpg, .jpeg, .webp, .gif, .bmp
    
    Returns:
        "data:image/png;base64,..." 格式的字符串
    """
```

**特性**:
- ✅ 自动检测文件存在性
- ✅ 自动识别MIME类型
- ✅ 生成标准data URI格式

## 使用示例

### 基础用法

```python
from app.services.llm_service import get_llm_service

llm = get_llm_service()

# 分析单张图片
result = llm.vision_completion(
    text_prompt="请描述这张图片中的表格内容",
    image_inputs=["path/to/image.png"]
)

# 分析多张图片
result = llm.vision_completion(
    text_prompt="对比这两张图片的技术参数差异",
    image_inputs=[
        "path/to/spec1.png",
        "path/to/spec2.png"
    ]
)
```

### 高级用法

```python
# 使用base64 data URI
base64_uri = llm.encode_image_to_base64("path/to/image.png")
result = llm.vision_completion(
    text_prompt="提取图片中的关键信息",
    image_inputs=[base64_uri]
)

# 指定特定模型
result = llm.vision_completion(
    text_prompt="分析技术架构图",
    image_inputs=["arch.png"],
    model="qwen:qwen-vl-max-latest"  # 显式指定模型
)

# 调整参数
result = llm.vision_completion(
    text_prompt="详细描述图片内容",
    image_inputs=["detail.png"],
    temperature=0.1,      # 更确定性的输出
    max_tokens=4000       # 更长的输出
)
```

## 技术架构

### 多模态消息格式

视觉模型使用OpenAI兼容的多模态消息格式：

```json
{
  "role": "user",
  "content": [
    {
      "type": "text",
      "text": "请分析这张图片"
    },
    {
      "type": "image_url",
      "image_url": {
        "url": "data:image/png;base64,iVBORw0KG..."
      }
    }
  ]
}
```

### Provider架构

```
LLMService
├── _clients: Dict[str, OpenAI]
│   ├── "openai"   → OpenAI client
│   ├── "deepseek" → DeepSeek client
│   └── "qwen"     → Qwen client (新增)
│
├── structured_completion()  # 结构化输出
├── text_completion()        # 文本生成
└── vision_completion()      # 视觉模型 (新增)
```

### Base64编码优势

1. **本地路径支持**: 无需上传到云端，直接编码发送
2. **隐私保护**: 图片不经过第三方存储
3. **性能优化**: 减少网络往返次数
4. **统一接口**: 与远程URL使用相同API

## 后续计划

### 阶段6：需求提取增强（视觉模型支持）

将在`pageindex_enricher.py`节点中集成视觉模型：

1. **图片内容分析**: 识别技术参数、规格表
2. **表格数据提取**: 智能解析复杂表格
3. **图文融合**: 结合Markdown文本和图片内容
4. **需求智能提取**: 从视觉内容中提取招标需求

### 阶段7：数据模型扩展

扩展需求树数据结构支持：

```python
{
  "requirement": "...",
  "original_text": "...",
  "caption": "图片描述/表格分析结果",  # 新增字段
  "image_paths": ["path1.png", "path2.png"]  # 新增字段
}
```

## 配置建议

### 生产环境

```bash
# 使用Qwen-VL-Max获得最佳效果
VISION_MODEL=qwen:qwen-vl-max-latest
QWEN_API_KEY=sk-your-production-key
```

### 开发环境

```bash
# 可使用Qwen-VL-Plus节省成本
VISION_MODEL=qwen:qwen-vl-plus-latest
QWEN_API_KEY=sk-your-dev-key
```

## 注意事项

1. **API密钥**: 确保配置有效的`QWEN_API_KEY`
2. **图片大小**: 建议单张图片<10MB，过大会影响性能
3. **Token消耗**: 图片会消耗较多token，注意成本控制
4. **错误处理**: 视觉模型调用失败会抛出异常，需妥善处理

## 测试验证

### 单元测试

```python
def test_vision_completion():
    llm = get_llm_service()
    
    # 测试单图
    result = llm.vision_completion(
        text_prompt="描述这张图片",
        image_inputs=["test/sample.png"]
    )
    assert len(result) > 0
    
    # 测试多图
    result = llm.vision_completion(
        text_prompt="对比这两张图",
        image_inputs=["test/img1.png", "test/img2.png"]
    )
    assert len(result) > 0
```

### 集成测试

将在阶段9进行完整的端到端测试。

## 总结

✅ **已完成**:
- Qwen-VL provider集成
- 视觉模型调用接口
- 本地图片base64编码
- 多图片同时分析
- 完整的配置支持

🔄 **进行中**:
- 阶段6：需求提取增强
- 阶段7：数据模型扩展

⏳ **待完成**:
- 阶段9：完整测试验证

---

**最后更新**: 2026-01-08  
**版本**: v1.0  
**作者**: Kilo Code