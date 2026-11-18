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
from .photos import IMAGE_EXT, own as _own  # noqa: F401 (IMAGE_EXT kept for callers)


def _variants(img):
    """Sizes to try. Barcodes in ~1000px photos are too small to read as-is; 2x upscale fixes it.
    zxing already tries rotations itself."""
    img = ImageOps.exif_transpose(img).convert("L")
    side = max(img.size)
    if side > 3000:
        big = img.copy()
        big.thumbnail((2400, 2400))
        yield big
    yield img
    if side < 2500:
        yield img.resize((img.width * 2, img.height * 2), Image.LANCZOS)


# zxing's default thresholding (LocalAverage) misses some printed barcodes on tinted boxes
# (e.g. a barcode on a lavender box panel with no white quiet zone); a fixed threshold
# reads them. Tried in order, stopping at the first that finds a retail code.
_B = getattr(zxingcpp, "Binarizer", None)
BINARIZERS = [None] + ([_B.FixedThreshold, _B.GlobalHistogram] if _B else [])


def _read(im, binarizer):
    return zxingcpp.read_barcodes(im) if binarizer is None else zxingcpp.read_barcodes(im, binarizer=binarizer)


def codes_in(path):
    found = Counter()
    with Image.open(path) as img:
        variants = list(_variants(img))
    for binarizer in BINARIZERS:
        for im in variants:
            for sym in _read(im, binarizer):
                code = sym.text.strip()
                if not (code.isdigit() and len(code) in RETAIL_LENGTHS):
                    continue
                if len(code) == 12:      # UPC-A -> 13-digit form, matches what's on Products
                    code = "0" + code
                found[code] += 1
            if found:
                return list(found)
    return list(found)


def images(folder):
    """Your photos only; stock/ images are skipped (see lister/photos.py)."""
    return _own(folder)


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
