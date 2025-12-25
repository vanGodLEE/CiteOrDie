# MinIO配置故障排查指南

## 常见问题

### 问题0：Access Denied（访问被拒绝） ⭐

**错误信息**：
```xml
<Error>
<Code>AccessDenied</Code>
<Message>Access Denied.</Message>
</Error>
```

**原因**：
MinIO bucket默认是私有的，直接访问URL会被拒绝。

**解决方案**：

系统已自动使用**预签名URL**（Presigned URL）：
- ✅ API返回的URL包含临时访问令牌
- ✅ 默认有效期24小时
- ✅ 无需修改bucket策略
- ✅ 安全且灵活

**使用方法**：
```bash
# 调用API获取预签名URL
GET /api/pdf/{task_id}

# 返回的minio_url已经包含访问令牌，可以直接访问
# 示例：http://192.168.100.219:19000/tender-pdf/xxx.pdf?X-Amz-Signature=...
```

**注意**：预签名URL会过期（24小时后），需要重新获取。

---

### 问题1：端口配置错误 ⚠️

**错误信息**：
```
S3 API Requests must be made to API port.
Response code: 400
```

**原因**：
MinIO有两个不同的端口：
- **Web Console端口**（用于浏览器访问）：通常是 `9001` 或 `19001`
- **S3 API端口**（用于程序调用）：通常是 `9000` 或 `19000`

程序需要连接到 **S3 API端口**，而不是Web Console端口。

**解决方案**：

1. **查找正确的S3 API端口**

   方法A：询问MinIO管理员
   ```
   请提供MinIO的S3 API端口号
   ```

   方法B：尝试常见端口
   ```bash
   # 尝试端口19000（如果Console是19001）
   # 尝试端口9000（如果Console是9001）
   ```

   方法C：检查MinIO服务器配置
   ```bash
   # 在MinIO服务器上查看配置
   cat /etc/default/minio
   # 或
   docker inspect minio | grep MINIO_API_PORT
   ```

2. **更新.env配置**

   在项目根目录的 `.env` 文件中修改：
   ```env
   # 从19001改为19000（或其他正确的API端口）
   MINIO_ENDPOINT=192.168.100.219:19000
   ```

3. **重启服务**
   ```bash
   # 重启FastAPI服务
   # Ctrl+C 停止，然后重新运行
   python -m uvicorn app.api.main:app --reload --port 8866
   ```

---

### 问题2：连接超时

**错误信息**：
```
Connection timeout
```

**可能原因**：
- MinIO服务器未启动
- 防火墙阻止连接
- 网络不通

**解决方案**：

1. **检查MinIO服务器状态**
   ```bash
   # 在MinIO服务器上
   systemctl status minio
   # 或
   docker ps | grep minio
   ```

2. **测试网络连接**
   ```bash
   # Windows
   Test-NetConnection 192.168.100.219 -Port 19000
   
   # Linux/Mac
   nc -zv 192.168.100.219 19000
   # 或
   telnet 192.168.100.219 19000
   ```

3. **检查防火墙**
   ```bash
   # 确保MinIO的API端口已开放
   ```

---

### 问题3：认证失败

**错误信息**：
```
Access Denied
Invalid credentials
```

**解决方案**：

1. **验证账号密码**
   
   在 `.env` 文件中检查：
   ```env
   MINIO_ACCESS_KEY=rag_flow
   MINIO_SECRET_KEY=infini_rag_flow
   ```

2. **测试MinIO登录**
   
   使用浏览器访问Web Console：
   ```
   http://192.168.100.219:19001
   ```
   
   尝试用相同的账号密码登录。

3. **联系MinIO管理员确认凭据**

---

### 问题4：桶不存在且无法创建

**错误信息**：
```
Bucket does not exist
Access Denied (creating bucket)
```

**解决方案**：

1. **检查用户权限**
   
   确保MinIO用户有创建桶的权限

2. **手动创建桶**
   
   登录MinIO Web Console：
   ```
   http://192.168.100.219:19001
   ```
   
   手动创建名为 `tender-pdf` 的桶

3. **使用已存在的桶**
   
   在 `.env` 中修改为已存在的桶名：
   ```env
   MINIO_BUCKET=your-existing-bucket-name
   ```

---

## 配置检查清单

使用以下清单验证MinIO配置：

- [ ] MinIO服务器正在运行
- [ ] 使用正确的S3 API端口（不是Web Console端口）
- [ ] 网络连接正常（能ping通服务器）
- [ ] API端口未被防火墙阻止
- [ ] Access Key和Secret Key正确
- [ ] 用户有创建桶的权限
- [ ] 桶名称有效（小写字母、数字、连字符）

---

## 快速测试脚本

创建 `test_minio.py` 文件测试连接：

```python
from minio import Minio
from minio.error import S3Error

# 配置（从.env中复制）
ENDPOINT = "192.168.100.219:19000"  # 注意：使用API端口
ACCESS_KEY = "rag_flow"
SECRET_KEY = "infini_rag_flow"
BUCKET = "tender-pdf"

print("=" * 60)
print("MinIO连接测试")
print("=" * 60)

try:
    # 创建客户端
    print(f"1. 连接MinIO: {ENDPOINT}")
    client = Minio(
        endpoint=ENDPOINT,
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        secure=False
    )
    print("   ✓ 连接成功")
    
    # 检查桶
    print(f"\n2. 检查桶: {BUCKET}")
    if client.bucket_exists(BUCKET):
        print(f"   ✓ 桶已存在")
    else:
        print(f"   ! 桶不存在，尝试创建...")
        client.make_bucket(BUCKET)
        print(f"   ✓ 桶创建成功")
    
    # 列出桶中的对象
    print(f"\n3. 列出桶中的对象")
    objects = list(client.list_objects(BUCKET, recursive=True))
    if objects:
        print(f"   找到 {len(objects)} 个对象:")
        for obj in objects[:5]:  # 只显示前5个
            print(f"     - {obj.object_name}")
    else:
        print(f"   桶是空的")
    
    print("\n" + "=" * 60)
    print("✓ 所有测试通过！MinIO配置正确")
    print("=" * 60)
    
except S3Error as e:
    print(f"\n✗ MinIO错误: {e}")
    print("\n可能的原因：")
    print("  1. 端口配置错误（请确认使用S3 API端口）")
    print("  2. Access Key或Secret Key不正确")
    print("  3. 用户权限不足")
    
except Exception as e:
    print(f"\n✗ 连接失败: {e}")
    print("\n可能的原因：")
    print("  1. MinIO服务器未启动")
    print("  2. 网络不通")
    print("  3. 防火墙阻止连接")
    print(f"  4. 端口 {ENDPOINT.split(':')[1]} 不是S3 API端口")
```

运行测试：
```bash
python test_minio.py
```

---

## 常见MinIO端口配置

| 场景 | Web Console端口 | S3 API端口 | 配置示例 |
|------|----------------|------------|----------|
| 标准部署 | 9001 | 9000 | `MINIO_ENDPOINT=ip:9000` |
| Docker | 19001 | 19000 | `MINIO_ENDPOINT=ip:19000` |
| 自定义 | 询问管理员 | 询问管理员 | 根据实际情况配置 |

---

## 获取帮助

如果以上方法都无法解决问题：

1. **查看MinIO日志**（在MinIO服务器上）
   ```bash
   journalctl -u minio -f
   # 或
   docker logs minio
   ```

2. **联系MinIO管理员**
   - 确认S3 API端口号
   - 确认用户权限
   - 确认网络策略

3. **查看项目日志**
   ```bash
   # 日志会显示详细的错误信息
   tail -f logs/app.log