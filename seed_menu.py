"""One-time seeder: parses index.html and loads all SKUs into menu_items.

Idempotent on SKU. Safe to run multiple times; updates fields on conflict.
"""
import re
from pathlib import Path
from db import get_conn, init_db

HTML_PATH = Path(__file__).parent / "index.html"

# Capture groups:
#   1 data-product        2 category          3 image src
#   4 tag modifier (opt)  5 tag text
#   6 h3 zh (name_zh)     7 h3 en (name_en)
#   8 desc_zh             9 desc_en
#  10 SKU code           11 meat_zh
PRODUCT_RE = re.compile(
    r'<article class="product-card[^"]*"\s+data-product="([^"]+)"\s+data-category="([^"]+)">'
    r'.*?<img[^>]*src="([^"]+)"'
    r'.*?<span class="product-tag(?:\s+(\w+))?">([^<]+)</span>'
    r'.*?<h3 class="lang zh">([^<]+)</h3>'
    r'.*?<h3 class="lang en">([^<]+)</h3>'
    r'.*?<p class="product-desc lang zh">\s*([^<]+?)\s*</p>'
    r'.*?<p class="product-desc lang en">\s*([^<]+?)\s*</p>'
    r'.*?<dd>(VYA-[A-Z0-9-]+)</dd>'
    r'.*?<dd class="lang zh">([^<]+)</dd>',
    re.DOTALL,
)


def normalize(s: str) -> str:
    if s is None:
        return ""
    return " ".join(s.split()).replace("&amp;", "&").replace("&nbsp;", " ")


def extract():
    html = HTML_PATH.read_text(encoding="utf-8")
    items = []
    for i, m in enumerate(PRODUCT_RE.finditer(html)):
        items.append({
            "sku": m.group(10),
            "category": m.group(2),
            "image": m.group(3),
            "tag_modifier": m.group(4) or "",
            "tag_zh": normalize(m.group(5)),
            "name_zh": normalize(m.group(6)),
            "name_en": normalize(m.group(7)),
            "desc_zh": normalize(m.group(8)),
            "desc_en": normalize(m.group(9)),
            "meat_zh": normalize(m.group(11)),
            "sort_order": i,
        })
    return items


def seed():
    init_db()
    items = extract()
    print(f"Parsed {len(items)} items from index.html")
    conn = get_conn()
    cur = conn.cursor()
    inserted = updated = 0
    for it in items:
        existing = cur.execute(
            "SELECT id FROM menu_items WHERE sku = ?", (it["sku"],)
        ).fetchone()
        if existing:
            cur.execute(
                """UPDATE menu_items SET
                    name_zh=?, name_en=?, desc_zh=?, desc_en=?,
                    category=?, meat_zh=?, image=?, tag_zh=?, tag_modifier=?,
                    sort_order=?
                   WHERE sku = ?""",
                (
                    it["name_zh"], it["name_en"], it["desc_zh"], it["desc_en"],
                    it["category"], it["meat_zh"], it["image"],
                    it["tag_zh"], it["tag_modifier"], it["sort_order"],
                    it["sku"],
                ),
            )
            updated += 1
        else:
            cur.execute(
                """INSERT INTO menu_items
                   (sku, name_zh, name_en, desc_zh, desc_en, category, meat_zh,
                    image, tag_zh, tag_modifier, price_cents, daily_cap, sort_order)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 200, 40, ?)""",
                (
                    it["sku"], it["name_zh"], it["name_en"],
                    it["desc_zh"], it["desc_en"],
                    it["category"], it["meat_zh"], it["image"],
                    it["tag_zh"], it["tag_modifier"], it["sort_order"],
                ),
            )
            inserted += 1
    conn.commit()
    conn.close()
    print(f"Inserted {inserted}, updated {updated}")


if __name__ == "__main__":
    seed()
