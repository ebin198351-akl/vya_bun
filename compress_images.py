"""Compress all images in the image/ directory for web performance."""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
from PIL import Image

IMAGE_DIR = os.path.join(os.path.dirname(__file__), "image")

# Settings
CARD_MAX_WIDTH = 800     # For product card thumbnails
MODAL_MAX_WIDTH = 1400   # For modal / carousel / large images
QUALITY = 82

def compress_image(filepath, max_width):
    """Compress a single image file in-place."""
    try:
        original_size = os.path.getsize(filepath)
        img = Image.open(filepath)

        # Convert RGBA to RGB if needed
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Resize if wider than max_width
        w, h = img.size
        if w > max_width:
            ratio = max_width / w
            new_size = (max_width, int(h * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        # Save with compression
        img.save(filepath, "JPEG", quality=QUALITY, optimize=True)

        new_size_bytes = os.path.getsize(filepath)
        saved = original_size - new_size_bytes
        pct = (saved / original_size * 100) if original_size > 0 else 0
        print(f"  {os.path.basename(filepath)}: {original_size/1024:.0f}KB -> {new_size_bytes/1024:.0f}KB ({pct:.0f}% saved)")
        return saved
    except Exception as e:
        print(f"  ERROR: {filepath}: {e}")
        return 0

total_saved = 0
file_count = 0

for root, dirs, files in os.walk(IMAGE_DIR):
    for fname in files:
        if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
            continue

        filepath = os.path.join(root, fname)
        rel = os.path.relpath(filepath, IMAGE_DIR)

        # Determine max width based on location
        # Product card images get smaller, carousel/hero get larger
        if "product" in rel:
            max_w = CARD_MAX_WIDTH
        else:
            max_w = MODAL_MAX_WIDTH

        print(f"[{rel}]")
        saved = compress_image(filepath, max_w)
        total_saved += saved
        file_count += 1

print(f"\nDone! Compressed {file_count} files, saved {total_saved/1024/1024:.1f} MB total.")
