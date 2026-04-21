import http.server
import socketserver
import os
import json
from send_email import send_contact_email


# 使用多线程混合类，避免SMTP阻塞整个服务器
class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """多线程HTTP服务器，每个请求在独立线程中处理"""
    daemon_threads = True  # 允许主线程退出时自动清理子线程
    allow_reuse_address = True  # 允许地址重用，快速重启


class ContactFormHandler(http.server.SimpleHTTPRequestHandler):
    # 设置超时时间（秒）
    timeout = 30
    
    def log_message(self, format, *args):
        """自定义日志格式，包含时间戳"""
        import sys
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sys.stderr.write(f"[{timestamp}] {format % args}\n")
    def do_POST(self):
        if self.path == "/api/contact":
            # Read the request body
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            
            try:
                # Parse JSON data
                data = json.loads(post_data.decode("utf-8"))
                name = data.get("name", "")
                phone = data.get("phone", "")
                email = data.get("email", "")
                message = data.get("message", "")
                
                # Validate required fields
                if not name or not message:
                    self.send_response(400)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "success": False,
                        "message": "Name and message are required"
                    }).encode())
                    return
                
                # Validate at least phone or email
                if not phone and not email:
                    self.send_response(400)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "success": False,
                        "message": "Please provide at least phone or email"
                    }).encode())
                    return
                
                # Send email
                success = send_contact_email(name, phone, email, message)
                
                if success:
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "success": True,
                        "message": "Email sent successfully"
                    }).encode())
                else:
                    self.send_response(500)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "success": False,
                        "message": "Failed to send email"
                    }).encode())
                    
            except Exception as e:
                import traceback
                error_msg = str(e)
                error_trace = traceback.format_exc()
                print(f"Error in contact form handler: {error_msg}")
                print(f"Traceback: {error_trace}")
                
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": False,
                    "message": error_msg
                }).encode())
        else:
            # Handle GET requests normally
            super().do_GET()
    
    def do_GET(self):
        # 健康检查端点
        if self.path == "/health" or self.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "message": "Server is running"
            }).encode())
            return
        # Serve static files
        super().do_GET()
    
    def do_OPTIONS(self):
        # Handle CORS preflight
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def run_server(port: int = None):
    """
    Start a simple HTTP server to serve the current directory (static files).
    
    After starting, open http://localhost:8000 in your browser.
    """
    import sys
    
    # 从环境变量读取端口，如果没有则使用默认值 8000
    if port is None:
        port = int(os.getenv("PORT", "8000"))
    
    # Serve files from the directory where this script is located
    web_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(web_dir)
    
    # 输出启动信息到 stderr，确保在后台运行时也能看到
    sys.stderr.write(f"[{__file__}] Starting server on port {port}...\n")
    sys.stderr.write(f"[{__file__}] Working directory: {os.getcwd()}\n")
    sys.stderr.flush()

    try:
        # 绑定到 0.0.0.0 以接受所有接口的连接（AWS 环境需要）
        httpd = ThreadingHTTPServer(("0.0.0.0", port), ContactFormHandler)
        # 设置服务器超时
        httpd.timeout = 30
        
        # 输出到 stdout 和 stderr，确保日志可见
        message = f"Serving Vya's Kitchen at http://0.0.0.0:{port} (accessible from all interfaces)\n"
        print(message)
        sys.stderr.write(message)
        sys.stderr.write(f"Health check: http://0.0.0.0:{port}/health\n")
        sys.stderr.write("Press Ctrl+C to stop the server.\n")
        sys.stderr.flush()
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            sys.stderr.write("\nShutting down server...\n")
            httpd.server_close()
        except Exception as e:
            sys.stderr.write(f"Server error: {e}\n")
            import traceback
            sys.stderr.write(traceback.format_exc())
            raise
    except OSError as e:
        error_msg = f"Failed to start server on port {port}: {e}\n"
        sys.stderr.write(error_msg)
        print(error_msg)
        # 如果是端口被占用，尝试查找并提示
        if "Address already in use" in str(e) or "address already in use" in str(e).lower():
            sys.stderr.write(f"Port {port} is already in use. Try:\n")
            sys.stderr.write(f"  - Kill the process using port {port}\n")
            sys.stderr.write(f"  - Use a different port by setting PORT environment variable\n")
        sys.exit(1)
    except Exception as e:
        error_msg = f"Unexpected error starting server: {e}\n"
        sys.stderr.write(error_msg)
        import traceback
        sys.stderr.write(traceback.format_exc())
        print(error_msg)
        sys.exit(1)


if __name__ == "__main__":
    # 支持从命令行参数读取端口
    import sys
    port = None
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port number: {sys.argv[1]}")
            sys.exit(1)
    run_server(port)
