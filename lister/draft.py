"""Per-item outputs: draft.md (research to read), listing.toml (the listing to edit), draft.json (raw)."""
import json
import re
from datetime import date

from .config import house_specifics, time_period, INTRO_LINE, INTRO_NOUN, PLATFORM_MARKUP, TITLE_SUFFIX
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


def _median_new(prices, us_only):
    """(n, low, median) for new listings, US sellers only or any location."""
    keys = ["New, ships from US"] if us_only else ["New, ships from US", "New, ships from abroad"]
    tot = [c for k in keys for c in [prices.get(k)] if c]
    if not tot:
        return None
    n = sum(c["n"] for c in tot)
    low = min(c["low"] for c in tot)
    med = tot[0]["median"] if len(tot) == 1 else round(sum(c["median"] * c["n"] for c in tot) / n, 2)
    return n, low, med


def lot_price_lines(ebay, rec):
    """Per-item table, sum of singles, and comparable lots."""
    out = ["", "| Item | Barcode | New, US sellers (n · low · median) | New, anywhere (n · median) |", "|---|---|---|---|"]
    sum_us, sum_any, complete_us = 0.0, 0.0, True
    names = {i.get("barcode"): i.get("name") for i in (rec.get("items") or [])}
    for info in ebay["lot"]:
        us, anyw = _median_new(info["prices"], True), _median_new(info["prices"], False)
        label = names.get(info["barcode"]) or (info["titles"][0][:45] if info["titles"] else "?")
        out.append(f"| {label} | {info['barcode']} | "
                   + (f"{us[0]} · ${us[1]:.2f} · ${us[2]:.2f}" if us else "none")
                   + " | " + (f"{anyw[0]} · ${anyw[2]:.2f}" if anyw else "none") + " |")
        if us:
            sum_us += us[2]
        else:
            complete_us = False
        if anyw:
            sum_any += anyw[2]
    out.append(f"| **Sum of singles** | | **${sum_us:.2f}**" + ("" if complete_us else " (some items have no US listings)")
               + f" | ${sum_any:.2f} |")
    comps = ebay.get("lot_comps")
    if comps:
        out += ["", f"Comparable lots for \"{comps['query']}\" ({comps['n_listings']} found):"]
        out += price_lines(comps.get("prices", {}))
    out += ["", "_Singles each pay their own shipping (~$5-6 each, buyer-paid); a lot pays it once. "
            "If one item's median is far above the rest, consider selling it alone and lotting the others._"]
    return out


def products_row(rec, barcode):
    """Products columns B..K (stop before the auto columns M/N)."""
    return "\t".join([rec.get("name", ""), rec.get("category", ""), rec.get("franchise", ""),
                      rec.get("line", ""), rec.get("character", ""), rec.get("variant", ""),
                      rec.get("maker", ""), barcode or "", barcode_kind(barcode) if barcode else "",
                      rec.get("height", "")])


def is_prize(rec):
    return rec.get("category") in ("Figure", "Plush")


def lot_lines(rec):
    items = rec.get("items") or []
    if not items:
        return []
    return [f"This lot includes {len(items)} items:"] + [f"- {i.get('name') or i.get('barcode')}" for i in items] + [""]


def description_text(rec, details):
    lot = bool(rec.get("items"))
    if is_prize(rec) or (lot and rec.get("intro_hook")):
        noun = "lot" if lot else INTRO_NOUN.get(rec.get("category"), "item")
        intro = INTRO_LINE.replace("{noun}", noun)
        lines = [intro.replace("[release date/rarity]", rec.get("intro_hook") or "[release date/rarity]"),
                 ""] + lot_lines(rec) + [BBTS_PLACEHOLDER, ""]
        lines += [f"- {k}: {v}" for k, v in details]
        lines += ["- Condition: Brand new, factory sealed"]
    else:   # no claw-machine / figurine wording, no BBTS
        lines = [rec.get("intro_line") or "TODO: opening sentence", ""] + lot_lines(rec) + [OTHER_PLACEHOLDER, ""]
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
           "# listing order; first = main photo. stock/ = web images (put after yours by default)",
           "photos = [" + ", ".join(_toml_str(p) for p in photos) + "]", "",
           "# Plain text. Blank line = new paragraph, '- ' lines = bullet list.",
           "description = '''", description.replace("'''", '"""'), "'''", "",
           "[package]   # TODO: packed weight and box size",
           "weight_lb = 0", "weight_oz = 0", "length_in = 0", "width_in = 0", "height_in = 0", "",
           "[specifics]"]
    out += [f"{_toml_str(k)} = {_toml_str(v)}" for k, v in specifics.items()]
    return "\n".join(out) + "\n"


