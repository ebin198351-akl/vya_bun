"""Notifications — email customer + email kitchen + SMS customer.

Three event types in the reservation flow:
  - "received"  : just submitted, kitchen will review
  - "confirmed" : kitchen approved, will deliver as agreed
  - "rejected"  : kitchen cannot fulfill (with optional reason)

Best-effort: each channel failing is logged but doesn't block others.
"""
import os
import smtplib
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional


KITCHEN_EMAIL = os.getenv("ORDER_NOTIFY_EMAIL", "yawen4092@gmail.com")
GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_PASS = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
WECHAT = "ya312322063"
PUBLIC_BASE = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def order_link(order: dict) -> str:
    """Tokenised customer-facing link to the order status page."""
    from helpers import make_order_token
    return f"{PUBLIC_BASE}/order/{order['id']}?t={make_order_token(order['id'])}"


# ---------- email plumbing ----------

def _smtp_send(to_email: str, subject: str, body: str) -> bool:
    if not GMAIL_USER or not GMAIL_PASS:
        print(f"[notify] Gmail not configured; would email {to_email}: {subject}")
        return False
    msg = MIMEMultipart()
    msg["From"] = f"Vya's Kitchen 薇雅厨房 <{GMAIL_USER}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    server = None
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_PASS)
        server.sendmail(GMAIL_USER, to_email, msg.as_string())
        return True
    except Exception:
        print(f"[notify] email failed: {traceback.format_exc()}")
        return False
    finally:
        if server:
            try: server.quit()
            except Exception: pass


def _items_block(items: list) -> str:
    return "\n".join(
        f"  • {i['name_snapshot']} × {i['quantity']} = "
        f"NZ$ {(i['unit_price_cents']*i['quantity'])/100:.2f}"
        for i in items
    )


# ---------- customer emails ----------

_DIVIDER = "\n\n" + "─" * 40 + "\n\n"  # visual separator between zh and en


