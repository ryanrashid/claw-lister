"""Calls the local Claude Code CLI (`claude -p`), which runs on your Claude Pro plan.

ANTHROPIC_API_KEY is removed from the child environment on purpose: if it were set,
the CLI would bill the API key instead of using your subscription.
"""
import json, os, re, shutil, subprocess, sys

TIMEOUT = 300
MAX_PHOTOS = 6   # more photos = slower and uses more of your Pro limit


def ask_json(prompt, cwd):
    if not shutil.which("claude"):
        sys.exit("The `claude` CLI isn't installed or not on PATH (npm i -g @anthropic-ai/claude-code, then run `claude` once to log in).")
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    proc = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json", "--allowedTools", "Read"],
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
Data from active US eBay listings found for this item (titles, and item-specific values with how many listings gave each):
{json.dumps({k: ebay[k] for k in ("n_listings", "titles", "aspect_votes", "ebay_category_path")}, ensure_ascii=False, indent=1)}

Rules:
- The photos are the ground truth. If the eBay listings describe a different item or variant, say so in "match_note" and set "matches_photos" to false.
- Product name format: {name_rule}. Franchise = the series it comes from (e.g. "The Legend of Zelda: Tears of the Kingdom"), Line = the prize line (e.g. "FIGURIZMα", "Desktop Cute", "BiCute Bunnies"), Variant only if the box or most listings name one (e.g. "Black Ver.", "Reissue"). Don't repeat a word already in an earlier part.
- ebay_title: max 80 characters, buyer search terms first (franchise, character, line, maker, "Figure"/"Plush"), then "New" / "Japan" / "Authentic" if room. No emojis, no all caps words except brand names.
- item_specifics: only values supported by the photos or by at least 2 listings. Use eBay's names: Brand, Franchise, Character, Series, Type, Model, MPN, Material, Country of Origin, Item Height, Year Manufactured.
- Put anything you are unsure about in "uncertain" so a human checks it.

Reply with ONLY a JSON object:
{{"matches_photos": true, "match_note": "",
  "name": "", "category": "Figure|Plush|Other",
  "franchise": "", "line": "", "character": "", "variant": "", "maker": "",
  "height": "", "release_info": "anything on the box about year/edition/rarity",
  "ebay_title": "",
  "item_specifics": {{}},
  "uncertain": []}}"""
    return ask_json(prompt, cwd)
