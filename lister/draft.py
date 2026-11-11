"""Render one item's draft listing (Markdown for you, JSON for the later eBay-publish step)."""
import json
from datetime import date

from .config import HOUSE_SPECIFICS, INTRO_LINE, PLATFORM_MARKUP, TITLE_SUFFIX
from .ebay import barcode_kind


def price_lines(prices):
    out = []
    if not prices:
        return ["- no active listings found"]
    for cond, p in prices.items():
        out.append(f"- **{cond}:** {p['n']} listings · low ${p['low']:.2f} · median ${p['median']:.2f} · "
                   f"high ${p['high']:.2f} (incl. shipping)")
        for c in p["cheapest"]:
            out.append(f"  - ${c['total']:.2f} — [{c['title'][:70]}]({c['url']})")
    return out


def products_row(rec, barcode):
    """Products columns B..K (stop before the auto columns M/N)."""
    return "\t".join([rec.get("name", ""), rec.get("category", ""), rec.get("franchise", ""),
                      rec.get("line", ""), rec.get("character", ""), rec.get("variant", ""),
                      rec.get("maker", ""), barcode or "", barcode_kind(barcode) if barcode else "",
                      rec.get("height", "")])


def description_text(rec, details):
    lines = [INTRO_LINE.replace("[release date/rarity]", rec.get("intro_hook") or "[release date/rarity]"),
             "", BBTS_PLACEHOLDER, ""]
    lines += [f"- {k}: {v}" for k, v in details]
    lines += ["- Condition: Brand new, factory sealed"]
    return "\n".join(lines)


BBTS_PLACEHOLDER = "[paste BBTS description here, or delete this line]"


def _toml_str(v):
    return json.dumps(str(v), ensure_ascii=False)   # JSON string escapes are valid TOML basic strings


def listing_toml(photos, title, kind, specifics, description):
    """The file you edit before publishing. Everything publish.py sends to eBay comes from here.
    (TOML: top-level keys must come before the [package] / [specifics] sections.)"""
    from .config import SCHEDULE_DAYS
    out = ["# Edit this, then: python3 publish.py <this folder>",
           "# Anything marked TODO must be filled in.", "",
           f"title = {_toml_str(title)}   # max 80 characters",
           "price = 0.00            # TODO  USD, eBay price",
           f"category = {_toml_str(kind)}      # Figure or Plush (ids in lister/config.py)",
           f"schedule_days = {SCHEDULE_DAYS}       # 0 = list right away; otherwise starts this many days out",
           "# listing order; first = main photo",
           "photos = [" + ", ".join(_toml_str(p) for p in photos) + "]", "",
           "# Plain text. Blank line = new paragraph, '- ' lines = bullet list.",
           "description = '''", description.replace("'''", '"""'), "'''", "",
           "[package]   # TODO: packed weight and box size",
           "weight_lb = 0", "weight_oz = 0", "length_in = 0", "width_in = 0", "height_in = 0", "",
           "[specifics]"]
    out += [f"{_toml_str(k)} = {_toml_str(v)}" for k, v in specifics.items()]
    return "\n".join(out) + "\n"


def render(folder_name, photos, barcode, ebay, rec):
    specifics = {k: v for k, v in (rec.get("item_specifics") or {}).items()
                 if k not in ("UPC", "EAN", "Condition") and k not in HOUSE_SPECIFICS}
    if barcode:   # one barcode field: UPC for US codes, EAN for JAN/EAN-13
        specifics["UPC" if barcode.startswith("0") else "EAN"] = barcode[1:] if barcode.startswith("0") else barcode

    cats = ebay.get("categories") or {}
    chosen = cats.get(rec.get("category")) or cats.get("Figure")
    if chosen:   # house values, only for fields that exist in this category
        allowed = {a["name"] for k in ("required", "recommended") for a in chosen["aspects"][k]}
        for k, v in HOUSE_SPECIFICS.items():
            if k in allowed or not allowed:
                specifics[k] = v
    missing = []
    if chosen:
        names = {k.lower() for k in specifics}
        missing = [a["name"] for a in chosen["aspects"]["required"]
                   if a["name"].lower() not in names and a["name"] not in ("UPC", "EAN", "Condition")]
    details = [(k, v) for k, v in (("Maker", rec.get("maker")), ("Line", rec.get("line")),
                                   ("Character", rec.get("character")), ("Version", rec.get("variant")),
                                   ("Height", rec.get("height") or "TODO"),
                                   ("Material", specifics.get("Material", ""))) if v]

    warn = []
    if rec.get("matches_photos") is False:
        warn.append(f"> ⚠ **eBay matches may be a different item:** {rec.get('match_note', '')}")
    if not ebay.get("n_listings"):
        warn.append("> ⚠ No active eBay listings found — fields come from the photos only.")

    title = rec.get("ebay_title", "")
    if title and len(title) + len(TITLE_SUFFIX) <= 80:
        title += TITLE_SUFFIX
    md = [f"# {rec.get('name') or folder_name}", "",
          f"_Draft generated {date.today():%m/%d/%y} from folder `{folder_name}` · photos: {', '.join(photos)}_", ""]
    md += warn + ([""] if warn else [])
    md += ["## eBay title", "", f"`{title}`  ({len(title)}/80)", "",
           "## Category", "",
           (f"{chosen['path']} (id {chosen['id']})" if chosen else "—"), ""]
    md += ["## Item specifics", "", "| Field | Value |", "|---|---|", "| Condition | New |"]
    md += [f"| {k} | {v} |" for k, v in specifics.items()]
    md += [f"| {m} | **TODO (required)** |" for m in missing]
    md += ["", "Shipping: weight **TODO**, package size **TODO**", "",
           "## Description", "", description_text(rec, details), ""]
    if rec.get("box_facts"):
        md += ["**From the box (for you, not the listing):** " + " · ".join(rec["box_facts"]), ""]
    md += [
           "## Price", "", "Active listings right now (asking prices, not sold). US sellers are your real competition; abroad totals include international shipping:"]
    md += price_lines(ebay.get("prices", {}))
    md += ["", "| Platform | Price |", "|---|---|"]
    md += [f"| {p} | **TODO**{f' (eBay + ${m:.0f})' if m else ''} |" for p, m in PLATFORM_MARKUP.items()]
    if rec.get("uncertain"):
        md += ["", "## Check these", ""] + [f"- {u}" for u in rec["uncertain"]]
    md += ["", "## Products row (paste into column B)", "", "```", products_row(rec, barcode), "```", ""]
    kind = rec.get("category") if rec.get("category") in cats else "Figure"
    return "\n".join(md), listing_toml(photos, title, kind, specifics, description_text(rec, details))


def save(folder, photos, barcode, ebay, rec, overwrite_listing=False):
    md, toml = render(folder.name, photos, barcode, ebay, rec)
    (folder / "draft.md").write_text(md)
    lt = folder / "listing.toml"
    if overwrite_listing or not lt.exists():
        lt.write_text(toml)
    else:
        (folder / "listing.new.toml").write_text(toml)
        print("  (kept your edited listing.toml; the fresh one is listing.new.toml)")
    (folder / "draft.json").write_text(json.dumps(
        {"barcode": barcode, "photos": photos, "record": rec, "ebay": ebay}, ensure_ascii=False, indent=1))
