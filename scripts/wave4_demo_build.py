#!/usr/bin/env python3
"""Wave-4 demo builder — consumes new_email_candidates_v3.json (lead task f91eee59).

Rules (owner zero-tolerance / plan guardrails):
- REAL business data only: business_name, phone, city, state, industry from the lead record.
- NO fabrication: a lead WITHOUT a real 10-digit phone is SKIPPED (never write the
  (555) 000-0000 placeholder — that caused the 8/16 corpus fix).
- Canonical slug rule: replace(/&/g,'and') BEFORE stripping non-alphanumeric.
- Skips leads whose demo already exists on disk (idempotent re-runs).
- Does NOT email anyone (sales-closer owns sends).
- Does NOT modify lead data.

Usage: python3 scripts/wave4_demo_build.py /home/team/shared/new_email_candidates_v3.json
"""
import json, os, re, sys, glob, datetime

BASE_DIR = "/home/team/shared/instaweb3.0"
OUTPUT_DIR = f"{BASE_DIR}/data/demos/mass_output"

sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
from regenerate_demo_stubs import render_demo, OUTPUT_DIR  # noqa: E402

EXISTING = set(os.path.basename(f)[:-5] for f in glob.glob(f"{OUTPUT_DIR}/*.html"))


def slugify(name):
    """Canonical slug: & -> and BEFORE stripping non-alphanumeric (plan guardrail)."""
    s = str(name or "").lower().replace("&", "and").replace("'", "")
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:80]


def fmt_phone(p):
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
    if digits == "2147483647":  # INT_MAX placeholder — scraper fake-phone fallback
        return ""
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def build_lead_record(rec):
    """Normalize a v3 candidate record into render_demo-compatible dict (real data only)."""
    name = str(rec.get("business_name") or rec.get("name") or "").strip()
    phone = fmt_phone(rec.get("phone") or rec.get("phone_number") or "")
    if not name or not phone:
        return None  # no real phone -> skip (no fabrication)
    industry = str(rec.get("industry") or rec.get("niche") or "hvac").lower()
    if industry in ("hvac_r", "hvac-r"):
        industry = "hvac"
    return {
        "business_name": name,
        "phone": phone,
        "city": str(rec.get("city") or "Serving"),
        "state_code": str(rec.get("state") or rec.get("state_code") or ""),
        "state": str(rec.get("state") or rec.get("state_code") or ""),
        "industry": industry,
        "email": str(rec.get("email") or ""),
    }


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "/home/team/shared/new_email_candidates_v3.json"
    if not os.path.exists(src):
        print(f"SOURCE NOT FOUND: {src}")
        sys.exit(2)
    data = json.load(open(src))
    if isinstance(data, dict):
        # accept {"leads": [...]} or {key: record}
        data = data.get("leads") or data.get("candidates") or list(data.values())
    if not isinstance(data, list):
        print("Unrecognized v3 list format (expected list or {leads:[...]})")
        sys.exit(3)
    print(f"v3 leads in list: {len(data)}")

    built, skipped_no_phone, exists, failed = [], [], [], []
    for rec in data:
        lr = build_lead_record(rec)
        slug = slugify((rec.get("business_name") or rec.get("name") or ""))
        if not slug:
            skipped_no_phone.append(("no-name", rec.get("business_name") or rec.get("name")))
            continue
        # Record already carries a demo_url -> honor it (may be address-slug based,
        # e.g. v2-style "plumber-800-e-73rd-ave-unit-2" rather than name-slug).
        du = rec.get("demo_url") or rec.get("demo") or ""
        if isinstance(du, str) and "/demo/" in du:
            du_slug = du.rstrip("/").split("/demo/")[-1]
            if du_slug in EXISTING:
                exists.append(du_slug)
                continue
        if slug in EXISTING:
            exists.append(slug)
            continue
        if lr is None:
            skipped_no_phone.append((slug, "no-real-phone"))
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
    print(f"SKIPPED (no real phone / no fabrication): {len(skipped_no_phone)}")
    print(f"FAILED: {len(failed)}")
    for s, r in failed[:10]:
        print(f"   {s}: {r}")

    report = {
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "source": src,
        "built": sorted(built),
        "already_exists": sorted(exists),
        "skipped_no_phone": sorted({f"{s}" for s, _ in skipped_no_phone}),
        "failed": failed,
        "demo_urls": {s: f"https://instaweb.agency/demo/{s}" for s in sorted(built)},
    }
    out = "/home/team/shared/wave4_demo_build_report.json"
    with open(out, "w") as f:
        json.dump(report, f, indent=1)
    print(f"report -> {out}")
    print(f"\nTOTAL demo corpus after build: {len(EXISTING)}")


if __name__ == "__main__":
    main()
