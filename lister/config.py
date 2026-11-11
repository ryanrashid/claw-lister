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

# eBay US category per item type: (id, full path). Leave an id empty to have it looked up
# by path (Taxonomy API). The path is also how a configured id gets double-checked.
EBAY_CATEGORIES = {
    "Figure": ("261055", "Collectibles > Animation Art & Merchandise > Animation Merchandise > Figures & Statues"),
    "Plush": ("", "Toys & Hobbies > Stuffed Animals > Other Stuffed Animals"),
}

# Things you always put, whatever the photos/listings say. These override Claude and eBay data.
# Add more here as you remember them (aspect name -> value).
HOUSE_SPECIFICS = {
    "Country of Origin": "Japan",
    "Country/Region of Manufacture": "Japan",   # eBay's name for the same field in some categories
}
TITLE_SUFFIX = " (US Seller)"   # appended to every eBay title when it fits in 80 characters