def render(folder_name, photos, barcode, ebay, rec):
    house = house_specifics(rec.get("category"))   # {} unless Figure/Plush; these replace Claude's values
    specifics = {k: v for k, v in (rec.get("item_specifics") or {}).items()
                 if k not in ("UPC", "EAN", "Condition") and k not in house}
    lot = ebay.get("lot")   # lot mode: list of per-barcode research
    if barcode and not lot:   # one barcode field: UPC for US codes, EAN for JAN/EAN-13
        specifics["UPC" if barcode.startswith("0") else "EAN"] = barcode[1:] if barcode.startswith("0") else barcode

    cats = ebay.get("categories") or {}
    chosen = cats.get(rec.get("category")) or cats.get("Figure")
    if chosen and house:   # only fields this category actually has (required, recommended or optional)
        a = chosen["aspects"]
        allowed = {x["name"] for k in ("required", "recommended") for x in a[k]} | set(a.get("optional", []))
        for k, v in house.items():
            if k in allowed or not allowed:
                specifics[k] = v
        if "Time Period Manufactured" in allowed or not allowed:   # from the year if known, else default
            specifics["Time Period Manufactured"] = time_period(specifics.get("Year Manufactured"))
    missing = []
    if chosen:
        names = {k.lower() for k in specifics}
        missing = [a["name"] for a in chosen["aspects"]["required"]
                   if a["name"].lower() not in names and a["name"] not in ("UPC", "EAN", "Condition")]
    details = [(k, v) for k, v in (("Maker", rec.get("maker")), ("Line", rec.get("line")))
               if v] if lot else [(k, v) for k, v in (("Maker", rec.get("maker")), ("Line", rec.get("line")),
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
    cjk = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uff00-\uffef]")
    for label, text in (("Title", title), ("Intro", rec.get("intro_hook") or rec.get("intro_line") or ""),
                        ("Specifics", " ".join(map(str, specifics.values())))):
        if cjk.search(text):
            todo.insert(0, f"{label} contains Japanese characters; romanize or remove them in listing.toml")
    if todo:
        md += ["## Check these", ""] + [f"- {u}" for u in todo] + [""]
    if rec.get("box_facts"):
        md += ["## From the box", ""] + [f"- {f}" for f in rec["box_facts"]] + [""]
    md += ["## Price research", "",
           "Active listings right now (asking prices, not sold). US sellers are your real competition; "
           "abroad totals include international shipping:"]
    md += lot_price_lines(ebay, rec) if lot else price_lines(ebay.get("prices", {}))
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
           "```"] + ([products_row({**rec, **i, "category": rec.get("category")}, i.get("barcode", ""))
                      for i in rec.get("items") or []] if lot else [products_row(rec, barcode)]) + ["```", ""]
    return "\n".join(md), listing_toml(photos, title, toml_category, toml_specifics, description_text(rec, details))


def save(folder, photos, barcode, ebay, rec, overwrite_listing=False):
    """photos = your photos (what Claude saw). The listing gets them plus stock/ images,
    read from disk now, so stock added later shows up on --render too."""
    from .photos import stock
    md, toml = render(folder.name, list(photos) + stock(folder), barcode, ebay, rec)
    (folder / "draft.md").write_text(md)
    lt = folder / "listing.toml"
    if overwrite_listing or not lt.exists():
        lt.write_text(toml)
    else:
        (folder / "listing.new.toml").write_text(toml)
        print("  (kept your edited listing.toml; the fresh one is listing.new.toml)")
    from .claude import USAGE_LOG
    prev = json.loads((folder / "draft.json").read_text()) if (folder / "draft.json").exists() else {}
    usage = list(USAGE_LOG) or prev.get("claude_usage", [])   # --render keeps the original numbers
    USAGE_LOG.clear()
    (folder / "draft.json").write_text(json.dumps(
        {"barcode": barcode, "photos": photos, "record": rec, "ebay": ebay, "claude_usage": usage},
        ensure_ascii=False, indent=1))
