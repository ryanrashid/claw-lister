"""Calls the local Claude Code CLI (`claude -p`), which runs on your Claude Pro plan.

ANTHROPIC_API_KEY is removed from the child environment on purpose: if it were set,
the CLI would bill the API key instead of using your subscription.
"""
import json, os, re, shutil, subprocess, sys

TIMEOUT = 300
MAX_PHOTOS = 6   # more photos = slower and uses more of your Pro limit


def ask_json(prompt, cwd):
    exe = os.environ.get("CLAUDE_BIN") or "claude"
    if not shutil.which(exe):
        sys.exit(f"Can't find the Claude CLI ({exe}). Install it (see README) or set CLAUDE_BIN in .env.")
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    proc = subprocess.run(
        [exe, "-p", prompt, "--output-format", "json", "--allowedTools", "Read"],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed ({proc.returncode}): {proc.stderr[:500]}")
    text = json.loads(proc.stdout).get("result", "")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise RuntimeError(f"No JSON in Claude's answer:\n{text[:500]}")
    return json.loads(m.group(0))


def read_box(photo_names, cwd):
    """No barcode found: identify the item from the packaging."""
    prompt = f"""You are identifying a Japanese prize figure or plush from product photos.
Use the Read tool to look at each of these files in the current folder: {', '.join(photo_names[:MAX_PHOTOS])}.

Reply with ONLY a JSON object:
{{"search_query": "best eBay search to find this exact item (maker, line, character, variant; English)",
  "barcode_digits": "any JAN/UPC digits printed on the box, else empty",
  "box_text": "important text you can read (maker, line name, character, version, year, height)",
  "confidence": "high|medium|low"}}"""
    return ask_json(prompt, cwd)


def clean_up(photo_names, barcode, ebay, name_rule, cwd):
    """Turn noisy eBay data + photos into one consistent product record and eBay fields."""
    prompt = f"""You are preparing an eBay listing for a new, unopened Japanese prize figure or plush.
First use the Read tool to look at these photos in the current folder: {', '.join(photo_names[:MAX_PHOTOS])}.

Barcode on the box: {barcode or "none found"}
Data from active eBay listings found for this item (titles, and item-specific values with how many listings gave each):
{json.dumps({k: ebay[k] for k in ("n_listings", "titles", "aspect_votes")}, ensure_ascii=False, indent=1)}

eBay US category candidates, each with the item specifics eBay requires/recommends there
("allowed" = eBay only accepts those values):
{json.dumps(ebay.get("category_candidates", []), ensure_ascii=False, indent=1)}

Rules:
- The photos are the ground truth. If the eBay listings describe a different item or variant, say so in "match_note" and set "matches_photos" to false.
- Product name format: {name_rule}. Franchise = the series it comes from (e.g. "The Legend of Zelda: Tears of the Kingdom"), Line = the prize line (e.g. "FIGURIZMα", "Desktop Cute", "BiCute Bunnies"), Variant whenever this item differs from the standard release of that figure: a color/outfit version visible in the photos or named by the [barcode match] listings (e.g. "Black Ver."), or an edition named on the box (e.g. "Reissue"). Titles marked [barcode match] have this exact barcode and outrank the rest. Don't repeat a word already in an earlier part.
- ebay_title: max 80 characters, buyer search terms first (franchise, character, line, maker, "Figure"/"Plush"), then "New" / "Japan" / "Authentic" if room. No emojis, no all caps words except brand names.
- ebay_category_id: pick the best candidate for a boxed, non-articulated anime/game prize figure or plush (collectible figures/statues categories usually fit better than action figures). Empty if no candidates.
- item_specifics: use exactly the aspect names of the chosen category; fill every required one and as many recommended ones as the evidence supports; for "allowed" aspects use one of the listed values. Values must come from the photos/box or at least 2 listings. Don't include UPC/EAN (added automatically) or Condition.
- intro_hook: a short phrase that completes "This figurine is ___ so get it here now!" using only facts from the box or listings (e.g. "a 2025 FuRyu prize exclusive, one version only"). Empty if nothing true and interesting.
- box_facts: other useful facts read from the packaging (manufacture date, made in, sculptor, distributor sticker), one per item.
- Put anything you are unsure about in "uncertain" so a human checks it.

Reply with ONLY a JSON object:
{{"matches_photos": true, "match_note": "",
  "name": "", "category": "Figure|Plush|Other",
  "franchise": "", "line": "", "character": "", "variant": "", "maker": "",
  "height": "", "intro_hook": "", "box_facts": [],
  "ebay_title": "", "ebay_category_id": "",
  "item_specifics": {{}},
  "uncertain": []}}"""
    return ask_json(prompt, cwd)