def email_customer(order: dict, items: list, event: str,
                   reason: Optional[str] = None,
                   admin_note: Optional[str] = None) -> bool:
    """event in {received, confirmed, rejected}.

    Always sends a BILINGUAL email (Chinese section + divider + English section),
    regardless of order.language. Subject also bilingual.
    """
    if not order.get("email"):
        return False
    name = order["customer_name"]
    oid = order["id"]
    total = f"NZ$ {order['total_cents']/100:.2f}"
    items_block = _items_block(items)
    link = order_link(order)

    if event == "received":
        subject = f"【薇雅厨房】预约已收到 #{oid} · Reservation received #{oid}"
        zh = (
            f"亲爱的 {name},\n\n"
            f"感谢您的预约!我们已收到订单 #{oid},以下是您提交的内容:\n\n"
            f"送达日期(预约): {order['delivery_date']}\n"
            f"送达地址: {order['address']}\n"
            f"联系电话: {order['phone']}\n\n"
            f"商品:\n{items_block}\n\n"
            f"预估合计: {total}\n\n"
            f"我们会尽快与您确认 库存 / 送达时间 / 配送地址,确认后会再次发"
            f"邮件和短信通知您。\n\n"
            f"📋 随时查看订单状态:\n{link}\n\n"
            f"如有疑问请微信联系: {WECHAT}\n\n"
            f"—— 薇雅厨房"
        )
        en = (
            f"Hi {name},\n\n"
            f"Thanks for your reservation! We've received order #{oid}:\n\n"
            f"Requested delivery: {order['delivery_date']}\n"
            f"Address: {order['address']}\n"
            f"Phone: {order['phone']}\n\n"
            f"Items:\n{items_block}\n\n"
            f"Estimated total: {total}\n\n"
            f"We'll confirm stock, delivery time and address as soon as possible "
            f"and notify you again by email + SMS.\n\n"
            f"📋 Check your order status anytime:\n{link}\n\n"
            f"Questions? WeChat {WECHAT}\n\n"
            f"—— Vya's Kitchen"
        )
    elif event == "confirmed":
        subject = f"【薇雅厨房】订单已确认 #{oid} · Order confirmed #{oid}"
        note_zh = f"\n💬 厨房补充:\n{admin_note}\n" if admin_note else ""
        note_en = f"\n💬 Note from kitchen:\n{admin_note}\n" if admin_note else ""
        zh = (
            f"亲爱的 {name},\n\n"
            f"好消息!您的订单 #{oid} 已确认 ✓\n\n"
            f"确认送达日: {order['delivery_date']}\n"
            f"送达地址: {order['address']}\n"
            f"商品:\n{items_block}\n\n"
            f"合计: {total}\n"
            f"{note_zh}\n"
            f"我们会在送达前 30-60 分钟再发短信提醒。\n\n"
            f"📋 订单详情:\n{link}\n\n"
            f"如有任何问题请微信: {WECHAT}\n\n"
            f"—— 薇雅厨房"
        )
        en = (
            f"Hi {name},\n\n"
            f"Great news — your order #{oid} is confirmed ✓\n\n"
            f"Delivery: {order['delivery_date']}\n"
            f"Address: {order['address']}\n"
            f"Items:\n{items_block}\n\n"
            f"Total: {total}\n"
            f"{note_en}\n"
            f"We'll text you 30-60 minutes before delivery.\n\n"
            f"📋 Order detail:\n{link}\n\n"
            f"Questions? WeChat {WECHAT}\n\n"
            f"—— Vya's Kitchen"
        )
    elif event == "rejected":
        subject = (
            f"【薇雅厨房】很抱歉,订单无法接受 #{oid} · "
            f"Cannot accept order #{oid}"
        )
        zh = (
            f"亲爱的 {name},\n\n"
            f"很抱歉,您的订单 #{oid} 暂时无法接受。\n\n"
        )
        if reason:
            zh += f"原因:\n{reason}\n\n"
        zh += (
            f"如想调整数量、口味或日期,欢迎微信联系我们重新预约: {WECHAT}\n\n"
            f"—— 薇雅厨房"
        )
        en = (
            f"Hi {name},\n\n"
            f"Sorry — we're unable to accept order #{oid} at this time.\n\n"
        )
        if reason:
            en += f"Reason:\n{reason}\n\n"
        en += (
            f"Feel free to WeChat us at {WECHAT} to adjust quantity, flavours "
            f"or date and try again.\n\n"
            f"—— Vya's Kitchen"
        )
    else:
        return False
    body = zh + _DIVIDER + en
    return _smtp_send(order["email"], subject, body)


# ---------- kitchen email (one shape, sent on every state change) ----------

def email_kitchen(order: dict, items: list, event: str,
                  reason: Optional[str] = None) -> bool:
    label = {
        "received":  "新预约待审核",
        "confirmed": "订单已确认(由你)",
        "rejected":  "订单已拒绝(由你)",
    }.get(event, event)
    items_block = _items_block(items)
    subject = (
        f"【{label}】#{order['id']} – {order['customer_name']} – "
        f"NZ$ {order['total_cents']/100:.2f}"
    )
    body = (
        f"{label} #{order['id']}\n"
        f"{'=' * 40}\n\n"
        f"客户: {order['customer_name']}\n"
        f"电话: {order['phone']}\n"
        f"邮箱: {order.get('email') or '—'}\n"
        f"地址: {order['address']}\n"
        f"距离: {order.get('distance_km') or '—'} km\n"
        f"送达日期: {order['delivery_date']}\n\n"
        f"商品:\n{items_block}\n\n"
        f"合计: NZ$ {order['total_cents']/100:.2f}\n\n"
        f"客户备注: {order.get('notes') or '—'}\n"
    )
    if event == "received":
        body += (
            f"\n=== 操作 ===\n"
            f"请到后台审核 → 确认或拒绝:\n"
            f"  /admin/orders/{order['id']}\n"
        )
    if reason:
        body += f"\n拒绝原因(已发给客户):\n{reason}\n"
    return _smtp_send(KITCHEN_EMAIL, subject, body)


