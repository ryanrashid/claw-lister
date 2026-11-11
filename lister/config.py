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
              "This figurine is [release date/rarity] so get it here now!")
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
    "Country of Origin": "Japan",
    "Country/Region of Manufacture": "Japan",   # eBay's name for the same field in some categories
}
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
