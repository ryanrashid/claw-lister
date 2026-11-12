#!/usr/bin/env python3
"""list.py — photos in, draft listings out.

Put each item's photos in its own folder inside the inbox (default ~/Listings/inbox):
    ~/Listings/inbox/link/IMG_001.jpg ...
    ~/Listings/inbox/hitagi/IMG_010.jpg ...
Then:
    python3 list.py                 # every folder without a draft yet
    python3 list.py path/to/folder  # just these folders
    python3 list.py --redo          # redo the research (barcode, eBay, Claude) for existing drafts too
    python3 list.py --render        # rebuild draft.md / listing.new.toml from saved draft.json: no eBay, no Claude

For each folder: read barcode from the photos (or have Claude read the box) ->
eBay lookup -> Claude cleans it up against the photos -> writes draft.md + draft.json there.
"""
import sys
from pathlib import Path

from lister import barcode, claude, draft, ebay
from lister.config import NAME_RULE, inbox, load_env


def process(folder):
    photos = [p.name for p in barcode.images(folder)]
    if not photos:
        print("  no photos, skipping")
        return
    print(f"  {len(photos)} photos")

    codes = barcode.scan(folder)
    if len(codes) > 1:
        print(f"  ! several barcodes {list(codes)} — using the one seen in most photos; "
              "split the folder if these are different items")
    code = max(codes, key=lambda c: len(codes[c])) if codes else ""

    query = None
    if code:
        print(f"  barcode {code}")
    else:
        print("  no barcode readable — asking Claude to read the box")
        box = claude.read_box(photos, cwd=folder)
        code = "".join(ch for ch in box.get("barcode_digits", "") if ch.isdigit())
        query = None if code else box.get("search_query")
        print(f"  box says: {box.get('search_query')} ({box.get('confidence')})")

    info = ebay.gather(code=code) if code else ebay.gather(q=query)
    if code and not info["n_listings"]:
        print("  barcode found nothing on eBay — falling back to box reading")
        box = claude.read_box(photos, cwd=folder)
        info = ebay.gather(q=box.get("search_query"))
    print(f"  eBay: {info['n_listings']} listings ({info['n_us']} from US sellers), specifics from {info['n_detailed']}")

    print("  Claude: matching to photos and cleaning up")
    rec = claude.clean_up(photos, code, info, NAME_RULE, cwd=folder)
    draft.save(folder, photos, code, info, rec)
    flag = "" if rec.get("matches_photos", True) else "   ⚠ eBay matches may be a different item"
    print(f"  -> {rec.get('name')}{flag}")
    print(f"  -> {folder / 'draft.md'}")


def render_only(folder):
    """Re-render from the saved research (after a code/format change). Costs nothing."""
    import json
    saved = folder / "draft.json"
    if not saved.exists():
        print("  no draft.json yet; run list.py without --render first")
        return
    d = json.loads(saved.read_text())
    draft.save(folder, d["photos"], d["barcode"], d["ebay"], d["record"])
    print(f"  -> re-rendered {folder / 'draft.md'} (no eBay or Claude calls)")


def main():
    load_env()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    redo = "--redo" in sys.argv
    if "--render" in sys.argv:
        folders = [Path(a).expanduser() for a in args] or sorted(
            p for p in inbox().iterdir() if p.is_dir() and (p / "draft.json").exists())
        for f in folders:
            print(f"\n=== {f.name}")
            render_only(f)
        return
    if args:
        folders = [Path(a).expanduser() for a in args]
    else:
        root = inbox()
        if not root.exists():
            root.mkdir(parents=True)
            sys.exit(f"Created {root}. Put one folder of photos per item in it and run again.")
        folders = sorted(p for p in root.iterdir() if p.is_dir())
    todo = [f for f in folders if redo or not (f / "draft.md").exists()]
    if not todo:
        print("Nothing to do (every folder already has a draft.md; use --redo to rebuild).")
    for f in todo:
        print(f"\n=== {f.name}")
        try:
            process(f)
        except Exception as e:   # one bad item shouldn't stop the batch
            print(f"  ! failed: {e}")


if __name__ == "__main__":
    main()
