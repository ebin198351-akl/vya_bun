"""
Build script for production deployment
Creates optimized files in dist/ directory
"""
import os
import shutil
import re
from pathlib import Path

def minify_html(content):
    """Minify HTML content - preserve script and style content"""
    # Protect script and style tags
    protected = []
    
    def protect_script_style(match):
        protected_content = match.group(0)
        protected.append(protected_content)
        return f'__PROTECTED_{len(protected)-1}__'
    
    # Protect <script> tags (including inline JavaScript)
    content = re.sub(r'<script[^>]*>.*?</script>', protect_script_style, content, flags=re.DOTALL | re.IGNORECASE)
    # Protect <style> tags
    content = re.sub(r'<style[^>]*>.*?</style>', protect_script_style, content, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove HTML comments
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    # Remove extra whitespace
    content = re.sub(r'\s+', ' ', content)
    # Remove whitespace between tags
    content = re.sub(r'>\s+<', '><', content)
    
    # Restore protected content
    for i, protected_content in enumerate(protected):
        content = content.replace(f'__PROTECTED_{i}__', protected_content)
    
    return content.strip()

def minify_css(content):
    """Minify CSS content"""
    # Remove comments
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    # Remove extra whitespace
    content = re.sub(r'\s+', ' ', content)
    # Remove whitespace around specific characters
    content = re.sub(r'\s*([{}:;,])\s*', r'\1', content)
    # Remove trailing semicolons
    content = re.sub(r';}', '}', content)
    return content.strip()

def minify_js(content):
    """Minify JavaScript content - be careful with string literals"""
    # First, protect string literals
    strings = []
    string_pattern = r'(["\'`])(?:(?=(\\?))\2.)*?\1'
    
    def replace_string(match):
        strings.append(match.group(0))
        return f'__STRING_{len(strings)-1}__'
    
    # Protect strings
    content = re.sub(string_pattern, replace_string, content)
    
    # Remove single-line comments (but preserve URLs)
    content = re.sub(r'//(?!https?://).*?$', '', content, flags=re.MULTILINE)
    # Remove multi-line comments
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    # Remove extra whitespace (but keep newlines in some cases)
    content = re.sub(r'[ \t]+', ' ', content)
    # Remove whitespace around specific operators (but be careful)
    content = re.sub(r'\s*([=+\-*/%<>!&|,;])\s*', r'\1', content)
    # Remove whitespace around brackets (but keep structure)
    content = re.sub(r'\s*([{}()\[\]])\s*', r'\1', content)
    
    # Restore strings
    for i, string in enumerate(strings):
        content = content.replace(f'__STRING_{i}__', string)
    
    return content.strip()

def copy_and_optimize_file(src_path, dst_path, file_type):
    """Copy and optimize a file"""
    print(f"Processing {src_path}...")
    
    with open(src_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if file_type == 'html':
        content = minify_html(content)
    elif file_type == 'css':
        content = minify_css(content)
    elif file_type == 'js':
        content = minify_js(content)
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    
    with open(dst_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Get file sizes
    src_size = os.path.getsize(src_path)
    dst_size = os.path.getsize(dst_path)
    reduction = ((src_size - dst_size) / src_size * 100) if src_size > 0 else 0
    print(f"  {src_size} bytes -> {dst_size} bytes ({reduction:.1f}% reduction)")

def build_production():
    """Build production-ready files"""
    print("=" * 60)
    print("Building production files...")
    print("=" * 60)
    
    # Create dist directory
    dist_dir = Path("dist")
    if not dist_dir.exists():
        dist_dir.mkdir()
    else:
        print("Cleaning dist directory...")
        # Try to remove individual files instead of entire directory
        try:
            for item in dist_dir.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
        except Exception as e:
            print(f"Warning: Could not clean some files: {e}")
            print("Continuing with build...")
    
    # Copy and optimize HTML
    print("\n[1/4] Processing HTML files...")
    copy_and_optimize_file("index.html", "dist/index.html", "html")
    
    # Copy and optimize CSS
    print("\n[2/4] Processing CSS files...")
    copy_and_optimize_file("styles.css", "dist/styles.css", "css")
    
    # Copy Python files
    print("\n[3/4] Copying Python files...")
    python_files = ["server.py", "send_email.py"]
    for py_file in python_files:
        if os.path.exists(py_file):
            shutil.copy2(py_file, f"dist/{py_file}")
            print(f"  Copied {py_file}")
    
    # Copy requirements.txt
    if os.path.exists("requirements.txt"):
        shutil.copy2("requirements.txt", "dist/requirements.txt")
        print("  Copied requirements.txt")
    
    # Copy image directory
    print("\n[4/4] Copying image directory...")
    if os.path.exists("image"):
        shutil.copytree("image", "dist/image", dirs_exist_ok=True)
        print("  Copied image/ directory")
    
    # Create production README
    readme_content = """# Vya's Kitchen - Production Deployment

## 部署说明 / Deployment Instructions

### 1. 安装依赖 / Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. 配置邮箱 / Configure Email

编辑 `send_email.py`，确保 Gmail 应用密码已正确配置。

Edit `send_email.py` to ensure Gmail App Password is correctly configured.

### 3. 运行服务器 / Run Server

```bash
python server.py
```

服务器将在 http://localhost:8000 启动。

Server will start at http://localhost:8000.

### 4. 生产环境建议 / Production Recommendations

- 使用专业的 Web 服务器（如 Nginx）作为反向代理
- 使用 Gunicorn 或 uWSGI 运行 Python 应用
- 配置 HTTPS/SSL 证书
- 设置防火墙规则
- 定期备份数据

- Use professional web server (e.g., Nginx) as reverse proxy
- Use Gunicorn or uWSGI to run Python application
- Configure HTTPS/SSL certificate
- Set up firewall rules
- Regular data backups

## 文件说明 / File Structure

- `index.html` - 主页面（已优化压缩）
- `styles.css` - 样式文件（已优化压缩）
- `server.py` - Web 服务器
- `send_email.py` - 邮件发送功能
- `image/` - 图片资源目录

## 优化说明 / Optimization Notes

所有前端文件已进行压缩优化：
- HTML: 移除注释和多余空白
- CSS: 压缩样式代码
- 文件大小已减少，加载速度更快

All frontend files have been minified:
- HTML: Comments and extra whitespace removed
- CSS: Style code compressed
- File sizes reduced for faster loading
"""
    
    with open("dist/README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("  Created README.md")
    
    print("\n" + "=" * 60)
    print("Build completed! Files are in dist/ directory")
    print("=" * 60)
    
    # Calculate total size
    total_size = sum(
        os.path.getsize(os.path.join(dirpath, filename))
        for dirpath, dirnames, filenames in os.walk(dist_dir)
        for filename in filenames
    )
    print(f"\nTotal production build size: {total_size / 1024:.2f} KB")

if __name__ == "__main__":
    try:
        build_production()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

