"""Admin blueprint — password-gated, session-backed.

Mounted at /admin by app.py.
"""
import hmac
import os
from functools import wraps

from flask import (
    Blueprint, flash, redirect, render_template, request, session, url_for,
)

import models
from helpers import this_week_start, next_week_start, date_label

bp = Blueprint(
    "admin", __name__, template_folder="templates", static_folder="static",
)


# ---------- auth ----------

def _admin_password() -> str:
    return os.getenv("ADMIN_PASSWORD") or "changeme"


def admin_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if not session.get("is_admin"):
            return redirect(url_for("admin.login", next=request.path))
        return view(*a, **kw)
    return wrapper


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pw = request.form.get("password", "")
        if hmac.compare_digest(pw, _admin_password()):
            session["is_admin"] = True
            nxt = request.args.get("next") or url_for("admin.dashboard")
            return redirect(nxt)
        flash("密码错误 Wrong password", "error")
    return render_template("admin/login.html")


@bp.route("/logout")
def logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin.login"))


# ---------- pages ----------

@bp.route("/")
@admin_required
def dashboard():
    items = models.list_menu_items()
    weekly_now = models.get_weekly(this_week_start())
    weekly_next = models.get_weekly(next_week_start())
    pending = models.list_orders(status="pending", limit=10)
    confirmed = models.list_orders(status="confirmed", limit=10)

    # Compute today's order-window state (for the sold-out one-click button)
    from helpers import next_delivery_date
    from db import get_conn
    target = next_delivery_date()
    with get_conn() as c:
        soldout_count = c.execute(
            "SELECT COUNT(*) FROM daily_soldout WHERE delivery_date=?",
            (target.isoformat(),),
        ).fetchone()[0]
    active_total = sum(1 for i in items if i["active"])
    is_all_soldout = active_total > 0 and soldout_count >= active_total

    return render_template(
        "admin/dashboard.html",
        items=items,
        weekly_now=weekly_now,
        weekly_next=weekly_next,
        pending=pending,
        confirmed=confirmed,
        paid=confirmed,  # template back-compat
        target_date=target,
        target_label=date_label(target, "zh"),
        soldout_count=soldout_count,
        is_all_soldout=is_all_soldout,
        this_week_start=this_week_start(),
        next_week_start=next_week_start(),
        date_label=date_label,
    )


@bp.route("/menu", methods=["GET", "POST"])
@admin_required
def menu():
    if request.method == "POST":
        # Bulk update: each item posts price/cap/active
        items = models.list_menu_items()
        for it in items:
            iid = it["id"]
            price_str = request.form.get(f"price_{iid}")
            cap_str = request.form.get(f"cap_{iid}")
            active = 1 if request.form.get(f"active_{iid}") else 0
            try:
                price_cents = int(round(float(price_str) * 100)) if price_str else None
            except ValueError:
                price_cents = None
            try:
                cap = int(cap_str) if cap_str else None
            except ValueError:
                cap = None
            models.update_menu_item(
                iid, price_cents=price_cents, daily_cap=cap, active=active,
            )
        flash("菜单已保存 Menu saved", "ok")
        return redirect(url_for("admin.menu"))
    items = models.list_menu_items()
    return render_template("admin/menu.html", items=items)


@bp.route("/weekly", methods=["GET", "POST"])
@admin_required
def weekly():
    this_ws = this_week_start()
    next_ws = next_week_start()

    if request.method == "POST":
        which = request.form.get("which")  # 'this' | 'next'
        ws = this_ws if which == "this" else next_ws
        mapping = {}
        for pos in (1, 2, 3, 4):
            val = request.form.get(f"slot_{pos}")
            mapping[pos] = int(val) if val and val != "0" else None
        models.set_weekly(ws, mapping)
        flash(f"本{'周' if which == 'this' else '下周'}菜单已保存", "ok")
        return redirect(url_for("admin.weekly"))

    items = models.list_menu_items(active_only=True)
    return render_template(
        "admin/weekly.html",
        items=items,
        this_ws=this_ws,
        next_ws=next_ws,
        weekly_now=dict(models.get_weekly(this_ws)),
        weekly_next=dict(models.get_weekly(next_ws)),
        date_label=date_label,
    )


