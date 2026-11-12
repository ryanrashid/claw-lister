"""Calls the local Claude Code CLI (`claude -p`), which runs on your Claude Pro plan.

ANTHROPIC_API_KEY is removed from the child environment on purpose: if it were set,
the CLI would bill the API key instead of using your subscription.
"""
import base64, io, json, os, re, shutil, subprocess, sys
from pathlib import Path

from .config import CLAUDE_IMAGE_MAX, CLAUDE_LEAN, CLAUDE_MODEL

TIMEOUT = 300
USAGE_LOG = []   # one entry per claude -p call in this run: {"call", "input", "cache_read", "output", ...}
MAX_PHOTOS = 6   # more photos = slower and uses more of your Pro limit


def _log_usage(out, label):
    """Record what the CLI reports for this call. Input tokens include Claude Code's own
    system prompt/tool definitions plus the photos; cache reads are much cheaper than fresh input."""
    u = out.get("usage") or {}
    entry = {"call": label,
             "input": u.get("input_tokens", 0),
             "cache_write": u.get("cache_creation_input_tokens", 0),
             "cache_read": u.get("cache_read_input_tokens", 0),
             "output": u.get("output_tokens", 0),
             "turns": out.get("num_turns"),
             "seconds": round((out.get("duration_ms") or 0) / 1000, 1),
             "model": ",".join((out.get("modelUsage") or {}).keys())}
    USAGE_LOG.append(entry)
    print(f"  [claude {label}] in {entry['input']:,} + cache write {entry['cache_write']:,} "
          f"+ cache read {entry['cache_read']:,} · out {entry['output']:,} · "
          f"{entry['turns']} turns · {entry['seconds']}s {entry['model']}")


SYSTEM = ("You extract structured product data from photos and marketplace listings for an eBay "
          "seller. Follow the user's rules exactly and reply with only the JSON object requested.")
PHOTOS = "<<PHOTOS>>"   # placeholder in prompts; replaced per mode below


def _exe():
    exe = os.environ.get("CLAUDE_BIN") or "claude"
    if not shutil.which(exe):
        sys.exit(f"Can't find the Claude CLI ({exe}). Install it (see README) or set CLAUDE_BIN in .env.")
    return exe


def _env():
    return {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}


def _model_args():
    model = os.environ.get("CLAUDE_MODEL", CLAUDE_MODEL)
    return ["--model", model] if model else []


def _image_block(path):
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((CLAUDE_IMAGE_MAX, CLAUDE_IMAGE_MAX))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(buf.getvalue()).decode()}}