# ---------- SMS ----------

def _send_sms(to_phone: str, body: str) -> bool:
    sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    tok = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    sender = os.getenv("TWILIO_FROM", "VyaKitchen").strip()
    if not sid or not tok:
        print(f"[notify] Twilio not configured; would SMS {to_phone}")
        return False
    try:
        from twilio.rest import Client
    except ImportError:
        print("[notify] twilio library not installed")
        return False
    try:
        client = Client(sid, tok)
        msg = client.messages.create(body=body, from_=sender, to=to_phone)
        print(f"[notify] sms sent sid={msg.sid}")
        return True
    except Exception:
        print(f"[notify] sms failed: {traceback.format_exc()}")
        return False


def sms_customer(order: dict, event: str, reason: Optional[str] = None,
                 admin_note: Optional[str] = None) -> bool:
    """Bilingual SMS — Chinese first, then English on a new line.

    Heads-up on cost:
      - Chinese chars force UCS-2 encoding → 70 chars / segment
      - Typical bilingual confirm ≈ 150-220 chars → 3-4 segments per message
      - NZ ~NZ$0.10 × 3 ≈ $0.30 per notification. Budget accordingly.
    """
    oid = order["id"]
    total = f"NZ$ {order['total_cents']/100:.2f}"
    link = order_link(order)
    # Clip admin note so we don't blow segment count
    note_short = (admin_note or "").strip()
    if len(note_short) > 60:
        note_short = note_short[:57] + "…"

    if event == "received":
        zh = f"【薇雅厨房】预约 #{oid} 已收到,我们会尽快确认。详情 {link}"
        en = f"[Vya] Reservation #{oid} received, confirming soon. Track: {link}"
    elif event == "confirmed":
        note_zh = f" 备注:{note_short}" if note_short else ""
        note_en = f" Note: {note_short}" if note_short else ""
        zh = (
            f"【薇雅厨房】订单 #{oid} 已确认 ✓ 送达 {order['delivery_date']}"
            f",合计 {total}。{note_zh}"
        )
        en = (
            f"[Vya] Order #{oid} confirmed ✓ Delivery {order['delivery_date']}, "
            f"total {total}.{note_en} {link}"
        )
    elif event == "rejected":
        rsn_zh = f" 原因:{reason}" if reason else ""
        rsn_en = f" Reason: {reason}" if reason else ""
        zh = (
            f"【薇雅厨房】很抱歉,订单 #{oid} 无法接受。{rsn_zh}"
            f" 想再下单请微信 {WECHAT}"
        )
        en = (
            f"[Vya] Sorry, can't accept order #{oid}.{rsn_en} "
            f"WeChat {WECHAT} to try again."
        )
    else:
        return False
    body = f"{zh}\n{en}"
    return _send_sms(order["phone"], body)


# ---------- top-level ----------

def notify_event(order: dict, items: list, event: str,
                 reason: Optional[str] = None,
                 admin_note: Optional[str] = None,
                 to_kitchen: bool = True,
                 to_customer: bool = True):
    """Fan out a single event to all enabled channels. Failures don't propagate."""
    if to_kitchen:
        try: email_kitchen(order, items, event, reason)
        except Exception as e: print(f"[notify] email_kitchen failed: {e}")
    if to_customer:
        try: email_customer(order, items, event, reason, admin_note)
        except Exception as e: print(f"[notify] email_customer failed: {e}")
        try: sms_customer(order, event, reason, admin_note)
        except Exception as e: print(f"[notify] sms_customer failed: {e}")


# ---------- backward-compat shims (used elsewhere) ----------

def email_customer_order(order: dict, items: list) -> bool:
    return email_customer(order, items, "confirmed")

def email_kitchen_order(order: dict, items: list) -> bool:
    return email_kitchen(order, items, "received")

def sms_customer_order(order: dict) -> bool:
    return sms_customer(order, "confirmed")

def notify_paid_order(order: dict, items: list):
    notify_event(order, items, "confirmed")
