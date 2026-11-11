#!/usr/bin/env python3
"""auth.py — sign in to eBay once so the scripts can list for you, then show your business policies.

    python3 auth.py            # sign in (opens eBay in your browser), then list policies
    python3 auth.py policies   # just list policies (already signed in)
"""
import sys, webbrowser

from lister import auth
from lister.config import load_env


def show_policies():
    for kind, path, key in (("Shipping", "fulfillment_policy", "fulfillmentPolicies"),
                            ("Payment", "payment_policy", "paymentPolicies"),
                            ("Returns", "return_policy", "returnPolicies")):
        res = auth.user_get(f"/sell/account/v1/{path}", marketplace_id="EBAY_US")
        items = res.get(key, [])
        print(f"\n{kind} policies ({len(items)}):")
        for p in items:
            pid = p.get("fulfillmentPolicyId") or p.get("paymentPolicyId") or p.get("returnPolicyId")
            print(f"  {pid}  {p.get('name')}")
    print("\nTell Claude which ones to use by default (or paste this output).")


def main():
    load_env()
    if sys.argv[1:] != ["policies"]:
        url = auth.consent_url()
        print("Opening eBay sign-in. Approve the app; eBay then sends you to a page whose address")
        print("contains '?code=...'. Copy that whole address and paste it here.\n")
        print(url, "\n")
        webbrowser.open(url)
        auth.exchange(input("Paste the address: "))
        print("Signed in. Token saved to .cache/ebay_user_token.json (not committed).")
    show_policies()


if __name__ == "__main__":
    main()
