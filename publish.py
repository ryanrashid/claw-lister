#!/usr/bin/env python3
"""publish.py — turn a finished listing.toml into an eBay listing.

    python3 publish.py ~/Listings/inbox/link            # dry run, then asks before listing
    python3 publish.py ~/Listings/inbox/link --yes      # no question
    python3 publish.py ~/Listings/inbox/link --check    # dry run only

By default the listing is *scheduled* schedule_days out (21), so it sits under
Seller Hub > Scheduled where you can still edit it, then start it whenever you like.
"""
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import tomllib
except ImportError:   # Python < 3.11
    sys.exit(f"This is Python {sys.version.split()[0]} at {sys.executable}.\n"
             "publish.py needs the project's Python 3.12: run `conda activate ./.venv` first "
             "(or call `.venv/bin/python publish.py ...`).")

from lister import trading
from lister.config import (CONDITION_ID, EBAY_CATEGORIES, EBAY_POLICIES, ITEM_POSTAL_CODE, RETURNS,
                           SHIPPING, load_env)
from lister.draft import BBTS_PLACEHOLDER, OTHER_PLACEHOLDER


def category_id(L):
    """'Figure'/'Plush' -> id from config; a numeric id is used as-is (any eBay category)."""
    c = str(L.get("category", "")).strip()
    if c in EBAY_CATEGORIES:
        return EBAY_CATEGORIES[c][0]
    return c if c.isdigit() else None


def problems(L):
    p = []
    if not L.get("title") or len(L["title"]) > 80:
        p.append(f"title is {len(L.get('title', ''))} characters (1-80)")
    if not L.get("price") or float(L["price"]) <= 0:
        p.append("price is not set")
    pk = L.get("package", {})
    if float(pk.get("weight_lb", 0)) * 16 + float(pk.get("weight_oz", 0)) <= 0:
        p.append("package weight is not set")
    if any(float(pk.get(k, 0)) <= 0 for k in ("length_in", "width_in", "height_in")):
        p.append("package size is not set")
    if any(x in L.get("description", "") for x in ("TODO", BBTS_PLACEHOLDER, OTHER_PLACEHOLDER)):
        p.append("description still has TODO / the BBTS placeholder")
    if any("TODO" in str(v) for v in L.get("specifics", {}).values()):
        p.append("a specific is still TODO")
    if category_id(L) is None:
        p.append(f"category must be one of {list(EBAY_CATEGORIES)} or an eBay category id like \"178893\"")
    else:
        # specifics eBay requires in this category that the file doesn't have
        from lister.ebay import category_aspects
        have = {k.lower() for k, v in L.get("specifics", {}).items() if str(v).strip()}
        need = [a["name"] for a in category_aspects(category_id(L))["required"]
                if a["name"].lower() not in have and a["name"] not in ("UPC", "EAN", "Condition")]
        if need:
            p.append(f"category {category_id(L)} requires specifics: {', '.join(need)}")
    if not ITEM_POSTAL_CODE:
        p.append("ITEM_POSTAL_CODE is empty in lister/config.py")
    if not L.get("photos"):
        p.append("no photos")
    return p


def upload_photos(folder, names):
    """Upload once; reuse the eBay URLs on later runs (cached per file+size+mtime)."""
    cache_f = folder / ".photos.json"
    cache = json.loads(cache_f.read_text()) if cache_f.exists() else {}
    urls = []
    for n in names:
        p = folder / n
        if not p.exists():
            sys.exit(f"photo not found: {p}")
        key = f"{n}:{p.stat().st_size}:{int(p.stat().st_mtime)}"
        if key not in cache:
            print(f"  uploading {n}")
            cache[key] = trading.upload_photo(p)
            cache_f.write_text(json.dumps(cache, indent=1))
        urls.append(cache[key])
    return urls


def main():
    load_env()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    folder = Path(args[0]).expanduser()
    lt = folder / "listing.toml"
    if not lt.exists():
        sys.exit(f"No listing.toml in {folder}. Run list.py first.")
    L = tomllib.loads(lt.read_text())
    if (folder / "published.json").exists() and "--force" not in sys.argv:
        sys.exit(f"Already listed: {json.loads((folder / 'published.json').read_text())}. Use --force to list again.")

    bad = problems(L)
    if bad:
        sys.exit("Fix these in listing.toml / config first:\n  - " + "\n  - ".join(bad))

    days = int(L.get("schedule_days", 0))
    start = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z") if days else ""
    cfg = {"category_id": category_id(L), "postal_code": ITEM_POSTAL_CODE,
           "policies": EBAY_POLICIES, "shipping": SHIPPING, "returns": RETURNS,
           "condition_id": int(L.get("condition_id", CONDITION_ID)), "schedule": start}

    print(f"=== {L['title']}")
    urls = upload_photos(folder, L["photos"])
    item = trading.item_xml(L, urls, cfg)

    try:
        root, warns = trading.call("VerifyAddFixedPriceItem", item)
    except trading.EbayError as e:
        msg = f"eBay rejected the dry run:\n{e}"
        if "ShippingDetails" in str(e) or "ShippingService" in str(e):
            msg += f"\n\nShipping service in config is '{SHIPPING['service']}'. USPS codes eBay accepts:\n" + \
                   "\n".join(f"  {c:32} {d}" for c, d, _ in trading.shipping_services("USPS"))
        sys.exit(msg)
    for w in warns:
        print(f"  warning [{w['code']}]: {w['message']}")
    fee_list = dict(trading.fees(root))
    total = fee_list.pop("ListingFee", sum(fee_list.values()))   # ListingFee is eBay's total, not an extra fee
    parts = ", ".join(f"{n} ${a:.2f}" for n, a in fee_list.items())
    print(f"  dry run OK. Upfront fees: ${total:.2f}" + (f" ({parts})" if parts else "")
          + "; final value fee comes out when it sells")
    if total:
        print("  (eBay's estimate: the dry run may not apply your free monthly listings, see README)")
    if "--check" in sys.argv:
        return

    when = f"scheduled to start {start[:10]} (edit it under Seller Hub > Scheduled)" if start else "live immediately"
    if "--yes" not in sys.argv and input(f"  List it ({when})? [y/N] ").strip().lower() != "y":
        print("  not listed")
        return
    root, warns = trading.call("AddFixedPriceItem", item)
    item_id = root.findtext(trading.NS + "ItemID")
    url = f"https://www.ebay.com/itm/{item_id}"
    (folder / "published.json").write_text(json.dumps(
        {"item_id": item_id, "url": url, "start": start or "now", "price": L["price"]}, indent=1))
    print(f"  listed: {url}  ({when})")


if __name__ == "__main__":
    main()
