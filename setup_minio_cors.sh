#!/bin/bash
# MinIO CORS 配置脚本
# 允许前端直接访问 MinIO 的预签名 URL

# 设置 MinIO 客户端别名（根据您的实际配置修改）
mc alias set myminio http://192.168.100.219:19000 minioadmin minioadmin

# 为 tender-pdf bucket 设置 CORS 策略
mc anonymous set-json /tmp/cors-config.json myminio/tender-pdf

# CORS 配置内容
cat > /tmp/cors-config.json << 'EOF'
{
  "CORSRules": [
    {
      "AllowedOrigins": [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000"
      ],
      "AllowedMethods": [
        "GET",
        "HEAD",
        "PUT",
        "POST"
      ],
      "AllowedHeaders": [
        "*"
      ],
      "ExposeHeaders": [
        "ETag",
        "Content-Length",
        "Content-Type"
      ],
      "MaxAgeSeconds": 3600
    }
  ]
}
EOF

echo "MinIO CORS 配置已应用到 tender-pdf bucket"
echo "现在前端应该可以直接访问 MinIO 的预签名 URL 了"
