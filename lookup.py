#!/usr/bin/env python3
"""lookup.py — quick eBay check for a barcode or search text (no photos, no Claude).

    python3 lookup.py 4580779532934
    python3 lookup.py "desktop cute hitagi"
"""
import sys

from lister import ebay
from lister.config import load_env
from lister.draft import price_lines


def main():
    load_env()
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for arg in sys.argv[1:]:
        digits = "".join(c for c in arg if c.isdigit())
        info = ebay.gather(code=digits) if digits == arg.strip() else ebay.gather(q=arg)
        print(f"\n=== {arg}   ({info['n_listings']} listings, {info['n_us']} from US sellers, specifics from {info['n_detailed']})")
        for kind, c in info["categories"].items():
            print(f"  {kind} category: {c['path']} (id {c['id'] or '?'}); required: "
                  + (", ".join(a["name"] for a in c["aspects"]["required"]) or "none"))
        for t in info["titles"][:5]:
            print(f"  - {t}")
        print("  item specifics (value: listings):")
        for k, v in sorted(info["aspect_votes"].items()):
            print(f"    {k}: " + ", ".join(f"{x} ({n})" for x, n in v.items()))
        print("\n".join(price_lines(info["prices"])))


if __name__ == "__main__":
    main()
