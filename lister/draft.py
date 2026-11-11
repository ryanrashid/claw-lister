"""Render one item's draft listing (Markdown for you, JSON for the later eBay-publish step)."""
import json
from datetime import date

from .config import INTRO_LINE, PLATFORM_MARKUP
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


def render(folder_name, photos, barcode, ebay, rec):
    specifics = dict(rec.get("item_specifics") or {})
    if barcode:
        specifics.setdefault("UPC" if barcode.startswith("0") else "EAN", barcode.lstrip("0") if barcode.startswith("0") else barcode)
    specifics.setdefault("Condition", "New")

    warn = []
    if rec.get("matches_photos") is False:
        warn.append(f"> ⚠ **eBay matches may be a different item:** {rec.get('match_note', '')}")
    if not ebay.get("n_listings"):
        warn.append("> ⚠ No active eBay listings found — fields come from the photos only.")

    title = rec.get("ebay_title", "")
    md = [f"# {rec.get('name') or folder_name}", "",
          f"_Draft generated {date.today():%m/%d/%y} from folder `{folder_name}` · photos: {', '.join(photos)}_", ""]
    md += warn + ([""] if warn else [])
    md += ["## eBay title", "", f"`{title}`  ({len(title)}/80)", "",
           "## Category", "", f"{ebay.get('ebay_category_path') or '—'} (id {ebay.get('ebay_category_id') or '—'})", "",
           "## Item specifics", "", "| Field | Value |", "|---|---|"]
    md += [f"| {k} | {v} |" for k, v in specifics.items()]
    md += ["| Item Weight | **TODO** |", "",
           "## Description", "",
           INTRO_LINE.replace("[release date/rarity]", f"[release date/rarity — box says: {rec.get('release_info') or 'nothing'}]"),
           "", "[paste BBTS description here]", "",
           "## Price", "", "Active listings right now (asking prices, not sold). US sellers are your real competition; abroad totals include international shipping:"]
    md += price_lines(ebay.get("prices", {}))
    md += ["", "| Platform | Price |", "|---|---|"]
    md += [f"| {p} | **TODO**{f' (eBay + ${m:.0f})' if m else ''} |" for p, m in PLATFORM_MARKUP.items()]
    if rec.get("uncertain"):
        md += ["", "## Check these", ""] + [f"- {u}" for u in rec["uncertain"]]
    md += ["", "## Products row (paste into column B)", "", "```", products_row(rec, barcode), "```", ""]
    return "\n".join(md)


def save(folder, photos, barcode, ebay, rec):
    (folder / "draft.md").write_text(render(folder.name, photos, barcode, ebay, rec))
    (folder / "draft.json").write_text(json.dumps(
        {"barcode": barcode, "photos": photos, "record": rec, "ebay": ebay}, ensure_ascii=False, indent=1))
