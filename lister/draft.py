"""Per-item outputs: draft.md (research to read), listing.toml (the listing to edit), draft.json (raw)."""
import json
from datetime import date

from .config import HOUSE_SPECIFICS, INTRO_LINE, INTRO_NOUN, PLATFORM_MARKUP, TITLE_SUFFIX
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


def is_prize(rec):
    return rec.get("category") in ("Figure", "Plush")


def description_text(rec, details):
    if is_prize(rec):
        intro = INTRO_LINE.replace("{noun}", INTRO_NOUN.get(rec.get("category"), "item"))
        lines = [intro.replace("[release date/rarity]", rec.get("intro_hook") or "[release date/rarity]"),
                 "", BBTS_PLACEHOLDER, ""]
        lines += [f"- {k}: {v}" for k, v in details]
        lines += ["- Condition: Brand new, factory sealed"]
    else:   # no claw-machine / figurine wording, no BBTS
        lines = [rec.get("intro_line") or "TODO: opening sentence", "", OTHER_PLACEHOLDER, ""]
        lines += [f"- {k}: {v}" for k, v in details if k != "Height"]
        lines += ["- Condition: TODO"]
    return "\n".join(lines)


BBTS_PLACEHOLDER = "[paste BBTS description here, or delete this line]"
OTHER_PLACEHOLDER = "[add details (what's included, condition notes), or delete this line]"


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
           f"category = {_toml_str(kind)}      # Figure, Plush, or any eBay category id, e.g. \"178893\"",
           "condition_id = 1000     # 1000 New, 1500 New other (open box), 3000 Used",
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
    house = HOUSE_SPECIFICS if is_prize(rec) else {}   # house values only replace Claude's on prize items
    specifics = {k: v for k, v in (rec.get("item_specifics") or {}).items()
                 if k not in ("UPC", "EAN", "Condition") and k not in house}
    if barcode:   # one barcode field: UPC for US codes, EAN for JAN/EAN-13
        specifics["UPC" if barcode.startswith("0") else "EAN"] = barcode[1:] if barcode.startswith("0") else barcode

    cats = ebay.get("categories") or {}
    chosen = cats.get(rec.get("category")) or cats.get("Figure")
    if chosen and is_prize(rec):   # house values: prize items only, and only fields this category has
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
    toml_specifics = dict(specifics, **{m: "TODO (required by eBay)" for m in missing})
    kind = rec.get("category") if rec.get("category") in cats else "Figure"
    toml_category = str(chosen["id"]) if kind == "Other" and chosen else kind

    # draft.md = research only. Title/specifics/description live ONLY in listing.toml,
    # so there's one place to edit and publish.py reads exactly what you edited.
    md = [f"# {rec.get('name') or folder_name}", "",
          f"_Research for `{folder_name}`, {date.today():%m/%d/%y}. "
          "**Edit the listing in `listing.toml`**; this file is read-only notes._", ""]
    md += warn + ([""] if warn else [])
    todo = []
    if missing:
        todo.append("Required by eBay, not found: " + ", ".join(missing) + " (marked TODO in listing.toml)")
    todo += list(rec.get("uncertain") or [])
    if todo:
        md += ["## Check these", ""] + [f"- {u}" for u in todo] + [""]
    if rec.get("box_facts"):
        md += ["## From the box", ""] + [f"- {f}" for f in rec["box_facts"]] + [""]
    md += ["## Price research", "",
           "Active listings right now (asking prices, not sold). US sellers are your real competition; "
           "abroad totals include international shipping:"]
    md += price_lines(ebay.get("prices", {}))
    md += ["", "Other platforms: " + ", ".join(
        f"{p} {'= eBay' if not m else f'= eBay + ${m:.0f}'}" for p, m in PLATFORM_MARKUP.items() if p != "eBay"), ""]
    md += ["## Category", "", f"{kind}: " + (f"{chosen['path']} (id {chosen['id']})" if chosen else "—")
           + (f", {chosen['how']}" if chosen and chosen.get("how") else "")]
    other_votes = [c for c in ebay.get("category_votes") or [] if not chosen or c["id"] != chosen["id"]]
    if other_votes:
        md += ["", "Other categories sellers used: " + "; ".join(
            f"{c['path']} ({c['id']}, {c['listings']})" for c in other_votes[:3])]
    sim = ebay.get("similar")
    if sim:
        md += ["", f"_Exact matches were thin, so specs also drew on {sim['n_listings']} similar listings "
               f"for \"{sim['query']}\" (any color/version)._"]
    md += [""]
    md += ["## Products row (paste into Shop Ledger > Products, column B)", "",
           "```", products_row(rec, barcode), "```", ""]
    return "\n".join(md), listing_toml(photos, title, toml_category, toml_specifics, description_text(rec, details))


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
