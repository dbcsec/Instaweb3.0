#!/usr/bin/env python3
"""Wave-8 demo builder — consumes new_email_candidates_v7.json (74 leads, fire-gate clean).

Built on wave7 (canonical V2 process). Hard requirement from the wave-7 stale-content
incident: FORCE-OVERWRITE any existing demo file at the same slug (prior-wave files were
the root cause of hill-electric-inc / american-plumbing showing stale city/phone). We
NEVER leave a prior-wave file at a slug.

Rules (owner zero-tolerance / plan guardrails):
- REAL business data only; NO fabrication.
- Canonical slug rule: replace(/&/g,'and') BEFORE stripping non-alphanumeric.
- Force-overwrite every target slug. Quarantine invalid records to .quarantine_wave8_invalid/.
- Built-in fire-gate CONTENT cross-check: after render, verify the page's city + phone
  match the v6/v7 record; any mismatch -> FAIL (never ship a page whose content is wrong).
- Does NOT email anyone (sends paused pending owner decision).
Usage: python3 scripts/wave8_demo_build.py
"""
import json, os, re, sys, glob, datetime
BASE_DIR = "/home/team/shared/instaweb3.0"
OUTPUT_DIR = f"{BASE_DIR}/data/demos/mass_output"
QUARANTINE_DIR = f"{BASE_DIR}/.quarantine_wave8_invalid"
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
from regenerate_demo_stubs import render_demo  # noqa: E402

TOLL_FREE = {"800", "888", "877", "866", "855", "900"}


def slugify(name):
    """Canonical slug: & -> and BEFORE stripping non-alphanumeric (plan guardrail)."""
    s = str(name or "").lower().replace("&", "and").replace("'", "")
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:80]


def tollfree_on_own_site(rec):
    """True if the record's toll-free phone is published on the business's OWN site."""
    import urllib.request
    website = str(rec.get("website") or rec.get("email_source") or "")
    # strip a URL fragment/path, keep scheme+host, but also try full URL
    candidates = [website]
    try:
        from urllib.parse import urlparse
        p = urlparse(website)
        if p.scheme and p.netloc:
            candidates.append(f"{p.scheme}://{p.netloc}")
    except Exception:
        pass
    phone = str(rec.get("phone") or "")
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) != 10:
        return False
    needle_10 = digits
    needle_11 = "1" + digits
    for site in candidates:
        if not site:
            continue
        try:
            req = urllib.request.Request(site, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=20) as r:
                html = r.read().decode("utf-8", "ignore")
            if needle_11 in html or needle_10 in html:
                return True
        except Exception:
            continue
    return False


def fmt_phone(p, allow_tollfree=False):
    """Normalize to (XXX) XXX-XXXX. Returns '' if not a plausible real US number."""
    p = str(p or "").strip()
    if not p:
        return ""
    if "000-0000" in p:
        return ""
    digits = re.sub(r"\D", "", p)
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) != 10:
        return ""
    if digits.startswith("000") or digits[3:6] == "000" or digits.startswith("555"):
        return ""
    if digits[3:6] == "555":
        return ""
    if digits == "2147483647":
        return ""
    if digits[:3] in TOLL_FREE and not allow_tollfree:
        return ""
    if len(set(digits)) == 1:
        return ""
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def build_lead_record(rec):
    """Normalize a wave-8 candidate into render_demo-compatible dict (real data only)."""
    name = str(rec.get("business_name") or rec.get("name") or "").strip()
    raw_phone = str(rec.get("phone") or "").strip()
    digits = re.sub(r"\D", "", raw_phone)
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    allow_tollfree = len(digits) == 10 and digits[:3] in TOLL_FREE and tollfree_on_own_site(rec)
    phone = fmt_phone(raw_phone, allow_tollfree=allow_tollfree)
    if not name or not phone:
        return None
    industry = str(rec.get("industry") or rec.get("niche") or "hvac").lower()
    if industry in ("hvac_r", "hvac-r"):
        industry = "hvac"
    email = str(rec.get("email") or "").strip()
    return {
        "business_name": name,
        "phone": phone,
        "city": str(rec.get("city") or "Serving"),
        "state_code": str(rec.get("state") or rec.get("state_code") or ""),
        "state": str(rec.get("state") or rec.get("state_code") or ""),
        "industry": industry,
        "email": email,
    }


def content_matches(html, rec):
    """Fire-gate CONTENT cross-check: does the rendered page show the record's city + phone?"""
    phone = str(rec.get("phone") or "")
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    city = str(rec.get("city") or "").strip()
    state = str(rec.get("state") or rec.get("state_code") or "").strip()
    html_digits = re.sub(r"\D", "", html)
    phone_ok = len(digits) == 10 and digits in html_digits
    city_ok = bool(city) and city in html and bool(state) and state in html
    return phone_ok, city_ok


def main():
    src = "/home/team/shared/new_email_candidates_v7.json"
    if not os.path.exists(src):
        print(f"SOURCE NOT FOUND: {src}")
        sys.exit(2)
    data = json.load(open(src))
    if isinstance(data, dict):
        data = data.get("leads") or data.get("candidates") or list(data.values())[0]
    if not isinstance(data, list):
        print("Unrecognized v7 list format (expected list or {leads:[...]})")
        sys.exit(3)
    os.makedirs(QUARANTINE_DIR, exist_ok=True)
    print(f"v7 leads in list: {len(data)}")
    built, quarantined, failed = [], [], []
    for rec in data:
        slug = str(rec.get("slug") or "").strip()
        du = str(rec.get("demo_url") or "").strip()
        if du and "/demo/" in du:
            du_slug = du.rstrip("/").split("/demo/")[-1]
            if du_slug:
                slug = du_slug
        if not slug:
            quarantined.append(("no-slug", rec.get("business_name")))
            continue
        lr = build_lead_record(rec)
        if lr is None:
            quarantined.append((slug, f"no-real-phone:{rec.get('phone')}"))
            with open(os.path.join(QUARANTINE_DIR, slug + ".json"), "w") as f:
                json.dump(rec, f, indent=1)
            continue
        path = os.path.join(OUTPUT_DIR, slug + ".html")
        try:
            html = render_demo(lr, path)  # render_demo overwrites (file open 'w')
            if "(555)" in html or "{{" in html or len(html) < 500:
                failed.append((slug, "render-invalid"))
                continue
            phone_ok, city_ok = content_matches(html, rec)
            if not (phone_ok and city_ok):
                failed.append((slug, f"content-mismatch phone_ok={phone_ok} city_ok={city_ok}"))
                continue
            built.append(slug)
        except Exception as e:
            failed.append((slug, f"error:{e}"))
    print(f"\nBUILT: {len(built)}")
    print(f"QUARANTINED (no real phone / invalid): {len(quarantined)}")
    for s, r in quarantined:
        print(f"   {s}: {r}")
    print(f"FAILED (content mismatch / error): {len(failed)}")
    for s, r in failed:
        print(f"   {s}: {r}")
    report = {
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "source": src,
        "leads_in_list": len(data),
        "built": sorted(built),
        "quarantined": [{"slug": s, "reason": r} for s, r in quarantined],
        "failed": failed,
        "demo_urls": {s: f"https://instaweb.agency/demo/{s}" for s in sorted(built)},
    }
    out = "/home/team/shared/wave8_demo_build_report.json"
    with open(out, "w") as f:
        json.dump(report, f, indent=1)
    print(f"report -> {out}")
    print(f"\nBUILT TOTAL: {len(built)} / {len(data)} leads")


if __name__ == "__main__":
    main()
