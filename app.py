"""Flask app — public site + JSON API + admin blueprint mount.

Static frontend (index.html, styles.css, image/*) is served from the project
root with an extension allowlist so source files stay private.
"""
import json
import os
import secrets
from pathlib import Path

from datetime import date as _date, datetime as _dt, timedelta as _td

from flask import (
    Flask, abort, jsonify, redirect, render_template, request,
    send_from_directory, url_for,
)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from db import init_db, get_conn
from send_email import send_contact_email
from admin import bp as admin_bp
from helpers import (
    next_delivery_date, this_week_start, next_week_start, date_label,
    closed_weekdays, today_nz, make_order_token, verify_order_token,
)
import models
import distance
import payments
import notify


ROOT = Path(__file__).parent
SAFE_EXTS = {".html", ".css", ".js", ".jpg", ".jpeg", ".png", ".gif",
             ".svg", ".webp", ".ico", ".woff", ".woff2", ".ttf",
             ".pdf", ".txt", ".webmanifest"}

# Site canonical base — used inside schema URLs. Falls back to a sensible
# default for production; can be overridden via env at deploy time.
SITE_BASE = os.getenv("PUBLIC_BASE_URL", "https://vya.co.nz").rstrip("/")

CATEGORY_LABELS = {
    "pork":    ("猪肉",   "Pork"),
    "beef":    ("牛肉",   "Beef"),
    "chicken": ("鸡肉",   "Chicken"),
    "veg":     ("素食",   "Vegetarian"),
}


def _allergens_for(name_zh: str, meat_zh: str) -> list:
    """Heuristic allergen detection per item."""
    blob = (name_zh or "") + " " + (meat_zh or "")
    a = ["wheat (gluten)", "soy", "sesame"]
    if any(k in blob for k in ("虾", "shrimp", "shellfish")):
        a.append("crustaceans")
    if any(k in blob for k in ("鸡蛋", "蛋", "egg")):
        a.append("eggs")
    if any(k in blob for k in ("花生", "peanut")):
        a.append("peanuts")
    return a


def _build_menu_jsonld() -> str:
    """Render <script type=application/ld+json> with full Menu / MenuItem tree.

    Pulled from menu_items live so the schema reflects current price + active
    status. Sections are grouped by category (pork/beef/chicken/veg).
    """
    items = models.list_menu_items(active_only=True)
    sections = {}  # category → list of items
    for it in items:
        sections.setdefault(it["category"] or "other", []).append(it)

    menu_sections = []
    for cat, label in CATEGORY_LABELS.items():
        if cat not in sections:
            continue
        zh, en = label
        menu_items_jsonld = []
        for it in sections[cat]:
            allergens = _allergens_for(it["name_zh"], it["meat_zh"])
            desc_parts = []
            if it.get("desc_zh"): desc_parts.append(it["desc_zh"])
            if it.get("desc_en"): desc_parts.append(it["desc_en"])
            desc_parts.append(f"Allergens: {', '.join(allergens)}.")
            mi = {
                "@type": "MenuItem",
                "@id": f"{SITE_BASE}/#menu/{it['sku']}",
                "name": f"{it['name_zh']} ({it['name_en']})",
                "description": "  ".join(desc_parts),
                "image": f"{SITE_BASE}/{it['image']}" if it.get("image") else None,
                "offers": {
                    "@type": "Offer",
                    "price": f"{it['price_cents']/100:.2f}",
                    "priceCurrency": "NZD",
                    "availability": "https://schema.org/InStock",
                    "url": f"{SITE_BASE}/#menu",
                },
            }
            if cat == "veg":
                mi["suitableForDiet"] = "https://schema.org/VegetarianDiet"
            # remove None fields
            mi = {k: v for k, v in mi.items() if v is not None}
            menu_items_jsonld.append(mi)

        menu_sections.append({
            "@type": "MenuSection",
            "name": f"{zh} {en}",
            "hasMenuItem": menu_items_jsonld,
        })

    menu_doc = {
        "@context": "https://schema.org",
        "@type": "Menu",
        "@id": f"{SITE_BASE}/#menu",
        "name": "薇雅厨房菜单 / Vya's Kitchen Menu",
        "url": f"{SITE_BASE}/#menu",
        "inLanguage": ["zh-CN", "en"],
        "description": (
            "Weekly rotating handmade Chinese buns — each week features 4 of the "
            "below SKUs, made fresh and steamed to order. Auckland delivery."
        ),
        "hasMenuSection": menu_sections,
    }
    return (
        '<script type="application/ld+json">\n'
        + json.dumps(menu_doc, ensure_ascii=False, indent=2)
        + '\n    </script>'
    )


