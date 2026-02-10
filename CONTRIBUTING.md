# 贡献指南

感谢您对 CiteOrDie 项目的关注！我们欢迎各种形式的贡献。

## 🤝 如何贡献

### 报告Bug

如果您发现了Bug，请：

1. 在 [GitHub Issues](https://github.com/YOUR_USERNAME/CiteOrDie/issues) 中搜索是否已有相关问题
2. 如果没有，创建新Issue，包含以下信息：
   - Bug的详细描述
   - 复现步骤
   - 期望行为
   - 实际行为
   - 系统环境（OS、Python版本、Docker版本等）
   - 日志和截图（如有）

### 提出新功能

如果您有新功能的想法：

1. 在 Issues 中创建 Feature Request
2. 详细描述功能需求和使用场景
3. 讨论技术实现方案
4. 等待维护者反馈

### 提交代码

1. **Fork 项目**
   ```bash
   # 点击GitHub页面的Fork按钮
   ```

2. **克隆到本地**
   ```bash
   git clone https://github.com/YOUR_USERNAME/CiteOrDie.git
   cd CiteOrDie
   ```

3. **创建特性分支**
   ```bash
   git checkout -b feature/your-feature-name
   # 或
   git checkout -b fix/your-bug-fix
   ```

4. **开发**
   - 遵循代码规范（见下文）
   - 添加必要的测试
   - 更新相关文档

5. **提交更改**
   ```bash
   git add .
   git commit -m "feat: add new feature"
   # 或
   git commit -m "fix: fix bug in..."
   ```

6. **推送到GitHub**
   ```bash
   git push origin feature/your-feature-name
   ```

7. **创建 Pull Request**
   - 在GitHub上创建PR
   - 填写PR模板
   - 等待Review

## 📝 代码规范

### Python 代码规范

- 遵循 [PEP 8](https://www.python.org/dev/peps/pep-0008/)
- 使用类型提示（Type Hints）
- 函数和类添加文档字符串

示例：
```python
def extract_clauses(document: str, config: Dict[str, Any]) -> List[ClauseItem]:
    """
    从文档中提取条款
    
    Args:
        document: 文档内容
        config: 配置参数
        
    Returns:
        提取的条款列表
        
    Raises:
        ValueError: 当文档为空时
    """
    if not document:
        raise ValueError("文档不能为空")
    # ... implementation
```

### JavaScript/Vue 代码规范

- 使用 ES6+ 语法
- 组件使用 Composition API
- 变量和函数使用驼峰命名

示例：
```vue
<script setup>
import { ref, computed, onMounted } from 'vue'

const clauseList = ref([])
const filteredClauses = computed(() => {
  return clauseList.value.filter(c => c.type === 'requirement')
})

onMounted(async () => {
  await loadClauses()
})
</script>
```

### 提交信息规范

使用 [Conventional Commits](https://www.conventionalcommits.org/)：

```
<type>(<scope>): <subject>

<body>

<footer>
```

类型（type）：
- `feat`: 新功能
- `fix`: Bug修复
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构
- `perf`: 性能优化
- `test`: 测试相关
- `chore`: 构建/工具链

示例：
```
feat(extractor): add table clause extraction support

- Implement table content parsing
- Add vision model integration for table images
- Update extraction prompts

Closes #123
```

## 🧪 测试

提交代码前请确保：

```bash
# 运行所有测试
pytest tests/

# 检查代码风格
flake8 app/

# 类型检查
mypy app/
```

## 📖 文档

如果您的更改涉及：
- 新功能 → 更新 README.md 和相关文档
- API变更 → 更新 API文档
- 配置项变更 → 更新 .env.example 和配置说明

## 🔍 Code Review

您的PR将经过以下检查：

- ✅ 代码风格符合规范
- ✅ 所有测试通过
- ✅ 新功能有测试覆盖
- ✅ 文档已更新
- ✅ 无安全问题
- ✅ 性能无明显下降

## 💡 开发提示

### 本地开发环境搭建

```bash
# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate

# 2. 安装开发依赖
pip install -r requirements.txt
pip install pytest flake8 mypy black

# 3. 配置pre-commit（可选）
pip install pre-commit
pre-commit install
```

### 调试技巧

1. **启用详细日志**
   ```python
   LOG_LEVEL=DEBUG uvicorn app.api.main:app --reload
   ```

2. **使用断点**
   ```python
   import pdb; pdb.set_trace()
   ```

3. **查看LLM调用**
   ```python
   # 在 .env 中设置
   OPENAI_LOG=debug
   ```

## 🎯 优先级任务

当前需要帮助的领域：

- [ ] 支持更多文档格式（Word, Excel）
- [ ] 优化条款提取准确率
- [ ] 添加更多单元测试
- [ ] 改进用户界面
- [ ] 性能优化
- [ ] 国际化支持

查看 [Issues](https://github.com/YOUR_USERNAME/CiteOrDie/issues) 了解详情。

## 📮 联系方式

如有疑问，欢迎通过以下方式联系：

- **GitHub Issues**: 技术问题和Bug报告
- **GitHub Discussions**: 功能讨论和想法交流
- **Email**: your-email@example.com

---

再次感谢您的贡献！🎉
