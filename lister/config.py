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

# eBay US category used for every listing (verified by name at runtime).
# Figures & Statues under Collectibles > Animation Art & Merchandise > Animation Merchandise.
EBAY_CATEGORY_ID = "261055"
EBAY_CATEGORY_NAME = "Figures & Statues"