def create_app():
    app = Flask(__name__, static_folder=None)
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET") or secrets.token_hex(32)
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2 MB
    # Always re-read templates from disk so editing .html files takes effect
    # without restarting. Cheap (single dev server, low traffic).
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True

    init_db()
    app.register_blueprint(admin_bp, url_prefix="/admin")

    # ---------- public static / SPA ----------

    @app.route("/")
    def index():
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        marker = "<!-- MENU_JSONLD -->"
        if marker in html:
            html = html.replace(marker, _build_menu_jsonld())
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}

    @app.route("/<path:filename>")
    def static_proxy(filename):
        # block any traversal or hidden file
        if ".." in filename or filename.startswith("."):
            abort(404)
        target = (ROOT / filename).resolve()
        if not str(target).startswith(str(ROOT.resolve())):
            abort(404)
        if target.suffix.lower() not in SAFE_EXTS:
            abort(404)
        if not target.is_file():
            abort(404)
        rel = target.relative_to(ROOT)
        return send_from_directory(ROOT, str(rel))

    # ---------- JSON APIs ----------

    @app.route("/api/contact", methods=["POST"])
    def api_contact():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        phone = (data.get("phone") or "").strip()
        email = (data.get("email") or "").strip()
        message = (data.get("message") or "").strip()
        if not name or not message:
            return jsonify(success=False, error="Name and message required"), 400
        ok = send_contact_email(name, phone, email, message)
        if ok:
            return jsonify(success=True, message="发送成功 / Sent successfully")
        return jsonify(success=False, error="Failed to send email"), 500

    @app.route("/health")
    def health():
        return jsonify(status="ok")

    # ---------- SEO: robots + sitemap ----------

    @app.route("/robots.txt")
    def robots_txt():
        base = request.url_root.rstrip("/")
        body = (
            "User-agent: *\n"
            "Allow: /\n"
            "Disallow: /admin/\n"
            "Disallow: /admin\n"
            "Disallow: /checkout\n"
            "Disallow: /track\n"
            "Disallow: /order/\n"
            "Disallow: /api/\n"
            f"Sitemap: {base}/sitemap.xml\n"
        )
        return body, 200, {"Content-Type": "text/plain; charset=utf-8"}

    @app.route("/sitemap.xml")
    def sitemap_xml():
        base = request.url_root.rstrip("/")
        today_iso = today_nz().isoformat()
        urls = [
            ("/",          "1.0", "weekly"),
            ("/#menu",     "0.9", "weekly"),
            ("/#about",    "0.6", "monthly"),
            ("/#gallery",  "0.5", "monthly"),
            ("/#order",    "0.7", "monthly"),
            ("/#location", "0.7", "yearly"),
            ("/#group",    "0.6", "monthly"),
        ]
        out = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for path, prio, freq in urls:
            out.append(
                f"  <url><loc>{base}{path}</loc>"
                f"<lastmod>{today_iso}</lastmod>"
                f"<changefreq>{freq}</changefreq>"
                f"<priority>{prio}</priority></url>"
            )
        out.append("</urlset>")
        return "\n".join(out), 200, {"Content-Type": "application/xml; charset=utf-8"}

    # ---------- Menu APIs ----------

    def _serialize_item(it: dict) -> dict:
        return {
            "id": it["id"],
            "sku": it["sku"],
            "name_zh": it["name_zh"],
            "name_en": it["name_en"],
            "desc_zh": it["desc_zh"],
            "desc_en": it["desc_en"],
            "image": it["image"],
            "tag_zh": it["tag_zh"],
            "tag_modifier": it["tag_modifier"],
            "category": it["category"],
            "meat_zh": it["meat_zh"],
            "price_cents": it["price_cents"],
            "daily_cap": it["daily_cap"],
        }

    def _stock_for_date(item_ids, delivery_iso):
        """Returns {item_id: ordered_qty} for this delivery_date.

        Counts only paid orders' items (pending orders don't lock stock yet).
        """
        if not item_ids:
            return {}
        placeholders = ",".join("?" * len(item_ids))
        sql = f"""
            SELECT oi.menu_item_id, COALESCE(SUM(oi.quantity), 0) AS qty
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            WHERE o.delivery_date = ?
              AND o.payment_status = 'paid'
              AND oi.menu_item_id IN ({placeholders})
            GROUP BY oi.menu_item_id
        """
        with get_conn() as c:
            rows = c.execute(sql, [delivery_iso, *item_ids]).fetchall()
        return {r["menu_item_id"]: r["qty"] for r in rows}

    @app.route("/api/menu/this-week")
    def api_menu_this_week():
        ws = this_week_start()
        weekly = models.get_weekly(ws)              # [(pos, item), ...]
        delivery = next_delivery_date()
        item_ids = [it["id"] for _, it in weekly]
        ordered = _stock_for_date(item_ids, delivery.isoformat())
        items = []
        for pos, it in weekly:
            payload = _serialize_item(it)
            payload["position"] = pos
            payload["remaining"] = max(0, it["daily_cap"] - ordered.get(it["id"], 0))
            items.append(payload)
        return jsonify({
            "week_start": ws.isoformat(),
            "delivery_date": delivery.isoformat(),
            "delivery_label_zh": date_label(delivery, "zh"),
            "delivery_label_en": date_label(delivery, "en"),
            "items": items,
        })

    @app.route("/api/menu/next-week")
    def api_menu_next_week():
        ws = next_week_start()
        weekly = models.get_weekly(ws)
        items = []
        for pos, it in weekly:
            payload = _serialize_item(it)
            payload["position"] = pos
            items.append(payload)
        return jsonify({
            "week_start": ws.isoformat(),
            "items": items,
        })

    @app.route("/api/menu/all")
    def api_menu_all():
        rows = models.list_menu_items(active_only=True)
        return jsonify({"items": [_serialize_item(r) for r in rows]})

    # ---------- Checkout flow ----------

    def _list_delivery_dates(n_days: int = 14):
        """Return upcoming valid delivery dates (skip closed weekdays).

        Starts at next_delivery_date(); returns at most n_days entries.
        """
        out = []
        d = next_delivery_date()
        closed = closed_weekdays()
        while len(out) < n_days:
            if d.weekday() not in closed:
                out.append(d)
            d = d + _td(days=1)
        return out

    @app.route("/checkout")
    def checkout_page():
        delivery_dates = _list_delivery_dates(14)
        stripe_pk = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
        gmaps_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
        return render_template(
            "checkout.html",
            delivery_dates=[
                {"iso": d.isoformat(),
                 "label_zh": date_label(d, "zh"),
                 "label_en": date_label(d, "en")}
                for d in delivery_dates
            ],
            maps_enabled=bool(gmaps_key),
            google_maps_key=gmaps_key,
            stripe_enabled=payments.stripe_enabled(),
            stripe_pk=stripe_pk,
        )

    @app.route("/api/quote-delivery", methods=["POST"])
    def api_quote_delivery():
        data = request.get_json(silent=True) or {}
        address = (data.get("address") or "").strip()
        region = (data.get("region") or "").strip()
        if region:
            q = distance.quote_by_region(region)
        else:
            q = distance.quote_by_address(address)
        return jsonify({
            "deliverable": q.deliverable,
            "distance_km": q.distance_km,
            "min_qty": q.min_qty,
            "bucket_label": q.bucket_label,
            "fallback": q.fallback,
            "error": q.error,
        })

    @app.route("/api/order/create", methods=["POST"])
    def api_order_create():
        data = request.get_json(silent=True) or {}
        cart = data.get("items") or []
        cust = data.get("customer") or {}
        delivery_iso = (data.get("delivery_date") or "").strip()
        client_distance = data.get("distance_km")
        region = (data.get("region") or "").strip()

        # Validate cart
        if not cart:
            return jsonify(success=False, error="购物车为空 / Cart is empty"), 400
        for li in cart:
            if not li.get("id") or not li.get("qty") or int(li["qty"]) <= 0:
                return jsonify(success=False, error="Cart item invalid"), 400

        # Validate customer
        name = (cust.get("name") or "").strip()
        phone = (cust.get("phone") or "").strip()
        email = (cust.get("email") or "").strip() or None
        address = (cust.get("address") or "").strip()
        notes = (cust.get("notes") or "").strip() or None
        lang = cust.get("language") or "zh"
        if not name or not phone or not address:
            return jsonify(success=False,
                           error="姓名、电话、地址必填 / Name, phone, address required"), 400

        # Validate delivery date
        try:
            ddate = _date.fromisoformat(delivery_iso)
        except ValueError:
            return jsonify(success=False, error="Invalid delivery date"), 400
        if ddate < next_delivery_date() or ddate.weekday() in closed_weekdays():
            return jsonify(success=False,
                           error="送达日不可用 / Date not available"), 400

        # Re-quote distance server-side (don't trust client distance)
        if region:
            q = distance.quote_by_region(region)
        elif client_distance is not None:
            q = distance.quote_by_km(float(client_distance))
        else:
            q = distance.quote_by_address(address)
        if not q.deliverable:
            return jsonify(success=False, error=q.error or "地址超出配送范围"), 400

        # Validate min_qty met
        total_qty = sum(int(x["qty"]) for x in cart)
        if q.min_qty and total_qty < q.min_qty:
            return jsonify(
                success=False,
                error=f"该地址起送 {q.min_qty} 个,你只下了 {total_qty} 个",
            ), 400

        # Look up server-side prices + verify items active and stock
        with get_conn() as c:
            mi_rows = c.execute(
                "SELECT id, name_zh, name_en, image, price_cents, daily_cap, active "
                "FROM menu_items WHERE id IN ({})".format(
                    ",".join("?" * len(cart))
                ),
                [int(x["id"]) for x in cart],
            ).fetchall()
        items_by_id = {r["id"]: dict(r) for r in mi_rows}
        for li in cart:
            mi = items_by_id.get(int(li["id"]))
            if not mi or not mi["active"]:
                return jsonify(success=False,
                               error=f"商品 #{li['id']} 已下架"), 400

        # Re-check per-item stock
        ordered = _stock_for_date(list(items_by_id.keys()), ddate.isoformat())
        for li in cart:
            mi = items_by_id[int(li["id"])]
            available = mi["daily_cap"] - ordered.get(mi["id"], 0)
            if int(li["qty"]) > available:
                return jsonify(
                    success=False,
                    error=f"{mi['name_zh']} 库存不足(当日仅余 {available})"
                ), 400

        # Compute total from server-side prices
        total_cents = sum(
            items_by_id[int(li["id"])]["price_cents"] * int(li["qty"])
            for li in cart
        )

        # Insert pending order
        with get_conn() as c:
            cur = c.cursor()
            cur.execute(
                """INSERT INTO orders
                   (customer_name, phone, email, address, delivery_date,
                    distance_km, min_order_qty, total_cents, payment_status,
                    notes, language)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (name, phone, email, address, ddate.isoformat(),
                 q.distance_km, q.min_qty, total_cents, notes, lang),
            )
            order_id = cur.lastrowid
            for li in cart:
                mi = items_by_id[int(li["id"])]
                cur.execute(
                    """INSERT INTO order_items
                       (order_id, menu_item_id, name_snapshot, quantity, unit_price_cents)
                       VALUES (?, ?, ?, ?, ?)""",
                    (order_id, mi["id"], mi["name_zh"],
                     int(li["qty"]), mi["price_cents"]),
                )
            c.commit()

        # ----- Reservation flow (no online payment) -----
        # Send immediate "received" notification: email + SMS to customer,
        # email to kitchen so you know to review.
        order_obj, item_objs = models.get_order_with_items(order_id)
        if order_obj:
            try:
                notify.notify_event(order_obj, item_objs, "received")
            except Exception as e:
                print(f"[order_create] notify failed: {e}")

        token = make_order_token(order_id)
        return jsonify(
            success=True, order_id=order_id,
            redirect_url=url_for("order_view", oid=order_id, t=token),
        )

    @app.route("/api/stripe/webhook", methods=["POST"])
    def api_stripe_webhook():
        try:
            event = payments.verify_webhook(
                request.data, request.headers.get("Stripe-Signature", ""),
            )
        except Exception as e:
            return jsonify(error=f"verify failed: {e}"), 400

        etype = event.get("type") if isinstance(event, dict) else event["type"]
        if etype == "checkout.session.completed":
            obj = event["data"]["object"] if isinstance(event, dict) else event.data.object
            session_id = obj.get("id") if isinstance(obj, dict) else obj["id"]
            md = (obj.get("metadata") or {}) if isinstance(obj, dict) else dict(obj.metadata or {})
            order_id = int(md.get("order_id") or 0)
            if order_id:
                _mark_order_paid(order_id, session_id)
        return jsonify(received=True)

    def _mark_order_paid(order_id: int, session_id: str):
        with get_conn() as c:
            cur = c.cursor()
            row = cur.execute(
                "SELECT payment_status FROM orders WHERE id=?", (order_id,),
            ).fetchone()
            if not row or row["payment_status"] == "paid":
                return  # already paid or unknown
            cur.execute(
                "UPDATE orders SET payment_status='paid', paid_at=datetime('now'), "
                "stripe_session_id=COALESCE(stripe_session_id, ?) WHERE id=?",
                (session_id, order_id),
            )
            c.commit()
        order, items = models.get_order_with_items(order_id)
        if order:
            try:
                notify.notify_paid_order(order, items)
            except Exception as e:
                print(f"[webhook] notify failed: {e}")

    @app.route("/order/success")
    def order_success():
        sess = request.args.get("session_id", "")
        with get_conn() as c:
            row = c.execute(
                "SELECT id, payment_status FROM orders WHERE stripe_session_id=? "
                "ORDER BY id DESC LIMIT 1", (sess,),
            ).fetchone()
        if not row:
            return render_template("order_success.html",
                                   order=None, items=[], session_id=sess)
        # If webhook hasn't fired yet (likely in dev), poll Stripe directly
        if row["payment_status"] != "paid" and payments.stripe_enabled():
            try:
                import stripe
                stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
                s = stripe.checkout.Session.retrieve(sess)
                if s.get("payment_status") == "paid":
                    _mark_order_paid(row["id"], sess)
            except Exception as e:
                print(f"[order_success] stripe poll failed: {e}")
        order, items = models.get_order_with_items(row["id"])
        return render_template("order_success.html",
                               order=order, items=items, session_id=sess)

    @app.route("/order/<int:oid>")
    def order_view(oid):
        """Tokenised order status page — works for any state."""
        token = request.args.get("t", "")
        if not verify_order_token(oid, token):
            abort(404)
        order, items = models.get_order_with_items(oid)
        if not order:
            abort(404)
        return render_template("order_success.html",
                               order=order, items=items, session_id="",
                               order_token=token)

    # Public lookup: customer types phone → see all their orders.
    @app.route("/track", methods=["GET", "POST"])
    def order_track():
        err = None
        results = None
        searched_phone = ""
        if request.method == "POST":
            phone = (request.form.get("phone") or "").strip()
            searched_phone = phone
            if not phone:
                err = "请输入手机号 / Phone required"
            else:
                with get_conn() as c:
                    rows = c.execute(
                        "SELECT id, customer_name, payment_status, "
                        "delivery_date, total_cents, created_at "
                        "FROM orders WHERE phone=? "
                        "ORDER BY created_at DESC LIMIT 50",
                        (phone,),
                    ).fetchall()
                results = [
                    {**dict(r), "token": make_order_token(r["id"])}
                    for r in rows
                ]
                if not results:
                    err = ("此手机号下找不到订单。请检查号码是否完整(含国家码,"
                           "如 +64...)。如果刚下单几分钟内,稍后再试。")
        return render_template(
            "order_track.html",
            error=err, results=results, searched_phone=searched_phone,
        )

    # Reorder: returns cart-ready items so client can pre-fill localStorage.
    # Auth: token (same as the order detail page).
    @app.route("/api/order/<int:oid>/reorder")
    def api_order_reorder(oid):
        if not verify_order_token(oid, request.args.get("t", "")):
            return jsonify(success=False, error="Invalid token"), 403
        with get_conn() as c:
            order = c.execute("SELECT id FROM orders WHERE id=?", (oid,)).fetchone()
            if not order:
                return jsonify(success=False, error="Order not found"), 404
            rows = c.execute(
                """SELECT oi.menu_item_id, oi.quantity,
                          mi.sku, mi.name_zh, mi.name_en, mi.image,
                          mi.category, mi.price_cents, mi.active
                   FROM order_items oi
                   LEFT JOIN menu_items mi ON mi.id = oi.menu_item_id
                   WHERE oi.order_id=?""",
                (oid,),
            ).fetchall()
        items = []
        skipped = []
        for r in rows:
            if r["menu_item_id"] is None or not r["active"]:
                skipped.append(r["name_zh"] or "(未知商品)")
                continue
            items.append({
                "id": r["menu_item_id"],
                "sku": r["sku"],
                "name_zh": r["name_zh"],
                "name_en": r["name_en"],
                "category": r["category"],
                "image": r["image"],
                "price_cents": r["price_cents"],  # current price, not historical
                "qty": r["quantity"],
            })
        return jsonify(success=True, items=items, skipped=skipped)

    # ---- Back-compat redirects (old emails / bookmarks) ----
    @app.route("/order/received/<int:oid>")
    def _order_received_compat(oid):
        return redirect(url_for("order_view", oid=oid, t=make_order_token(oid)))

    @app.route("/order/pending/<int:oid>")
    def order_pending(oid):
        return redirect(url_for("order_view", oid=oid, t=make_order_token(oid)))

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("FLASK_DEBUG") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
