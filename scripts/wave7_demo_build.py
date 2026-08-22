#!/usr/bin/env python3
"""Wave-7 demo builder — consumes new_email_candidates_v6.json (the wave-7 list).
Built on wave6 (proven V2 template process). Builds the MISSING demo pages so the
A/B batch demo_urls stop 404ing. Rules (owner zero-tolerance / plan guardrails):
- REAL business data only; NO fabrication.
- Canonical slug rule: replace(/&/g,'and') BEFORE stripping non-alphanumeric.
- Build EXACTLY the demo_url slugs in v6 (already canonical).
- Idempotent: skip leads whose demo already exists on disk; existing corpus preserved.
- Phone sanitization identical to wave6: reject 555-EXCHANGE, xxx-0000, INT_MAX,
  repeating-digit, all-zero; toll-free allowed ONLY if on business's own site.
- Quarantine invalid records to .quarantine_wave7_invalid/ and report.
- Does NOT email anyone (sales-closer / A/B send owns sends).
Usage: python3 scripts/wave7_demo_build.py
"""
import json, os, re, sys, glob, datetime, shutil
BASE_DIR = "/home/team/shared/instaweb3.0"
OUTPUT_DIR = f"{BASE_DIR}/data/demos/mass_output"
QUARANTINE_DIR = f"{BASE_DIR}/.quarantine_wave7_invalid"
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
from regenerate_demo_stubs import render_demo  # noqa: E402

EXISTING = set(os.path.basename(f)[:-5] for f in glob.glob(f"{OUTPUT_DIR}/*.html"))
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
    phone = str(rec.get("phone") or "")
    if not website or not phone:
        return False
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) != 10:
        return False
    needle_10 = digits
    needle_11 = "1" + digits
    try:
        req = urllib.request.Request(website, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=25) as r:
            html = r.read().decode("utf-8", "ignore")
    except Exception:
        return False
    if needle_11 in html or needle_10 in html:
        return True
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
    """Normalize a wave-7 candidate into render_demo-compatible dict (real data only)."""
    name = str(rec.get("business_name") or rec.get("name") or "").strip()
    raw_phone = str(rec.get("phone") or "").strip()
    digits = re.sub(r"\D", "", raw_phone)
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    allow_tollfree = len(digits) == 10 and digits[:3] in TOLL_FREE and tollfree_on_own_site(rec)
    phone = fmt_phone(raw_phone, allow_tollfree=allow_tollfree)
    if not name or not phone:
        return None  # no real phone -> skip (no fabrication)
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


def main():
    src = "/home/team/shared/new_email_candidates_v6.json"
    if not os.path.exists(src):
        print(f"SOURCE NOT FOUND: {src}")
        sys.exit(2)
    data = json.load(open(src))
    if isinstance(data, dict):
        data = data.get("leads") or data.get("candidates") or list(data.values())
    if not isinstance(data, list):
        print("Unrecognized v6 list format (expected list or {leads:[...]})")
        sys.exit(3)
    os.makedirs(QUARANTINE_DIR, exist_ok=True)
    print(f"v6 leads in list: {len(data)}")
    built, exists, quarantined, failed = [], [], [], []
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
        if slug in EXISTING:
            exists.append(slug)
            continue
        lr = build_lead_record(rec)
        if lr is None:
            reason = "no-real-phone"
            quarantined.append((slug, f"{reason}:{rec.get('phone')}"))
            with open(os.path.join(QUARANTINE_DIR, slug + ".json"), "w") as f:
                json.dump(rec, f, indent=1)
            continue
        path = os.path.join(OUTPUT_DIR, slug + ".html")
        try:
            html = render_demo(lr, path)
            if "(555)" in html or "{{" in html or len(html) < 500:
                failed.append((slug, "render-invalid"))
                os.remove(path) if os.path.exists(path) else None
                continue
            built.append(slug)
            EXISTING.add(slug)
        except Exception as e:
            failed.append((slug, f"error:{e}"))
    print(f"\nBUILT: {len(built)}")
    print(f"SKIPPED (already on disk): {len(exists)}")
    print(f"QUARANTINED (no real phone / invalid): {len(quarantined)}")
    for s, r in quarantined:
        print(f"   {s}: {r}")
    print(f"FAILED: {len(failed)}")
    for s, r in failed[:10]:
        print(f"   {s}: {r}")
    report = {
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "source": src,
        "leads_in_list": len(data),
        "built": sorted(built),
        "already_exists": sorted(exists),
        "quarantined": [{"slug": s, "reason": r} for s, r in quarantined],
        "failed": failed,
        "demo_urls": {s: f"https://instaweb.agency/demo/{s}" for s in sorted(built)},
        "corpus_total_after": len(EXISTING),
    }
    out = "/home/team/shared/wave7_demo_build_report.json"
    with open(out, "w") as f:
        json.dump(report, f, indent=1)
    print(f"report -> {out}")
    print(f"\nTOTAL demo corpus after build: {len(EXISTING)}")


if __name__ == "__main__":
    main()