@bp.route("/orders")
@admin_required
def orders():
    status = request.args.get("status") or None
    rows = models.list_orders(status=status)
    return render_template("admin/orders.html", orders=rows, status=status)


@bp.route("/orders/<int:oid>")
@admin_required
def order_detail(oid):
    order, items = models.get_order_with_items(oid)
    if not order:
        return "Not found", 404
    return render_template("admin/order_detail.html", order=order, items=items)


@bp.route("/orders/<int:oid>/confirm", methods=["POST"])
@admin_required
def order_confirm(oid):
    note = (request.form.get("note") or "").strip() or None
    return _change_status(oid, "confirmed", reason=None, admin_note=note)


@bp.route("/orders/<int:oid>/reject", methods=["POST"])
@admin_required
def order_reject(oid):
    reason = (request.form.get("reason") or "").strip() or None
    return _change_status(oid, "cancelled", reason=reason)


@bp.route("/soldout", methods=["POST"])
@admin_required
def soldout_mark_all():
    """One-click: mark every active item in this week's menu as sold-out
    for the next-delivery-date. Used when offline orders exhaust capacity."""
    from db import get_conn
    from datetime import date as _date
    target_str = (request.form.get("date") or "").strip()
    try:
        target = _date.fromisoformat(target_str) if target_str else None
    except ValueError:
        target = None
    if not target:
        from helpers import next_delivery_date
        target = next_delivery_date()

    items = models.list_menu_items(active_only=True)
    with get_conn() as c:
        for it in items:
            c.execute(
                "INSERT OR IGNORE INTO daily_soldout(delivery_date, menu_item_id) "
                "VALUES (?, ?)", (target.isoformat(), it["id"]),
            )
        c.commit()
    flash(f"✓ 送达日 {target.isoformat()} 全部标记为售罄,前台立刻显示", "ok")
    return redirect(url_for("admin.dashboard"))


@bp.route("/soldout/clear", methods=["POST"])
@admin_required
def soldout_clear():
    """Undo the sold-out flag — restore normal sales for the given date."""
    from db import get_conn
    from datetime import date as _date
    target_str = (request.form.get("date") or "").strip()
    try:
        target = _date.fromisoformat(target_str)
    except ValueError:
        from helpers import next_delivery_date
        target = next_delivery_date()
    with get_conn() as c:
        c.execute("DELETE FROM daily_soldout WHERE delivery_date=?",
                  (target.isoformat(),))
        c.commit()
    flash(f"✓ 送达日 {target.isoformat()} 恢复销售", "ok")
    return redirect(url_for("admin.dashboard"))


@bp.route("/orders/<int:oid>/mark-delivered", methods=["POST"])
@admin_required
def order_mark_delivered(oid):
    # No customer notification for "delivered" — silent state change.
    from db import get_conn
    with get_conn() as c:
        c.execute(
            "UPDATE orders SET payment_status='delivered' WHERE id=?", (oid,),
        )
        c.commit()
    flash(f"订单 #{oid} 已标记为送达", "ok")
    return redirect(url_for("admin.order_detail", oid=oid))


def _change_status(oid: int, new_status: str, reason, admin_note=None):
    from db import get_conn
    import notify
    with get_conn() as c:
        cur = c.cursor()
        row = cur.execute(
            "SELECT payment_status FROM orders WHERE id=?", (oid,),
        ).fetchone()
        if not row:
            return "Not found", 404
        cur.execute(
            "UPDATE orders SET payment_status=?, paid_at=datetime('now') WHERE id=?",
            (new_status, oid),
        )
        c.commit()
    order, items = models.get_order_with_items(oid)
    event = "confirmed" if new_status == "confirmed" else "rejected"
    try:
        notify.notify_event(order, items, event, reason=reason,
                            admin_note=admin_note,
                            to_kitchen=True, to_customer=True)
    except Exception as e:
        print(f"[admin] notify failed: {e}")
    label = {"confirmed": "已确认 ✓", "cancelled": "已拒绝 / 取消"}[new_status]
    flash(f"订单 #{oid} {label} — 已发邮件 + 短信通知客户", "ok")
    return redirect(url_for("admin.order_detail", oid=oid))
