"""eBay user sign-in (OAuth authorization-code flow) for selling calls.

The app keys in .env only allow reading public listings. Creating listings, uploading
photos and reading your business policies need a *user* token: you sign in to eBay once,
approve this app, and we keep the refresh token (valid ~18 months) in .cache/, which is
gitignored. Access tokens (2 h) are refreshed automatically from it.
"""
import base64, json, os, sys, time, urllib.error, urllib.parse, urllib.request

from .config import ROOT

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
CONSENT_URL = "https://auth.ebay.com/oauth2/authorize"
SCOPES = [
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.inventory",          # listings + photo upload
    "https://api.ebay.com/oauth/api_scope/sell.account.readonly",   # read business policies
]
TOKEN_FILE = ROOT / ".cache" / "ebay_user_token.json"


def _basic():
    cid, sec = os.environ.get("EBAY_CLIENT_ID"), os.environ.get("EBAY_CLIENT_SECRET")
    if not cid or not sec:
        sys.exit("Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET in .env first.")
    return cid, "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode()


def _post(form):
    _, auth = _basic()
    req = urllib.request.Request(TOKEN_URL, data=urllib.parse.urlencode(form).encode(), headers={
        "Authorization": auth, "Content-Type": "application/x-www-form-urlencoded"})
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        sys.exit(f"eBay token call failed: HTTP {e.code}\n{e.read().decode()}")


def consent_url():
    cid, _ = _basic()
    runame = os.environ.get("EBAY_RUNAME")
    if not runame:
        sys.exit("Set EBAY_RUNAME in .env (see README: 'eBay sign-in').")
    return CONSENT_URL + "?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": runame, "response_type": "code", "scope": " ".join(SCOPES)},
        quote_via=urllib.parse.quote)   # eBay wants scopes separated by %20, not '+'



def exchange(pasted):
    """Accept the full redirected URL (or just the code) and store the tokens."""
    code = pasted.strip()
    if "code=" in code:
        code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query)["code"][0]
    tok = _post({"grant_type": "authorization_code", "code": code, "redirect_uri": os.environ["EBAY_RUNAME"]})
    _save(tok)
    return tok


def _save(tok, keep_refresh=None):
    now = time.time()
    data = {"access_token": tok["access_token"], "access_expires": now + tok.get("expires_in", 7200) - 120,
            "refresh_token": tok.get("refresh_token") or keep_refresh,
            "refresh_expires": now + tok["refresh_token_expires_in"] if "refresh_token_expires_in" in tok
            else (json.loads(TOKEN_FILE.read_text()).get("refresh_expires") if TOKEN_FILE.exists() else None)}
    TOKEN_FILE.parent.mkdir(exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(data, indent=1))
    os.chmod(TOKEN_FILE, 0o600)


def user_token():
    if not TOKEN_FILE.exists():
        sys.exit("Not signed in to eBay yet. Run: python3 auth.py")
    data = json.loads(TOKEN_FILE.read_text())
    if time.time() < data["access_expires"]:
        return data["access_token"]
    if data.get("refresh_expires") and time.time() > data["refresh_expires"]:
        sys.exit("eBay sign-in expired (they last ~18 months). Run: python3 auth.py")
    tok = _post({"grant_type": "refresh_token", "refresh_token": data["refresh_token"], "scope": " ".join(SCOPES)})
    _save(tok, keep_refresh=data["refresh_token"])
    return tok["access_token"]


def user_get(path, **params):
    url = "https://api.ebay.com" + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {user_token()}"})
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        print(f"  ! {path} HTTP {e.code}: {e.read().decode()[:300]}", file=sys.stderr)
        return {}
