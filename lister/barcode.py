"""Read retail barcodes (JAN/EAN-13, UPC-A, EAN-8) out of photos."""
from collections import Counter
from pathlib import Path

from PIL import Image, ImageOps

try:  # iPhone .heic support if pillow-heif is installed
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

import zxingcpp  # pip wheel with the native reader bundled: no brew/system install needed

# No `formats=` argument: its type changed between zxing-cpp versions (tuple vs flags) and broke
# on 3.x. Read everything and keep retail codes: all digits, 8/12/13 long.
RETAIL_LENGTHS = {8, 12, 13}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".webp"}


def _variants(img):
    img = ImageOps.exif_transpose(img).convert("L")
    for max_side in (2000, 1200, None):
        im = img
        if max_side and max(im.size) > max_side:
            im = im.copy()
            im.thumbnail((max_side, max_side))
        for angle in (0, 90):
            yield im.rotate(angle, expand=True) if angle else im


def codes_in(path):
    found = Counter()
    with Image.open(path) as img:
        for im in _variants(img):
            for sym in zxingcpp.read_barcodes(im):
                code = sym.text.strip()
                if not (code.isdigit() and len(code) in RETAIL_LENGTHS):
                    continue
                if len(code) == 12:      # UPC-A -> 13-digit form, matches what's on Products
                    code = "0" + code
                found[code] += 1
            if found:
                break
    return list(found)


def images(folder):
    return sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in IMAGE_EXT)


def scan(folder):
    """{code: [photo names]} for one item folder."""
    out = {}
    for p in images(folder):
        try:
            for c in codes_in(p):
                out.setdefault(c, []).append(p.name)
        except Exception as e:  # unreadable image shouldn't kill the batch
            print(f"  ! could not read {p.name}: {e}")
    return out
