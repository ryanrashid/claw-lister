# Architecture

**Principle:** deterministic code does everything that must be exact; Claude only does the fuzzy
reconciliation (11 inconsistent seller listings + 5 photos → one clean record). Code then enforces
invariants on Claude's output (title length, house specifics, one barcode field, required aspects).

```
photos ─▶ barcode.py ─┬─▶ ebay.gather(gtin) ─▶ claude.clean_up ─▶ draft.py ─▶ draft.md / listing.toml / draft.json
                      └─(none)─▶ claude.read_box ─▶ ebay.gather(q)   ┘
listing.toml (edited) ─▶ publish.py: validate ─▶ Media API photos ─▶ Trading API Verify ─▶ confirm ─▶ AddFixedPriceItem
```

## 1. Barcode — `lister/barcode.py`
- `zxing-cpp` (pip wheel, native decoder bundled). Pillow opens, applies EXIF rotation, grayscale.
- Up to three sizes per photo: downscale to 2400px if >3000px, original, and **2× LANCZOS upscale if
  <2500px** (~1000px photos only decode after upscaling). zxing tries rotations/binarizers itself.
- No `formats=` argument (its type changed between zxing-cpp versions); results are kept if all digits
  and length 8/12/13. 12-digit UPC-A gets a leading `0` (UPC-A is EAN-13 with a leading 0).
- One code per folder: most photos wins; mismatch prints a "split the folder" warning.

## 1b. No barcode — `claude.read_box`
- `subprocess.run(["claude", "-p", prompt, "--output-format", "json", "--allowedTools", "Read"], cwd=folder)`:
  Claude Code CLI headless on the Pro plan. `ANTHROPIC_API_KEY` is stripped from the child env
  (otherwise the CLI bills that key). The prompt lists ≤6 photo filenames; Claude views them with Read.
- Prompt covers boxes (figures) and paper hang tags / sewn-in tags (plushies). Returns
  `search_query`, `barcode_digits` (digits read off a box/tag), `box_text`, `confidence`.
- Parsing: CLI JSON envelope → `.result` text → first `{…}` via regex → `json.loads`.
- If Claude read digits, they're used as a barcode; otherwise `search_query` drives a keyword search.

## 2. eBay lookup — `lister/ebay.py`
- App token: OAuth client-credentials (`api_scope`), cached per process.
- **Browse** `item_summary/search`:
  - `gtin=<code>`, `filter=buyingOptions:{FIXED_PRICE|AUCTION}`, `limit=50`.
  - Headers `X-EBAY-C-MARKETPLACE-ID: EBAY_US`, `X-EBAY-C-ENDUSERCTX: contextualLocation=country=US,zip=…`
    (shipping estimates as if the buyer is in the US).
  - Keyword search on the number (`q=<code>`) only when <3 gtin hits: keyword hits are looser and
    pulled in the standard Miku when looking for the Black Ver.
  - No barcode: `q=<search_query>` only.
  - Lot/bundle titles dropped (regex).
- **Specifics vote:** `getItem` on the top 5 (gtin hits first, then US sellers). `Counter` per aspect
  name; junk values (NA, Does not apply…) dropped; top-level `brand`/`mpn` only counted when that listing
  has no such aspect (avoids double counting).
- **Prices:** total = price + first shipping option; grouped by New/Used × ships-from US/abroad
  (`itemLocation.country`); n, low, median, high, 3 cheapest.
- **Thin barcode results** (< 3 US matches): a second search by brand + model (from the matches'
  Brand/Model specifics, any language) adds "similar" listings. They feed model-level specs and the
  category only; identity and variant still come from exact matches.
- **Specifics are split by site:** ebay.com listings vs other eBay sites (`listingMarketplaceId`), the
  latter tagged `[EBAY_IT]` etc. so Claude translates them.
- **Category:** Figure/Plush fixed in `config.EBAY_CATEGORIES` (261055, 230). Anything else ("Other"):
  the most common `categoryId` among ebay.com listings (exact + similar), else Taxonomy
  `get_category_suggestions` for the title; its aspects are fetched like the fixed ones. **Taxonomy**
  `get_item_aspects_for_category` gives required/recommended aspects and allowed values for
  SELECTION_ONLY aspects; cached in `.cache/category_aspects.json` for 30 days.

## 3. Cleanup — `claude.clean_up`
- One `claude -p` call. Input: photos (Read), barcode, titles (barcode hits tagged `[barcode match]`),
  aspect votes with counts, both categories' aspect lists.
