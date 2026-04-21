"""
Email sending utility for contact form
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# Try to load environment variables if dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

def send_contact_email(name, phone, email, message):
    """
    Send contact form email to Gmail
    
    Args:
        name: Customer name
        phone: Customer phone (optional)
        email: Customer email (optional)
        message: Customer message
    
    Returns:
        bool: True if sent successfully, False otherwise
    """
    # Gmail SMTP settings
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    
    # Get credentials from environment variables
    # IMPORTANT: Gmail requires App Password, not regular password!
    # See GMAIL_SETUP.md for instructions on creating App Password
    sender_email = os.getenv("GMAIL_USER", "vya2025.kitchen@gmail.com")
    # App Password must be provided via GMAIL_APP_PASSWORD env var (see .env.example)
    sender_password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
    
    recipient_email = "yawen4092@gmail.com"
    
    # Create message
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg["Subject"] = f"咨询 - Vya's Kitchen - {name}"
    
    # Build email body
    body = f"""新咨询来自 Vya's Kitchen 网站

姓名 / Name: {name}
"""
    
    if phone:
        body += f"手机 / Phone: {phone}\n"
    
    if email:
        body += f"邮箱 / Email: {email}\n"
    
    body += f"""
咨询问题 / Message:
{message}

---
此邮件由 Vya's Kitchen 网站联系表单自动发送
"""
    
    msg.attach(MIMEText(body, "plain", "utf-8"))
    
    server = None
    try:
        # Connect to server and send email with timeout
        # 设置连接超时和读取超时，防止挂起
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, recipient_email, text)
        return True
    except Exception as e:
        import traceback
        error_msg = str(e)
        error_trace = traceback.format_exc()
        print(f"Error sending email: {error_msg}")
        print(f"Traceback: {error_trace}")
        return False
    finally:
        # 确保连接总是被正确关闭，即使出现异常
        if server is not None:
            try:
                server.quit()
            except Exception as e:
                # 如果quit失败，尝试close
                try:
                    server.close()
                except:
                    pass
                print(f"Warning: Error closing SMTP connection: {e}")

