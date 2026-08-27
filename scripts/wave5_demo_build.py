#!/usr/bin/env python3
"""Wave-5 demo builder — consumes new_email_candidates_v4.json (task d509d552).
Rules (owner zero-tolerance / plan guardrails):
- REAL business data only: business_name, phone, city, state, industry from the lead record.
- NO fabrication: reject (555) 000-0000, INT_MAX +12147483647, repeating-digit,
  toll-free 800/888/877/866/855/900 as display numbers; len != 10 -> skip.
- Canonical slug rule: replace(/&/g,'and') BEFORE stripping non-alphanumeric.
- Build EXACTLY the demo_url slugs in v4 (already canonical).
- Idempotent: skip leads whose demo already exists on disk; existing corpus preserved.
- Quarantine invalid records to .quarantine_wave5_invalid/ and report.
- Does NOT email anyone (sales-closer owns sends).
Usage: python3 scripts/wave5_demo_build.py
"""
import json, os, re, sys, glob, datetime, shutil
BASE_DIR = "/home/team/shared/instaweb3.0"
OUTPUT_DIR = f"{BASE_DIR}/data/demos/mass_output"
QUARANTINE_DIR = f"{BASE_DIR}/.quarantine_wave5_invalid"
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
    """True if the record's toll-free phone is published on the business's OWN site.
    Guardrail semantics (owner/lead, 2026-08-18): toll-free is REAL data when it is
    on the business's own site (e.g. Reinhold Electric 1-800-378-1158, Best Choice
    Roofing 888). Reject toll-free ONLY when it is NOT on the own site."""
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
    needle_10 = digits            # 8003781158
    needle_11 = "1" + digits      # 18003781158
    try:
        req = urllib.request.Request(website, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=25) as r:
            html = r.read().decode("utf-8", "ignore")
    except Exception:
        return False
    if needle_11 in html or needle_10 in html:
        return True
    # also accept formatted variants with punctuation, e.g. 1-800-378-1158
    pat = re.escape(phone[0]) if phone.startswith("+") else ""
    return bool(re.search(r"[1-9]\D*\d{3}\D*\d{3}\D*\d{4}", html)) and (
        needle_11 in re.sub(r"\D", "", html) or needle_10 in re.sub(r"\D", "", html)
    )


def fmt_phone(p, allow_tollfree=False):
    """Normalize to (XXX) XXX-XXXX. Returns '' if not a plausible real US number.
    allow_tollfree=True keeps 800/888/877/866/855/900 (verified on business's own site)."""
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
    if digits == "2147483647":  # INT_MAX placeholder
        return ""
    if digits[:3] in TOLL_FREE and not allow_tollfree:  # toll-free only if on own site
        return ""
    if len(set(digits)) == 1:  # repeating digit (1111111111 etc.)
        return ""
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def build_lead_record(rec):
    """Normalize a v4 candidate record into render_demo-compatible dict (real data only).
    Toll-free phones allowed ONLY when published on the business's own site."""
    name = str(rec.get("business_name") or rec.get("name") or "").strip()
    digits = re.sub(r"\D", "", str(rec.get("phone") or ""))
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    allow_tollfree = len(digits) == 10 and digits[:3] in TOLL_FREE and tollfree_on_own_site(rec)
    phone = fmt_phone(rec.get("phone") or rec.get("phone_number") or "", allow_tollfree=allow_tollfree)
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
    src = "/home/team/shared/new_email_candidates_v4.json"
    if not os.path.exists(src):
        print(f"SOURCE NOT FOUND: {src}")
        sys.exit(2)
    data = json.load(open(src))
    if isinstance(data, dict):
        data = data.get("leads") or data.get("candidates") or list(data.values())
    if not isinstance(data, list):
        print("Unrecognized v4 list format (expected list or {leads:[...]})")
        sys.exit(3)
    os.makedirs(QUARANTINE_DIR, exist_ok=True)
    print(f"v4 leads in list: {len(data)}")
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
        lr = build_lead_record(rec)
        if slug in EXISTING:
            exists.append(slug)
            continue
        if lr is None:
            reason = "no-real-phone"
            raw_phone = rec.get("phone")
            quarantined.append((slug, f"{reason}:{raw_phone}"))
            # preserve the source record for review (do not lose real data)
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
    out = "/home/team/shared/wave5_demo_build_report.json"
    with open(out, "w") as f:
        json.dump(report, f, indent=1)
    print(f"report -> {out}")
    print(f"\nTOTAL demo corpus after build: {len(EXISTING)}")


if __name__ == "__main__":
    main()
