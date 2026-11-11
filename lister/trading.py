"""eBay Trading API (XML): photo upload, dry-run, and listing creation.

Chosen over the Inventory API because listings it creates stay editable in Seller Hub,
and photos upload from the file itself via the Media API (no public URL needed).
"""
import io, json, sys, uuid, urllib.error, urllib.request
import xml.etree.ElementTree as ET
from html import escape
from xml.sax.saxutils import escape as xesc

from .auth import user_token

URL = "https://api.ebay.com/ws/api.dll"
COMPAT = "1349"
NS = "{urn:ebay:apis:eBLBaseComponents}"


class EbayError(Exception):
    pass


def _headers(call):
    return {"X-EBAY-API-COMPATIBILITY-LEVEL": COMPAT, "X-EBAY-API-CALL-NAME": call,
            "X-EBAY-API-SITEID": "0", "X-EBAY-API-IAF-TOKEN": user_token()}


def _parse(raw):
    root = ET.fromstring(raw)
    errors = []
    for e in root.iter(NS + "Errors"):
        errors.append({"severity": e.findtext(NS + "SeverityCode", ""),
                       "code": e.findtext(NS + "ErrorCode", ""),
                       "message": e.findtext(NS + "LongMessage") or e.findtext(NS + "ShortMessage", "")})
    return root, root.findtext(NS + "Ack", ""), errors


def call(name, inner_xml):
    body = (f'<?xml version="1.0" encoding="utf-8"?><{name}Request xmlns="urn:ebay:apis:eBLBaseComponents">'
            f"<ErrorLanguage>en_US</ErrorLanguage><WarningLevel>High</WarningLevel>{inner_xml}</{name}Request>")
    req = urllib.request.Request(URL, data=body.encode("utf-8"),
                                 headers={**_headers(name), "Content-Type": "text/xml"})
    try:
        raw = urllib.request.urlopen(req).read()
    except urllib.error.HTTPError as e:
        raise EbayError(f"{name}: HTTP {e.code} {e.read().decode()[:300]}")
    root, ack, errors = _parse(raw)
    if ack == "Failure":
        raise EbayError(f"{name} failed:\n" + "\n".join(f"  [{x['code']}] {x['message']}" for x in errors))
    return root, [x for x in errors if x["severity"] == "Warning"]


MEDIA = "https://apim.ebay.com/commerce/media/v1_beta"


def upload_photo(path):
    """Upload one image file to eBay Picture Services; returns the eBay-hosted URL.

    Uses the Media API: eBay decommissioned the Trading API's UploadSiteHostedPictures
    (it now 404s). Converted to JPEG first since webp/heic support isn't documented."""
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        if max(im.size) > 3000:
            im.thumbnail((3000, 3000))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92)
    boundary = "----claw" + uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{path.stem}.jpg\"\r\n"
            "Content-Type: image/jpeg\r\n\r\n").encode() + buf.getvalue() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{MEDIA}/image/create_image_from_file", data=body, method="POST", headers={
        "Authorization": f"Bearer {user_token()}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        raise EbayError(f"photo upload {path.name}: HTTP {e.code} {e.read().decode()[:300]}")
    raw = resp.read()
    data = json.loads(raw) if raw.strip() else {}
    if not data.get("imageUrl") and resp.headers.get("Location"):   # body empty: fetch by id
        loc = resp.headers["Location"]
        loc = loc if loc.startswith("http") else MEDIA + "/image/" + loc.rstrip("/").split("/")[-1]
        r2 = urllib.request.Request(loc, headers={"Authorization": f"Bearer {user_token()}"})
        data = json.load(urllib.request.urlopen(r2))
    if not data.get("imageUrl"):
        raise EbayError(f"photo upload {path.name}: no imageUrl in response {data}")
    return data["imageUrl"]


def description_html(text):
    """Plain text -> simple HTML: blank-line paragraphs, '- ' lines as bullets."""
    html, bullets, para = [], [], []

    def flush():
        if para:
            html.append("<p>" + "<br>".join(escape(x) for x in para) + "</p>")
            para.clear()
        if bullets:
            html.append("<ul>" + "".join(f"<li>{escape(b)}</li>" for b in bullets) + "</ul>")
            bullets.clear()

    for line in text.strip().splitlines():
        s = line.strip()
        if not s:
            flush()
        elif s.startswith("- "):
            if para:
                flush()
            bullets.append(s[2:])
        else:
            if bullets:
                flush()
            para.append(s)
    flush()
    return "".join(html)