def _run_lean(prompt, photos, cwd):
    """One turn: photos inline as image blocks, short system prompt, no tools, no MCP servers."""
    content = [_image_block(Path(cwd) / n) for n in photos]
    content.append({"type": "text", "text": prompt.replace(
        PHOTOS, f"The {len(photos)} photos of the item are attached above, in this order: {', '.join(photos)}.")})
    msg = json.dumps({"type": "user", "message": {"role": "user", "content": content}})
    proc = subprocess.run(
        [_exe(), "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
         "--system-prompt", SYSTEM, "--tools", "", "--strict-mcp-config", *_model_args()],
        input=msg + "\n", cwd=cwd, env=_env(), capture_output=True, text=True, timeout=TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(f"lean claude -p failed ({proc.returncode}): {proc.stderr[:400]}")
    result = next((json.loads(l) for l in reversed(proc.stdout.splitlines())
                   if l.strip().startswith("{") and json.loads(l).get("type") == "result"), None)
    if not result:
        raise RuntimeError(f"lean claude -p: no result event in output: {proc.stdout[-400:]}")
    return result


def _run_tools(prompt, photos, cwd):
    """Fallback: Claude opens the photos with its Read tool (several turns, default system prompt)."""
    proc = subprocess.run(
        [_exe(), "-p", prompt.replace(PHOTOS, "First use the Read tool to look at these photos in the "
                                      f"current folder (open them all at once): {', '.join(photos)}."),
         "--output-format", "json", "--allowedTools", "Read", "--strict-mcp-config", *_model_args()],
        cwd=cwd, env=_env(), capture_output=True, text=True, timeout=TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed ({proc.returncode}): {proc.stderr[:500]}")
    return json.loads(proc.stdout)


def ask_json(prompt, photos, cwd, label="call"):
    photos = list(photos)[:MAX_PHOTOS]
    out = None
    if CLAUDE_LEAN:
        try:
            out = _run_lean(prompt, photos, cwd)
        except Exception as e:   # CLI version without these flags, etc.
            print(f"  ! lean Claude call failed, falling back to the Read-tool mode: {e}")
    if out is None:
        out = _run_tools(prompt, photos, cwd)
    _log_usage(out, label)
    text = out.get("result", "")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise RuntimeError(f"No JSON in Claude's answer:\n{text[:500]}")
    return json.loads(m.group(0))


def read_box(photo_names, cwd):
    """No barcode decoded: identify the item from packaging, tags, and the item itself."""
    prompt = f"""You are identifying a Japanese prize figure or plush from product photos.
<<PHOTOS>>
Figures usually come in a printed box. Plushies often have no box: use the paper hang tag and the
sewn-in fabric tag (maker such as SEGA, Taito, FuRyu, Bandai Spirits, San-X, Sanrio; series name; size
in cm; prize code), plus the character itself.

Reply with ONLY a JSON object:
{{"search_query": "best eBay search to find this exact item: maker, line/series, character, variant, and 'plush' or 'figure', plus size for plushies (e.g. '30cm'); English, no filler words",
  "barcode_digits": "any JAN/UPC digits printed on a box or tag, else empty",
  "box_text": "important text you can read on box or tags (maker, line, character, version, year, size)",
  "confidence": "high|medium|low"}}"""
    return ask_json(prompt, photo_names, cwd, "read_box")


def clean_up(photo_names, barcode, ebay, name_rule, cwd):
    """Turn noisy eBay data + photos into one consistent product record and eBay fields."""
    from .config import HOUSE_SPECIFICS, TITLE_SUFFIX
    house_keys = ", ".join(HOUSE_SPECIFICS)
    title_max = 80 - len(TITLE_SUFFIX)
    evidence = {k: ebay.get(k) for k in ("n_listings", "titles", "aspect_votes", "aspect_votes_other_sites")}
    similar = ebay.get("similar")
    prompt = f"""You are preparing an eBay listing. Usually the item is a new, unopened Japanese prize figure or
plush won from a claw machine; sometimes it's other goods (electronics, games, ...).
<<PHOTOS>>

Barcode on the item: {barcode or "none found"}

EXACT MATCHES: active eBay listings for this barcode/search (titles; item-specific values with how many
listings gave each). "aspect_votes" are from ebay.com listings; "aspect_votes_other_sites" are from other
eBay sites, with the site in brackets: their names/values are in that language, so translate them.
{json.dumps(evidence, ensure_ascii=False, indent=1)}

SIMILAR LISTINGS (same brand+model, any variant/color; only searched when exact matches were thin):
{json.dumps(similar, ensure_ascii=False, indent=1) if similar else "none"}

CATEGORIES by item type, each with the item specifics eBay requires/recommends there
("allowed" = eBay only accepts those values). "Figure" and "Plush" are fixed; "Other" is the category
ebay.com sellers used for this item (or eBay's suggestion):
{json.dumps(ebay.get("categories", {}), ensure_ascii=False, indent=1)}

Rules:
- The photos are the ground truth. If the exact matches describe a different item or variant, say so in "match_note" and set "matches_photos" to false.
- category: "Figure" or "Plush" for prize figures/plushies, otherwise "Other".
- Name: for Figure/Plush use {name_rule}. Franchise = the series it comes from (e.g. "The Legend of Zelda: Tears of the Kingdom"), Line = the prize line (e.g. "FIGURIZMα", "Desktop Cute", "BiCute Bunnies"), Variant whenever this item differs from the standard release: a color/outfit version visible in the photos or named by the [barcode match] listings (e.g. "Black Ver."), or an edition named on the box (e.g. "Reissue"). Titles marked [barcode match] have this exact barcode and outrank the rest. Don't repeat a word already in an earlier part. For Other: "Brand Model Variant/Color" (put Brand in "maker", model in "line", color/version in "variant").
- Identity and variant come ONLY from the photos and the exact matches. Similar listings may be a different color/version: use them only for model-level specs (size, material, connectivity, compatibility...).
- ebay_title: max {title_max} characters (a suffix gets added after it), buyer search terms first (franchise, character, line, maker, "Figure"/"Plush"; or brand, model, color, type for Other), then "New" / "Japan" / "Authentic" if room and true. No emojis, no all caps words except brand names. Keep product-line names as printed, including symbols (write "FIGURIZMα", not "FIGURIZM Alpha").
- Don't flag Country of Origin / manufacture location in "uncertain" for Figure/Plush; the owner sets it.
- item_specifics: use exactly the aspect names of the category you chose; fill every required one and as many recommended ones as the evidence supports, in English; for "allowed" aspects use one of the listed values. A value needs one of: the photos/box/tag, 2+ listings agreeing, or (for model-level specs only) 1 listing that plainly describes this same model and isn't contradicted. Don't include UPC/EAN or Condition{", or these fields the owner sets himself for Figure/Plush: " + house_keys if house_keys else ""}.
- intro_hook (Figure/Plush only): a short phrase that completes "This figurine/plush is ___ so get it here now!" using only facts from the box or listings (e.g. "a 2025 FuRyu prize exclusive, one version only"). Empty if nothing true and interesting.
- intro_line (Other only): one plain, factual opening sentence for the description (what it is, condition, what's included). No claw-machine wording.
- Buyer-facing text (name, ebay_title, intro_hook, intro_line, item_specifics values) must be in English: romanize Japanese names (e.g. 黒星紅白 -> Kuroboshi Kouhaku), never paste Japanese characters there. Japanese is fine in box_facts.
- height: use the best value you have (box/tag first, then listings); if it isn't on the box/tag or at least 2 listings don't agree, still fill it in but say so in "uncertain".
- box_facts: other useful facts read from the packaging (manufacture date, made in, sculptor, distributor sticker, wear), one per item.
- Put anything you are unsure about in "uncertain" so a human checks it.

Reply with ONLY a JSON object:
{{"matches_photos": true, "match_note": "",
  "name": "", "category": "Figure|Plush|Other",
  "franchise": "", "line": "", "character": "", "variant": "", "maker": "",
  "height": "", "intro_hook": "", "intro_line": "", "box_facts": [],
  "ebay_title": "",
  "item_specifics": {{}},
  "uncertain": []}}"""
    return ask_json(prompt, photo_names, cwd, "clean_up")