- Rules: photos are ground truth (`matches_photos=false` + `match_note` if eBay found a different item);
  name format with Franchise/Line/Variant definitions; title ≤ 80 − len(TITLE_SUFFIX); specifics only from
  photos or ≥2 listings; skip UPC/EAN/Condition/house fields; keep line symbols (FIGURIZMα).
- Output JSON: name parts, `category`, `ebay_title`, `item_specifics`, `intro_hook`, `box_facts`,
  `uncertain`, `matches_photos`.

## 4. Draft — `lister/draft.py` (deterministic)
- Prize items (Figure/Plush) get the house specifics, intro line and BBTS slot; "Other" items get
  Claude's neutral `intro_line`, keep Claude's country, and `category` = the numeric eBay id.
- Strip Claude's UPC/EAN/Condition (and house keys on prize items); add exactly one barcode field (`UPC` = 12 digits if the code
  starts with 0, else `EAN`); apply `HOUSE_SPECIFICS` only to aspects the category has (hence Country lands
  in "Country/Region of Manufacture"); required aspects still missing → `TODO`; append `TITLE_SUFFIX` if
  it fits in 80.
- Writes `draft.md` (research only: Check these, box facts, price research, category, Products row; no
  listing content, so there's one place to edit), `draft.json` (raw inputs/outputs), `listing.toml` (the
  listing itself, to edit; required aspects still missing appear as `TODO (required by eBay)`, which blocks publish: top-level keys
  before `[package]`/`[specifics]` per TOML; strings JSON-escaped, which TOML accepts; description as a
  `'''` literal block). An existing `listing.toml` is never overwritten; reruns write `listing.new.toml`.

## 5. Publish — `publish.py`, `lister/auth.py`, `lister/trading.py`
- **User OAuth** (authorization-code): consent URL with the **RuName** as `redirect_uri` (eBay's alias for
  the registered accept URL); scopes `api_scope`, `sell.inventory`, `sell.account.readonly`; user pastes the
  landing URL; code → access token (~2 h) + refresh token (~18 mo) in `.cache/ebay_user_token.json`
  (chmod 600); auto-refresh.
- **Validate:** `tomllib` parse; `problems()` blocks on price, package weight/size, BBTS placeholder,
  TODOs, title length, category.
- **Photos → Media API:** `POST apim.ebay.com/commerce/media/v1_beta/image/create_image_from_file`,
  multipart field `image`; Pillow → JPEG q92, ≤3000px; `imageUrl` from the body, or GET the `Location`;
  cached in `.photos.json` keyed by name+size+mtime. (Trading `UploadSiteHostedPictures` is decommissioned.)
- **Listing → Trading API (XML):** `POST api.ebay.com/ws/api.dll`, headers call name, compat 1349,
  site 0, `X-EBAY-API-IAF-TOKEN` (OAuth). `<Item>` built from templates with XML escaping; description
  → HTML in CDATA (blank line = `<p>`, `- ` = `<li>`). Category, `StartPrice`, `ConditionID` 1000,
  `PostalCode`, `GTC` fixed price ×1, picture URLs, `ItemSpecifics`, calculated `ShippingDetails`
  (`USPSParcel` = Ground Advantage, `GlobalShipping` = eBay International Shipping), `DispatchTimeMax`,
  `ReturnPolicy`, `ShippingPackageDetails`, `ScheduleTime` = now + `schedule_days` (UTC).
- **Flow:** `VerifyAddFixedPriceItem` (`Ack=Failure` → errors from `<Errors>`; fees: `ListingFee` is the
  total, `PromotionalDiscount` subtracted; estimates only, the free monthly allowance isn't applied) →
  confirm → identical XML to `AddFixedPriceItem` → `ItemID` → `published.json`. On shipping errors,
  `GeteBayDetails` lists currently valid service codes.
- Scheduled listings sit under Seller Hub > Scheduled; editable, and the schedule can be removed to go
  live. This is the de-facto draft (real drafts need the limited-release Sell Listing API).

## Learned by running it
1092px photos need upscaling · keyword search on the number mixes variants · Taxonomy category
suggestions are unreliable · `UploadSiteHostedPictures` 404s · `OriginatingPostalCode` is rejected ·
Ground Advantage = `USPSParcel` · the dry-run $0.35 insertion fee wasn't charged.

## Weak spots
- No automated tests; validated with mocks and manual runs.
- Claude's JSON isn't schema-validated (regex + `json.loads`).
- Trading XML is string templates rather than a builder.
- Each `claude -p` call takes ~30–60 s and uses Pro limits.
- Prices are active listings only (sold data = Marketplace Insights, restricted).
- No-barcode items (many plushies) rely on keyword search: looser matches, so read `matches_photos` and
  the "Check these" list more carefully.
