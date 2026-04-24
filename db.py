"""SQLite schema + small helpers. No ORM, just sqlite3."""
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "data" / "vya.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS menu_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sku TEXT UNIQUE NOT NULL,
  name_zh TEXT NOT NULL,
  name_en TEXT NOT NULL,
  desc_zh TEXT,
  desc_en TEXT,
  category TEXT,
  meat_zh TEXT,
  image TEXT,
  tag_zh TEXT,
  tag_modifier TEXT,
  price_cents INTEGER NOT NULL DEFAULT 200,
  daily_cap INTEGER NOT NULL DEFAULT 40,
  active INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS weekly_menu (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  week_start_date TEXT NOT NULL,           -- ISO Monday date 'YYYY-MM-DD'
  position INTEGER NOT NULL,                -- 1..4
  menu_item_id INTEGER NOT NULL REFERENCES menu_items(id) ON DELETE CASCADE,
  UNIQUE(week_start_date, position)
);
CREATE INDEX IF NOT EXISTS idx_weekly_date ON weekly_menu(week_start_date);

CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_name TEXT NOT NULL,
  phone TEXT NOT NULL,
  email TEXT,
  address TEXT NOT NULL,
  delivery_date TEXT NOT NULL,             -- 'YYYY-MM-DD'
  distance_km REAL,
  min_order_qty INTEGER,
  total_cents INTEGER NOT NULL,
  payment_status TEXT DEFAULT 'pending',   -- pending|paid|cancelled|refunded
  payment_method TEXT,
  stripe_session_id TEXT,
  notes TEXT,
  language TEXT DEFAULT 'zh',
  created_at TEXT DEFAULT (datetime('now')),
  paid_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(payment_status);
CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(delivery_date);
CREATE INDEX IF NOT EXISTS idx_orders_session ON orders(stripe_session_id);

CREATE TABLE IF NOT EXISTS order_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  menu_item_id INTEGER NOT NULL REFERENCES menu_items(id),
  name_snapshot TEXT NOT NULL,             -- snapshot at order time (zh)
  quantity INTEGER NOT NULL,
  unit_price_cents INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);

-- daily_stock tracks committed (paid) order qty per item per delivery date.
-- Used to enforce per-item 40/day cap.
CREATE TABLE IF NOT EXISTS daily_stock (
  delivery_date TEXT NOT NULL,
  menu_item_id INTEGER NOT NULL REFERENCES menu_items(id),
  ordered_qty INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(delivery_date, menu_item_id)
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);
"""

DEFAULT_SETTINGS = {
    "cutoff_hour": "18",
    "daily_cap_total": "160",
    "per_item_cap": "40",
    "delivery_fee_cents": "0",
    "pickup_enabled": "0",
    "closed_weekdays": "5",          # comma-separated 0=Mon..6=Sun, 5=Saturday
    "delivery_buckets": "6:10,12:20,20:30,30:40",  # km_max:min_qty
    "max_delivery_km": "30",
}


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def cursor():
    conn = get_conn()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Idempotent: creates tables and seeds default settings."""
    with cursor() as cur:
        cur.executescript(SCHEMA)
        for k, v in DEFAULT_SETTINGS.items():
            cur.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                (k, v),
            )


def get_setting(key, default=None):
    with cursor() as cur:
        row = cur.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    with cursor() as cur:
        cur.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )


if __name__ == "__main__":
    init_db()
    print(f"Initialized DB at {DB_PATH}")
