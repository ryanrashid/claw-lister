"""Which photos in an item folder are yours vs. stock images from the web.

    <item>/IMG_0001.jpg ...   your photos: barcode reading, Claude, and the listing
    <item>/stock/*.jpg        web images of the figure: listing only, after yours

Stock images are never read for the barcode or sent to Claude: they don't show *this* unit
(could be another version, or out of the box), and skipping them saves usage.
"""
from pathlib import Path

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
STOCK_DIR = "stock"


def _imgs(folder):
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT)


def own(folder):
    """Your photos (top level of the item folder), as Paths."""
    return _imgs(folder)


def stock(folder):
    """Stock images, as paths relative to the item folder ("stock/x.jpg")."""
    return [f"{STOCK_DIR}/{p.name}" for p in _imgs(Path(folder) / STOCK_DIR)]


def for_listing(folder):
    """Listing order: your photos first (first = main photo), then stock."""
    return [p.name for p in own(folder)] + stock(folder)
