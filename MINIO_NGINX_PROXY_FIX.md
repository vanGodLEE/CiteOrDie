# Minio通过Nginx反向代理访问的签名验证问题完整解决方案

## 问题描述

直接访问Minio的预签名URL可以正常下载，但通过Nginx代理访问时报错：

```xml
<Error>
<Code>SignatureDoesNotMatch</Code>
<Message>The request signature we calculated does not match the signature you provided.</Message>
</Error>
```

## 根本原因

AWS S3签名（Minio使用）包含以下内容：
- HTTP方法、URL路径、查询参数
- **HTTP头部，特别是Host头**

**问题**：签名生成时使用的Host是`192.168.100.219:19000`（Minio地址），但Nginx代理后，Minio收到的Host头变成了Nginx的地址，导致签名验证失败。

## 完整解决方案

### 方案1：Nginx保持原始Host（推荐）

修改Nginx配置，确保转发时保持原始Host头：

```nginx
location /tender-minio/ {
    # 关键配置：保持Host为Minio的地址
    proxy_set_header Host 192.168.100.219:19000;
    
    # 去掉路径前缀/tender-minio，只保留后面的部分
    rewrite ^/tender-minio/(.*)$ /$1 break;
    
    # 转发到Minio
    proxy_pass http://192.168.100.219:19000;
    
    # 其他必要配置
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # 禁用缓冲（对于大文件下载很重要）
    proxy_buffering off;
    proxy_request_buffering off;
    
    # 超时设置
    proxy_connect_timeout 300;
    proxy_send_timeout 300;
    proxy_read_timeout 300;
}
```

**关键点**：
1. `proxy_set_header Host 192.168.100.219:19000` - 保持Host为Minio地址
2. `rewrite ^/tender-minio/(.*)$ /$1 break` - 移除代理路径前缀
3. `proxy_pass http://192.168.100.219:19000` - 转发到Minio（注意末尾没有/）

### 方案2：前端直接使用完整URL（备选）

如果无法修改Nginx配置，让前端直接使用`minio_url`（完整URL）：

```javascript
// API响应
const data = await fetch(`/api/pdf/${taskId}`).then(r => r.json());

// 直接使用完整URL（绕过Nginx代理）
window.open(data.minio_url);
// 而不是：window.open(`http://部署机IP${data.url_for_frontend}`)
```

**限制**：只适用于前端可以直接访问Minio内网地址的场景。

## 代码实现

### MinioService生成两个URL

**文件**: [`app/services/minio_service.py`](app/services/minio_service.py:96)

```python
def get_pdf_url(self, task_id: str, expires_hours: int = 24) -> tuple[Optional[str], Optional[str]]:
    """
    返回: (直接访问URL, Nginx代理路径)
    """
    # 生成预签名URL
    direct_url = self.client.presigned_get_object(
        bucket_name=self.bucket_name,
        object_name=obj.object_name,
        expires=timedelta(hours=expires_hours)
    )
    
    # 转换为Nginx代理路径
    nginx_url = self._convert_to_nginx_url(direct_url)
    
    return direct_url, nginx_url

def _convert_to_nginx_url(self, minio_url: str) -> str:
    """
    将Minio内网URL转换为Nginx代理路径
    
    输入: http://192.168.100.219:19000/tender-pdf/task/file.pdf?X-Amz-Signature=...
    输出: /tender-minio/tender-pdf/task/file.pdf?X-Amz-Signature=...
    """
    import urllib.parse
    parsed = urllib.parse.urlparse(minio_url)
    
    # 提取路径和查询参数
    path = parsed.path.lstrip('/')  # tender-pdf/task/file.pdf
    query = parsed.query  # X-Amz-Signature=...（保持不变）
    
    # 构建Nginx代理路径
    nginx_path = f"/tender-minio/{path}"
    if query:
        nginx_path = f"{nginx_path}?{query}"
    
    return nginx_path
```

### API返回两个URL

**文件**: [`app/api/async_analyze.py`](app/api/async_analyze.py:380)

```python
@router.get("/pdf/{task_id}")
async def get_pdf_url(task_id: str):
    # 获取两个URL
    direct_url, nginx_url = minio_service.get_pdf_url(task_id)
    
    return {
        "status": "success",
        "task_id": task_id,
        "file_name": task_record.file_name,
        "minio_url": direct_url,  # http://192.168.100.219:19000/tender-pdf/...?签名
        "url_for_frontend": nginx_url,  # /tender-minio/tender-pdf/...?签名
        "message": "PDF文件URL获取成功（24小时有效）"
    }
