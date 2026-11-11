"""eBay Browse API: barcode search, item specifics voting, active-price stats."""
import base64, json, os, re, statistics, sys
import urllib.error, urllib.parse, urllib.request
from collections import Counter, defaultdict

API = "https://api.ebay.com"
TOP_N_ASPECTS = 5
JUNK = {"", "na", "n/a", "none", "does not apply", "unbranded", "not applicable", "-", "unknown"}
LOT_WORDS = re.compile(r"\b(lot|bundle|set of \d|x\d|\d+\s*pcs|pick one|choose)\b", re.I)

_token = None


def token():
    global _token
    if _token:
        return _token
    cid, sec = os.environ.get("EBAY_CLIENT_ID"), os.environ.get("EBAY_CLIENT_SECRET")
    if not cid or not sec:
        sys.exit("Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET (in .env or the environment).")
    req = urllib.request.Request(
        f"{API}/identity/v1/oauth2/token",
        data=urllib.parse.urlencode({"grant_type": "client_credentials",
                                     "scope": "https://api.ebay.com/oauth/api_scope"}).encode(),
        headers={"Authorization": "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode(),
                 "Content-Type": "application/x-www-form-urlencoded"})
    try:
        _token = json.load(urllib.request.urlopen(req))["access_token"]
    except urllib.error.HTTPError as e:
        sys.exit(f"eBay token request failed: HTTP {e.code}\n{e.read().decode()}")
    return _token


def get(path, **params):
    url = f"{API}{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token()}",
                                               "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
                                               # shipping estimates as if the buyer is in the US
                                               "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%3DUS%2Czip%3D94103"})
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        print(f"  ! {path} HTTP {e.code}: {e.read().decode()[:200]}", file=sys.stderr)
        return {}


def search(code=None, q=None):
    """Listings worldwide (shown on ebay.com) by barcode (+ the number as keywords), or by text.

    Not limited to US sellers: many of these items are mostly listed by sellers in Japan,
    and their item specifics are still good. Prices are split US vs. abroad later.
    """
    flt = "buyingOptions:{FIXED_PRICE|AUCTION}"
    runs = [("gtin", {"gtin": code}), ("keyword", {"q": code})] if code else [("keyword", {"q": q})]
    seen, out = set(), []
    for how, params in runs:
        # Keyword hits on the number are looser (sellers paste several codes, e.g. the normal
        # and Black Ver. of the same figure), so only use them when barcode hits are thin.
        if how == "keyword" and code and sum(it["_via"] == "gtin" for it in out) >= 3:
            break
        for it in get("/buy/browse/v1/item_summary/search", limit=50, filter=flt, **params).get("itemSummaries", []):
            if it["itemId"] not in seen:
                seen.add(it["itemId"])
                it["_via"] = how
                out.append(it)
    return [it for it in out if not LOT_WORDS.search(it.get("title", ""))]


def details(items, n=TOP_N_ASPECTS):
    # barcode matches first, then US sellers (English specifics)
    ranked = sorted(items, key=lambda it: (it["_via"] != "gtin",
                                           (it.get("itemLocation") or {}).get("country") != "US"))[:n]
    return [get(f"/buy/browse/v1/item/{urllib.parse.quote(it['itemId'])}") for it in ranked]


def vote_aspects(dets):
    votes = defaultdict(Counter)
    for d in dets:
        have = {a["name"] for a in d.get("localizedAspects", [])}
        for a in d.get("localizedAspects", []):
            v = (a.get("value") or "").strip()
            if v.lower() not in JUNK:
                votes[a["name"]][v] += 1
        for k, name in (("brand", "Brand"), ("mpn", "MPN")):
            if name not in have and d.get(k) and d[k].lower() not in JUNK:
                votes[name][d[k]] += 1
    return votes


def prices(items):
    """{'New': {...}, 'Used/other': {...}} with totals incl. shipping, cheapest 3 listed."""
    groups = defaultdict(list)
    for it in items:
        try:
            p = float(it["price"]["value"])
        except (KeyError, ValueError):
            continue
        ship = 0.0
        opts = it.get("shippingOptions") or []
        if opts and opts[0].get("shippingCost"):
            try:
                ship = float(opts[0]["shippingCost"]["value"])
            except (KeyError, ValueError):
                pass
        cond = "New" if (it.get("condition") or "").lower().startswith("new") else "Used/other"
        where = "US" if (it.get("itemLocation") or {}).get("country") == "US" else "abroad"
        groups[f"{cond}, ships from {where}"].append({"total": round(p + ship, 2), "price": p, "title": it["title"],
                             "url": it.get("itemWebUrl", "").split("?")[0]})
    out = {}
    order = ["New, ships from US", "Used/other, ships from US", "New, ships from abroad", "Used/other, ships from abroad"]
    for cond in [k for k in order if k in groups]:
        g = groups[cond]
        g.sort(key=lambda x: x["total"])
        t = [x["total"] for x in g]
        out[cond] = {"n": len(g), "low": t[0], "median": round(statistics.median(t), 2),
                     "high": t[-1], "cheapest": g[:3]}
    return out


def gather(code=None, q=None):
    """Everything the cleanup step needs about one product."""
    items = search(code=code, q=q)
    dets = details(items) if items else []
    votes = vote_aspects(dets)
    cat_ids = Counter(d.get("categoryId") for d in dets if d.get("categoryId"))
    return {
        "query": code or q,
        "n_listings": len(items),
        "n_us": sum((it.get("itemLocation") or {}).get("country") == "US" for it in items),
        "n_detailed": len(dets),
        "titles": [("[barcode match] " if it["_via"] == "gtin" else "") + it["title"]
                   for it in sorted(items, key=lambda it: it["_via"] != "gtin")[:15]],
        "aspect_votes": {k: dict(v.most_common(4)) for k, v in votes.items()},
        "ebay_category_id": cat_ids.most_common(1)[0][0] if cat_ids else "",
        "ebay_category_path": next((d.get("categoryPath") for d in dets if d.get("categoryPath")), ""),
        "epid": next((d.get("epid") for d in dets if d.get("epid")), ""),
        "prices": prices(items),
    }


def barcode_kind(code):
    if len(code) == 13 and code[:2] in ("45", "49"):
        return "JAN"
    if len(code) == 12 or code.startswith("0"):
        return "UPC (distributor)"
    return "Other"
