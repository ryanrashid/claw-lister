"""Loads .env from the repo root (stdlib only). Real environment variables win."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env():
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v and k.strip() not in os.environ:
            os.environ[k.strip()] = v


def inbox():
    return Path(os.environ.get("LISTER_INBOX") or Path.home() / "Listings" / "inbox").expanduser()


# Listing conventions (edit here, not in code below)
INTRO_LINE = ("Brand new, unopened, won from a claw machine at Round 1 SF. "
              "This {noun} is [release date/rarity] so get it here now!")
INTRO_NOUN = {"Figure": "figurine", "Plush": "plush"}   # fills {noun} in INTRO_LINE
NAME_RULE = "{Franchise} {Line} {Character} [{Variant}] Figure   (or ... Plush)"
PLATFORM_MARKUP = {"eBay": 0.0, "Depop": 0.0, "Mercari": 1.0, "FB Marketplace": 1.0}

# eBay US category per item type: (id, full path). The id is what's used; the path is a label.
# To find an id: open the category on ebay.com; it's the number in the URL
# (ebay.com/b/Other-Stuffed-Animals/230/bn_...). An empty id gets looked up by path once.
EBAY_CATEGORIES = {
    "Figure": ("261055", "Collectibles > Animation Art & Merchandise > Animation Merchandise > Figures & Statues"),
    "Plush": ("230", "Toys & Hobbies > Stuffed Animals > Other Stuffed Animals"),
}

# Things you always put, whatever the photos/listings say. These override Claude and eBay data.
# Add more here as you remember them (aspect name -> value).
HOUSE_SPECIFICS = {
    "Prize": {   # Figure and Plush
        "Country of Origin": "Japan",
        "Country/Region of Manufacture": "Japan",   # eBay's name for the same field in some categories
        "Packaging": "Original (Unopened)",
        "Occasion": "All Occasions",
    },
    "Figure": {
        "Convention/Event": "Nor Con",
    },
}
# Fields Claude should always try to fill (from the box/tag or 2+ listings), even when eBay
# lists them as optional for the category. Empty if there's no evidence.
ALSO_FILL = ["Year Manufactured"]

# Time Period Manufactured for Figure/Plush: derived from Year Manufactured when known
# (eBay's buckets), otherwise this default.
TIME_PERIOD_DEFAULT = "2020-Now"


def time_period(year):
    try:
        y = int(str(year).strip()[:4])
    except (TypeError, ValueError):
        return TIME_PERIOD_DEFAULT
    if y >= 2020:
        return "2020-Now"
    decade = y // 10 * 10
    return f"{decade}-{decade + 9}"


def house_specifics(kind):
    """Your fixed values for a Figure/Plush ({} for anything else)."""
    if kind not in ("Figure", "Plush"):
        return {}
    return {**HOUSE_SPECIFICS.get("Prize", {}), **HOUSE_SPECIFICS.get(kind, {})}


def house_keys():
    return sorted({k for group in HOUSE_SPECIFICS.values() for k in group})
TITLE_SUFFIX = " (US Seller)"   # appended to every eBay title when it fits in 80 characters

# ---- publishing (publish.py) ----
SCHEDULE_DAYS = 21          # new listings start this many days out = a "draft" you finish in Seller Hub
ITEM_POSTAL_CODE = "94103"  # ZIP the item ships from
# Your account doesn't use eBay business policies, so these go into each listing directly.
# (If you ever turn business policies on, put their ids in EBAY_POLICIES and they win.)
EBAY_POLICIES = {"shipping": "", "payment": "", "returns": ""}
SHIPPING = {
    "service": "USPSParcel",            # eBay's code for USPS Ground Advantage; buyer pays, calculated
    "handling_days": 2,
    "intl_ebay_international_shipping": True,
}
RETURNS = {
    "domestic": False,                  # no returns (eBay Money Back Guarantee still covers not-as-described)
    "intl_via_ebay_international_shipping": True,   # accepted within 30 days, eBay handles it
    "intl_days": 30,
}
CONDITION_ID = 1000         # eBay "New"

# ---- Claude usage (list.py) ----
CLAUDE_MODEL = "sonnet"     # cheaper on Pro limits than Opus; set "opus" (or "") to compare/revert
CLAUDE_LEAN = True          # photos sent inline, own short system prompt, no tools/MCP: ~1 turn per call
CLAUDE_IMAGE_MAX = 1568     # px; Claude downsizes larger images anyway, so bigger only costs upload time