def item_xml(L, photo_urls, cfg):
    """L = parsed listing.toml; cfg = dict with category_id, postal_code, policies, condition_id, schedule."""
    pk = L["package"]
    specifics = "".join(
        f"<NameValueList><Name>{xesc(k)}</Name><Value>{xesc(str(v))}</Value></NameValueList>"
        for k, v in L.get("specifics", {}).items() if str(v).strip())
    pics = "".join(f"<PictureURL>{xesc(u)}</PictureURL>" for u in photo_urls)
    sched = f"<ScheduleTime>{cfg['schedule']}</ScheduleTime>" if cfg.get("schedule") else ""
    return (
        "<Item>"
        f"<Title>{xesc(L['title'])}</Title>"
        f"<Description><![CDATA[{description_html(L['description'])}]]></Description>"
        f"<PrimaryCategory><CategoryID>{cfg['category_id']}</CategoryID></PrimaryCategory>"
        f"<StartPrice currencyID=\"USD\">{float(L['price']):.2f}</StartPrice>"
        f"<ConditionID>{cfg['condition_id']}</ConditionID>"
        "<Country>US</Country><Currency>USD</Currency>"
        f"<PostalCode>{xesc(cfg['postal_code'])}</PostalCode>"
        "<ListingDuration>GTC</ListingDuration><ListingType>FixedPriceItem</ListingType>"
        "<Quantity>1</Quantity>"
        f"<PictureDetails>{pics}</PictureDetails>"
        f"<ItemSpecifics>{specifics}</ItemSpecifics>"
        f"{_policies_xml(cfg)}"
        "<ShippingPackageDetails><MeasurementUnit>English</MeasurementUnit>"
        f"<WeightMajor unit=\"lbs\">{int(pk['weight_lb'])}</WeightMajor>"
        f"<WeightMinor unit=\"oz\">{int(pk['weight_oz'])}</WeightMinor>"
        f"<PackageLength unit=\"inches\">{pk['length_in']}</PackageLength>"
        f"<PackageWidth unit=\"inches\">{pk['width_in']}</PackageWidth>"
        f"<PackageDepth unit=\"inches\">{pk['height_in']}</PackageDepth>"
        "</ShippingPackageDetails>"
        f"{sched}"
        "</Item>")


def _policies_xml(cfg):
    """Business-policy ids if configured, otherwise shipping/returns written into the listing."""
    pol = cfg["policies"]
    if all(pol.values()):
        return ("<SellerProfiles>"
                f"<SellerShippingProfile><ShippingProfileID>{pol['shipping']}</ShippingProfileID></SellerShippingProfile>"
                f"<SellerPaymentProfile><PaymentProfileID>{pol['payment']}</PaymentProfileID></SellerPaymentProfile>"
                f"<SellerReturnProfile><ReturnProfileID>{pol['returns']}</ReturnProfileID></SellerReturnProfile>"
                "</SellerProfiles>")
    sh, rt = cfg["shipping"], cfg["returns"]
    # Calculated rates use Item.PostalCode + ShippingPackageDetails; eBay no longer accepts
    # CalculatedShippingRate.OriginatingPostalCode (error 219451).
    ship = ("<ShippingDetails><ShippingType>Calculated</ShippingType>"
            "<ShippingServiceOptions><ShippingServicePriority>1</ShippingServicePriority>"
            f"<ShippingService>{sh['service']}</ShippingService></ShippingServiceOptions>"
            + ("<GlobalShipping>true</GlobalShipping>" if sh.get("intl_ebay_international_shipping") else "")
            + "</ShippingDetails>"
            f"<DispatchTimeMax>{int(sh['handling_days'])}</DispatchTimeMax>")
    ret = "<ReturnPolicy>"
    ret += ("<ReturnsAcceptedOption>ReturnsAccepted</ReturnsAcceptedOption><ReturnsWithinOption>Days_30</ReturnsWithinOption>"
            "<ShippingCostPaidByOption>Buyer</ShippingCostPaidByOption>" if rt.get("domestic")
            else "<ReturnsAcceptedOption>ReturnsNotAccepted</ReturnsAcceptedOption>")
    if rt.get("intl_via_ebay_international_shipping"):
        ret += ("<InternationalReturnsAcceptedOption>ReturnsAccepted</InternationalReturnsAcceptedOption>"
                f"<InternationalReturnsWithinOption>Days_{int(rt['intl_days'])}</InternationalReturnsWithinOption>"
                "<InternationalShippingCostPaidByOption>Buyer</InternationalShippingCostPaidByOption>")
    ret += "</ReturnPolicy>"
    return ship + ret


def shipping_services(word="USPS"):
    """Domestic shipping service codes eBay accepts right now (GeteBayDetails)."""
    root, _ = call("GeteBayDetails", "<DetailName>ShippingServiceDetails</DetailName>")
    out = []
    for d in root.iter(NS + "ShippingServiceDetails"):
        code = d.findtext(NS + "ShippingService", "")
        if (word.lower() in code.lower() and d.findtext(NS + "ValidForSellingFlow") == "true"
                and d.findtext(NS + "InternationalService") != "true"):
            out.append((code, d.findtext(NS + "Description", ""),
                        "/".join(t.text for t in d.findall(NS + "ShippingCarrier") if t.text)))
    return out


def fees(root):
    """(name, amount after any promotional discount). These are eBay's *estimates*: per the
    FeeType docs, Verify calls may omit discounts, and the free monthly listing allowance
    isn't reliably reflected, so a $0.35 insertion fee here may not actually be charged."""
    out = []
    for f in root.iter(NS + "Fee"):
        amt = float(f.findtext(NS + "Fee", "0") or 0)
        amt -= float(f.findtext(NS + "PromotionalDiscount", "0") or 0)
        if amt > 0:
            out.append((f.findtext(NS + "Name"), round(amt, 2)))
    return out
