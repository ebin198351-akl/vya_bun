# 生产环境部署指南 / Production Deployment Guide

## 快速开始 / Quick Start

### 1. 构建生产文件 / Build Production Files

```bash
python build.py
```

这将创建 `dist/` 目录，包含所有优化后的生产文件。

This will create a `dist/` directory with all optimized production files.

### 2. 进入 dist 目录 / Navigate to dist

```bash
cd dist
```

### 3. 安装依赖 / Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. 配置邮箱 / Configure Email

编辑 `send_email.py`，确保 Gmail 应用密码已正确配置。

Edit `send_email.py` to ensure Gmail App Password is correctly configured.

### 5. 运行服务器 / Run Server

```bash
python server.py
```

服务器将在 http://localhost:8000 启动。

Server will start at http://localhost:8000.

## 优化说明 / Optimization Details

构建脚本已自动优化以下内容：

The build script has automatically optimized:

- **HTML**: 压缩了 33.3%（53KB → 36KB）
- **CSS**: 压缩了 27.3%（23KB → 17KB）
- **总文件大小**: 约 160MB（主要是图片资源）

## 生产环境建议 / Production Recommendations

### 使用 Nginx 作为反向代理 / Use Nginx as Reverse Proxy

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### 使用 Gunicorn 运行 Python 应用 / Use Gunicorn

```bash
pip install gunicorn
gunicorn -w 4 -b 127.0.0.1:8000 server:app
```

### 配置 HTTPS / Configure HTTPS

使用 Let's Encrypt 免费 SSL 证书：

```bash
sudo certbot --nginx -d your-domain.com
```

### 设置系统服务 / Set Up System Service

创建 `/etc/systemd/system/vya-kitchen.service`:

```ini
[Unit]
Description=Vya's Kitchen Web Server
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/dist
ExecStart=/usr/bin/python3 /path/to/dist/server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl enable vya-kitchen
sudo systemctl start vya-kitchen
```

## 文件结构 / File Structure

```
dist/
├── index.html          # 优化后的主页面
├── styles.css          # 优化后的样式文件
├── server.py           # Web 服务器
├── send_email.py       # 邮件发送功能
├── requirements.txt    # Python 依赖
├── image/              # 图片资源
└── README.md           # 说明文档
```

## 性能优化建议 / Performance Tips

1. **启用 Gzip 压缩** / Enable Gzip Compression
   - 在 Nginx 配置中启用 gzip
   - 可以进一步减少传输大小

2. **图片优化** / Image Optimization
   - 考虑使用 WebP 格式
   - 压缩大图片文件

3. **CDN 加速** / CDN Acceleration
   - 将静态资源（CSS、图片）放到 CDN
   - 使用 Cloudflare 或其他 CDN 服务

4. **缓存策略** / Caching Strategy
   - 设置适当的缓存头
   - 使用浏览器缓存减少请求

## 安全建议 / Security Recommendations

1. **防火墙配置** / Firewall Configuration
   - 只开放必要的端口（80, 443）
   - 限制 SSH 访问

2. **定期更新** / Regular Updates
   - 保持 Python 和依赖包最新
   - 定期检查安全漏洞

3. **备份策略** / Backup Strategy
   - 定期备份网站文件和数据库
   - 测试恢复流程

## 监控和日志 / Monitoring and Logging

建议使用以下工具监控网站：

Recommended monitoring tools:

- **Uptime Monitoring**: UptimeRobot, Pingdom
- **Error Tracking**: Sentry
- **Analytics**: Google Analytics
- **Server Monitoring**: New Relic, Datadog

## 故障排查 / Troubleshooting

### 邮件发送失败 / Email Sending Fails

1. 检查 Gmail 应用密码是否正确
2. 查看服务器日志获取详细错误信息
3. 确认防火墙允许 SMTP 连接（端口 587）

### 服务器无法启动 / Server Won't Start

1. 检查端口 8000 是否被占用
2. 确认 Python 版本（需要 Python 3.7+）
3. 检查依赖是否已安装

### 页面加载慢 / Slow Page Loading

1. 检查图片文件大小
2. 启用 Gzip 压缩
3. 考虑使用 CDN
4. 优化服务器配置

## 联系支持 / Support

如有问题，请查看：
- `GMAIL_SETUP.md` - Gmail 设置说明
- `README_EMAIL_SETUP.md` - 邮件配置说明

For issues, please check:
- `GMAIL_SETUP.md` - Gmail setup instructions
- `README_EMAIL_SETUP.md` - Email configuration guide

