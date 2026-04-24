"""DB query helpers — menus, weekly schedule, orders."""
from datetime import date
from typing import Optional

from db import get_conn


# ---------- menu items ----------

def list_menu_items(active_only: bool = False):
    sql = "SELECT * FROM menu_items"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY sort_order, id"
    with get_conn() as c:
        return [dict(r) for r in c.execute(sql).fetchall()]


def get_menu_item(item_id: int):
    with get_conn() as c:
        row = c.execute("SELECT * FROM menu_items WHERE id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def update_menu_item(item_id: int, *, price_cents=None, daily_cap=None,
                     active=None, sort_order=None):
    fields, vals = [], []
    for k, v in [
        ("price_cents", price_cents),
        ("daily_cap", daily_cap),
        ("active", active),
        ("sort_order", sort_order),
    ]:
        if v is not None:
            fields.append(f"{k} = ?")
            vals.append(v)
    if not fields:
        return
    vals.append(item_id)
    with get_conn() as c:
        c.execute(f"UPDATE menu_items SET {', '.join(fields)} WHERE id = ?", vals)
        c.commit()


# ---------- weekly menu ----------

def get_weekly(week_start: date):
    """Returns list of (position, menu_item_dict) sorted by position. Length 0..4."""
    with get_conn() as c:
        rows = c.execute(
            """SELECT wm.position, mi.*
               FROM weekly_menu wm
               JOIN menu_items mi ON mi.id = wm.menu_item_id
               WHERE wm.week_start_date = ?
               ORDER BY wm.position""",
            (week_start.isoformat(),),
        ).fetchall()
    return [(r["position"], dict(r)) for r in rows]


def set_weekly(week_start: date, position_to_item_id: dict):
    """Replace the weekly menu for week_start with the given map.

    position_to_item_id: {1: menu_item_id_or_None, 2: ..., 3: ..., 4: ...}
    Positions whose value is None/0 are removed.
    """
    iso = week_start.isoformat()
    with get_conn() as c:
        c.execute("DELETE FROM weekly_menu WHERE week_start_date = ?", (iso,))
        for pos, item_id in position_to_item_id.items():
            if not item_id:
                continue
            c.execute(
                "INSERT INTO weekly_menu (week_start_date, position, menu_item_id) "
                "VALUES (?, ?, ?)",
                (iso, int(pos), int(item_id)),
            )
        c.commit()


# ---------- orders ----------

def list_orders(status: Optional[str] = None, limit: int = 200):
    sql = "SELECT * FROM orders"
    args = []
    if status:
        sql += " WHERE payment_status = ?"
        args.append(status)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    with get_conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def get_order_with_items(order_id: int):
    with get_conn() as c:
        order = c.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not order:
            return None, []
        items = c.execute(
            "SELECT * FROM order_items WHERE order_id = ? ORDER BY id",
            (order_id,),
        ).fetchall()
    return dict(order), [dict(i) for i in items]
