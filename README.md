# claw-lister

Photos of a claw-machine prize in, a draft listing out.

```
~/Listings/inbox/<item>/  (photos)  ──list.py──▶  draft.md + draft.json in the same folder
```

1. **Identify** — read the JAN/UPC barcode from the photos (`pyzbar`). No barcode? Claude reads the box.
2. **Look up** — eBay Browse API: listings for that barcode (worldwide sellers, since many of these are mostly listed from Japan), item specifics from the top 5 (with how many agree), active prices split US vs. abroad.
3. **Clean up** — Claude checks the eBay matches against your photos and writes the name (house format), an 80-char eBay title, and item specifics.
4. **Draft** — `listing.toml`: the listing you edit (title, specifics, your intro line, a slot for the BBTS description, price, package). `draft.md`: research to read alongside it (things to check, box facts, price snapshot, a Products row to paste into the Shop Ledger).

5. **Publish** — you finish `listing.toml` (price, package weight/size, description); `publish.py` uploads the photos, does an eBay dry run (errors + fees), then creates the listing *scheduled 21 days out*, so it waits under Seller Hub > Scheduled as a de-facto draft.

Not built yet: crosslist copy for Mercari/Depop/FB.

## Setup (each computer, nothing installed globally)

```bash
git clone https://github.com/ryanrashid/claw-lister && cd claw-lister
python3 -m venv .venv            # needs Python 3.11+ (check: python3 --version)
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # zxing-cpp + pillow, inside .venv only
cp .env.example .env               # fill in the eBay Production App ID + Cert ID
```

Run the scripts with the venv active (or call `.venv/bin/python list.py` directly).

**Claude CLI.** If `claude` already works in your terminal, nothing to do. Otherwise install it
inside the project instead of globally, log in once, and point `.env` at it:

```bash
npm install @anthropic-ai/claude-code      # creates ./node_modules (gitignored)
./node_modules/.bin/claude                 # log in, then exit
echo "CLAUDE_BIN=$PWD/node_modules/.bin/claude" >> .env
```

Claude runs on your Pro plan through that CLI. Don't set `ANTHROPIC_API_KEY`
(the scripts strip it anyway) or it would bill an API key instead.

## eBay sign-in (for creating listings)

The `.env` keys can only read public listings. Listing for you needs a one-time sign-in:

1. developer.ebay.com → Application Keys → **User Tokens** (Production keyset) →
   "Get a Token from eBay via Your Application" → add an eBay Redirect URL. The "auth accepted"
   URL can be any https page (e.g. `https://example.com/ok`). Copy the **RuName** it shows.
2. Put it in `.env` as `EBAY_RUNAME=...`
3. `python3 auth.py` → approve in the browser → paste back the address you land on.
   The token is kept in `.cache/` (gitignored) and lasts ~18 months; it prints your business policies.

## Use

```bash
python3 list.py                     # every inbox folder without a draft.md
python3 list.py ~/Listings/inbox/x  # specific folders
python3 list.py --redo              # rebuild drafts
python3 lookup.py 4580779532934     # quick eBay check, no photos / no Claude
python3 lookup.py "desktop cute hitagi"
python3 auth.py                     # once: eBay sign-in, prints your business policies
python3 publish.py ~/Listings/inbox/x --check   # dry run only
python3 publish.py ~/Listings/inbox/x           # dry run, then asks, then lists (scheduled)
```

**Fees in the dry run are eBay's estimate.** eBay's docs say Verify calls may leave out discounts, and the free monthly listing allowance isn't reliably applied there, so a $0.35 insertion fee can show even when you have free listings left. Check the real charge in Seller Hub > Payments after listing.

Each item folder ends up with `draft.md` (read), `listing.toml` (edit; `--redo` won't overwrite it,
it writes `listing.new.toml` instead), and after publishing `published.json` + `.photos.json`.

One folder per item. If a folder has two different barcodes, it warns: split it.

How each step works (code, APIs, logic): see [ARCHITECTURE.md](ARCHITECTURE.md).

## Layout

| File | What |
|---|---|
| `list.py` | the pipeline (steps 1–4) |
| `lookup.py` | barcode/text → eBay specifics + prices, printed |
| `lister/config.py` | `.env` loading, intro line, naming rule, platform markups |
| `lister/barcode.py` | barcode reading |
| `lister/ebay.py` | eBay auth, search, specifics voting, price stats |
| `lister/claude.py` | `claude -p` prompts (box reading, cleanup) |
| `lister/draft.py` | draft.md / listing.toml / draft.json |
| `publish.py`, `lister/trading.py` | photo upload, dry run, listing (Trading API) |
| `auth.py`, `lister/auth.py` | eBay sign-in, business policies |
