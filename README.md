# claw-lister

Photos of a claw-machine prize in, a draft listing out.

```
~/Listings/inbox/<item>/  (photos)  ──list.py──▶  draft.md + draft.json in the same folder
```

1. **Identify** — read the JAN/UPC barcode from the photos (`pyzbar`). No barcode? Claude reads the box.
2. **Look up** — eBay Browse API: US listings for that barcode, item specifics from the top 5 (with how many agree), active prices.
3. **Clean up** — Claude checks the eBay matches against your photos and writes the name (house format), an 80-char eBay title, and item specifics.
4. **Draft** — `draft.md`: title, category, specifics, your intro line, a slot for the BBTS description, price snapshot, TODOs for weight and price, a Products row to paste into the Shop Ledger.

Not built yet: publishing the draft to eBay (Inventory API), crosslist copy for Mercari/Depop/FB.

## Setup (each computer, nothing installed globally)

```bash
git clone https://github.com/ryanrashid/claw-lister && cd claw-lister
python3 -m venv .venv            # needs Python 3.10+ (check: python3 --version)
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

## Use

```bash
python3 list.py                     # every inbox folder without a draft.md
python3 list.py ~/Listings/inbox/x  # specific folders
python3 list.py --redo              # rebuild drafts
python3 lookup.py 4580779532934     # quick eBay check, no photos / no Claude
python3 lookup.py "desktop cute hitagi"
```

One folder per item. If a folder has two different barcodes, it warns: split it.

## Layout

| File | What |
|---|---|
| `list.py` | the pipeline (steps 1–4) |
| `lookup.py` | barcode/text → eBay specifics + prices, printed |
| `lister/config.py` | `.env` loading, intro line, naming rule, platform markups |
| `lister/barcode.py` | barcode reading |
| `lister/ebay.py` | eBay auth, search, specifics voting, price stats |
| `lister/claude.py` | `claude -p` prompts (box reading, cleanup) |
| `lister/draft.py` | draft.md / draft.json rendering |