```

## 前端使用

### 通过Nginx代理访问（需要正确的Nginx配置）

```javascript
const response = await fetch(`/api/pdf/${taskId}`);
const data = await response.json();

// 构建完整URL：部署机IP + Nginx代理路径
const fullUrl = `http://192.168.100.219:8866${data.url_for_frontend}`;
window.open(fullUrl);

// 或者使用当前域名
const fullUrl = `${window.location.origin}${data.url_for_frontend}`;
window.open(fullUrl);
```

### 直接访问Minio（绕过Nginx）

```javascript
const response = await fetch(`/api/pdf/${taskId}`);
const data = await response.json();

// 直接使用完整URL
window.open(data.minio_url);
```

## Nginx配置详解

### 完整配置示例

```nginx
http {
    # 上游服务器定义
    upstream minio_backend {
        server 192.168.100.219:19000;
    }
    
    server {
        listen 8866;
        server_name _;
        
        # FastAPI后端代理
        location /api/ {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
        
        # Minio文件代理（关键配置）
        location /tender-minio/ {
            # ⭐ 关键：保持Host为Minio地址
            proxy_set_header Host 192.168.100.219:19000;
            
            # ⭐ 关键：去掉/tender-minio前缀
            rewrite ^/tender-minio/(.*)$ /$1 break;
            
            # 转发到Minio
            proxy_pass http://minio_backend;
            
            # 传递客户端信息
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # 大文件下载优化
            proxy_buffering off;
            proxy_request_buffering off;
            proxy_max_temp_file_size 0;
            
            # 超时设置（大文件下载可能需要更长时间）
            proxy_connect_timeout 300s;
            proxy_send_timeout 300s;
            proxy_read_timeout 300s;
            
            # 允许大文件上传（如果需要）
            client_max_body_size 500M;
        }
    }
}
```

### 配置验证

**验证Nginx配置语法**：
```bash
nginx -t
```

**重载Nginx配置**：
```bash
nginx -s reload
# 或
systemctl reload nginx
```

**查看Nginx日志**：
```bash
tail -f /var/log/nginx/error.log
tail -f /var/log/nginx/access.log
```

## 测试验证

### 1. 测试直接访问Minio

```bash
curl -I "http://192.168.100.219:19000/tender-pdf/task_id/file.pdf?X-Amz-Signature=..."
```

**预期结果**：
```
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Length: 1234567
```

### 2. 测试Nginx代理访问

```bash
curl -I "http://192.168.100.219:8866/tender-minio/tender-pdf/task_id/file.pdf?X-Amz-Signature=..."
```

**预期结果**：
```
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Length: 1234567
```

### 3. 测试API接口

```bash
curl http://192.168.100.219:8866/api/pdf/2cc40a14-5451-4458-b085-32d5b330ee71
```

**预期响应**：
```json
{
  "status": "success",
  "task_id": "2cc40a14...",
  "file_name": "长三角2024技术招标信息.pdf",
  "minio_url": "http://192.168.100.219:19000/tender-pdf/.../file.pdf?X-Amz-Signature=...",
  "url_for_frontend": "/tender-minio/tender-pdf/.../file.pdf?X-Amz-Signature=...",
  "message": "PDF文件URL获取成功（24小时有效）"
}
```

## 常见错误排查

### 错误1：SignatureDoesNotMatch

```xml
<Code>SignatureDoesNotMatch</Code>
```

**可能原因**：
1. Nginx没有保持Host头为Minio地址
2. 查询参数被修改或丢失
3. URL路径被错误重写

**解决方法**：
```nginx
# 确保这两行配置正确
proxy_set_header Host 192.168.100.219:19000;
rewrite ^/tender-minio/(.*)$ /$1 break;
```

### 错误2：404 Not Found

```xml
<Code>NoSuchKey</Code>
```

**可能原因**：
1. 路径重写错误，Minio收到的路径不对
2. 文件确实不存在

**排查方法**：
```bash
# 查看Nginx access日志，确认转发的路径
tail -f /var/log/nginx/access.log

# 查看Minio日志
docker logs minio-container
```

### 错误3：403 Access Denied

```xml
<Code>AccessDenied</Code>
```

**可能原因**：
1. URL过期（超过24小时）
2. Access Key/Secret Key错误
3. Bucket权限配置问题

**解决方法**：
```bash
# 重新生成URL
curl http://192.168.100.219:8866/api/pdf/task_id

# 检查Minio配置
mc admin info myminio
```

### 错误4：连接超时

**可能原因**：
1. Minio服务未启动
2. 防火墙阻止
3. 网络不通

**排查方法**：
```bash
# 检查Minio是否运行
curl -I http://192.168.100.219:19000/minio/health/live

# 检查端口是否开放
telnet 192.168.100.219 19000

# 检查防火墙规则
firewall-cmd --list-all
```

## 调试技巧

### 1. 查看完整请求头

在Nginx配置中添加日志：

```nginx
location /tender-minio/ {
    # 记录详细的请求头
    access_log /var/log/nginx/minio_proxy.log combined;
    error_log /var/log/nginx/minio_proxy_error.log debug;
    
    # ... 其他配置
}
```

### 2. 使用curl调试

```bash
# 显示完整的请求和响应头
curl -v "http://192.168.100.219:8866/tender-minio/tender-pdf/xxx.pdf?X-Amz-Signature=..."

# 只显示响应头
curl -I "..."

# 下载文件到本地
curl -o test.pdf "..."
```

### 3. 浏览器开发者工具

1. 打开开发者工具（F12）
2. 切换到Network标签
3. 点击PDF链接
4. 查看请求详情：
   - Request URL：确认URL是否正确
   - Request Headers：检查是否包含所有必要参数
   - Response Headers：查看错误信息

## 性能优化建议

### 1. 启用Nginx缓存（可选）

```nginx
# 定义缓存路径
proxy_cache_path /var/cache/nginx/minio levels=1:2 keys_zone=minio_cache:10m max_size=1g inactive=24h;

location /tender-minio/ {
    # 使用缓存（注意：预签名URL会变，缓存要小心）
    proxy_cache minio_cache;
    proxy_cache_valid 200 1h;
    proxy_cache_key "$request_uri";
    
    # ... 其他配置
}
```

### 2. 启用Gzip压缩（不推荐用于PDF）

```nginx
location /tender-minio/ {
    # PDF文件已经是压缩格式，不建议再压缩
    gzip off;
    
    # ... 其他配置
}
```

### 3. 限速配置（可选）

```nginx
location /tender-minio/ {
    # 限制下载速度为5MB/s
    limit_rate 5m;
    
    # ... 其他配置
}
```

## 安全建议

### 1. 限制访问来源

```nginx
location /tender-minio/ {
    # 只允许特定IP访问
    allow 192.168.100.0/24;
    deny all;
    
    # ... 其他配置
}
```

### 2. 添加访问日志监控

```nginx
location /tender-minio/ {
    # 记录所有访问
    access_log /var/log/nginx/minio_access.log combined;
    
    # ... 其他配置
}
```

### 3. 防止盗链

```nginx
location /tender-minio/ {
    # 检查Referer
    valid_referers none blocked server_names *.example.com;
    if ($invalid_referer) {
        return 403;
    }
    
    # ... 其他配置
}
```

## 总结

**推荐方案**：使用Nginx代理 + 正确的Host头配置

**关键配置**：
```nginx
location /tender-minio/ {
    proxy_set_header Host 192.168.100.219:19000;  # 保持原始Host
    rewrite ^/tender-minio/(.*)$ /$1 break;        # 移除代理前缀
    proxy_pass http://192.168.100.219:19000;       # 转发到Minio
}
```

**代码改动**：
- ✅ `app/services/minio_service.py` - 生成两个URL
- ✅ `app/api/async_analyze.py` - API返回两个URL

**前端使用**：
```javascript
// 通过Nginx代理访问（推荐）
window.open(`${window.location.origin}${data.url_for_frontend}`);

// 或直接访问Minio（内网环境）
window.open(data.minio_url);
```

这样可以确保通过Nginx代理访问时，签名验证能够成功通过。