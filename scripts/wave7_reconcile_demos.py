#!/usr/bin/env python3
"""Wave-7 reconcile: force-overwrite 6 v6 demos whose content is stale/mismatched.

The wave-7 fire-gate audit found 6/111 demo files that return 200 but show stale/wrong
city or phone (root cause: a prior-wave file sitting at the same slug was never
overwritten). Owner zero-tolerance — rebuild these so the live page matches the v6
record exactly.

Records (from new_email_candidates_v6.json, the canonical clean 111, verified by lead):
  hill-electric-inc  -> (479) 267-2403  Fayetteville AR
  american-plumbing  -> (225) 644-7748  Baton Rouge LA
  abacus-plumbing-air-conditioning-and-electrical -> (281) 215-3046 Houston TX
  314-roofing-solutions -> (832) 688-8363 Houston TX
  metro-flow-plumbing-dallas-emergency-plumbers -> (214) 214-4718 Dallas TX
  kb-complete-plumbing-heating-cooling-and-electrical-inc -> (816) 327-1709 Kansas City MO

Forces overwrite of any existing slug file (the documented root cause). Reuses the
canonical build_lead_record/phone gates from wave7_demo_build. Does NOT email anyone.
Usage: python3 scripts/wave7_reconcile_demos.py
"""
import json, os, re, sys, glob, datetime
BASE_DIR = "/home/team/shared/instaweb3.0"
OUTPUT_DIR = f"{BASE_DIR}/data/demos/mass_output"
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
from regenerate_demo_stubs import render_demo  # noqa: E402

TOLL_FREE = {"800", "888", "877", "866", "855", "900"}

# The 6 slugs from the fire-gate audit (v6 record matched by slug)
TARGET_SLUGS = {
    "hill-electric-inc",
    "american-plumbing",
    "abacus-plumbing-air-conditioning-and-electrical",
    "314-roofing-solutions",
    "metro-flow-plumbing-dallas-emergency-plumbers",
    "kb-complete-plumbing-heating-cooling-and-electrical-inc",
}


def fmt_phone(p):
    p = str(p or "").strip()
    if not p:
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
    if len(set(digits)) == 1:
        return ""
    if digits[:3] in TOLL_FREE:
        return ""  # toll-free requires on-own-site check; not needed for these 6
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def build_record(rec):
    name = str(rec.get("business_name") or rec.get("name") or "").strip()
    raw = str(rec.get("phone") or "").strip()
    phone = fmt_phone(raw)
    if not name or not phone:
        return None
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
        "email": str(rec.get("email") or "").strip(),
    }


def main():
    src = "/home/team/shared/new_email_candidates_v6.json"
    data = json.load(open(src))
    if not isinstance(data, list):
        data = data.get("leads") or data.get("candidates") or list(data.values())[0]

    # index by canonical slug (from demo_url / records, same rule as builder)
    by_slug = {}
    for rec in data:
        slug = str(rec.get("slug") or "").strip()
        du = str(rec.get("demo_url") or "").strip()
        if du and "/demo/" in du:
            slug = du.rstrip("/").split("/demo/")[-1]
        if not slug:
            continue
        by_slug[slug] = rec

    rebuilt, failed, missing = [], [], []
    for slug in sorted(TARGET_SLUGS):
        rec = by_slug.get(slug)
        if rec is None:
            missing.append(slug)
            continue
        lr = build_record(rec)
        if lr is None:
            failed.append((slug, "no-real-phone"))
            continue
        path = os.path.join(OUTPUT_DIR, slug + ".html")
        try:
            html = render_demo(lr, path)  # FORCE overwrite
            if "(555)" in html or "{{" in html or len(html) < 500:
                failed.append((slug, "render-invalid"))
                continue
            # content match check against the v6 record
            phone_needle = re.sub(r"\D", "", (rec.get("phone") or ""))
            if len(phone_needle) == 11 and phone_needle[0] == "1":
                phone_needle = phone_needle[1:]
            phone_display = lr["phone"]  # e.g. (479) 267-2403
            city = str(rec.get("city") or "").strip()
            state = str(rec.get("state") or rec.get("state_code") or "").strip()
            html_clean = re.sub(r"\D", "", html)
            ok_phone = (phone_display in html) and (phone_needle in html_clean)
            ok_city = (city in html) and (state in html)
            if not (ok_phone and ok_city):
                failed.append((slug, f"content-verify city={city}{state} phone={phone_display}"))
                continue
            rebuilt.append(slug)
        except Exception as e:
            failed.append((slug, f"error:{e}"))

    print("TARGETS:", len(TARGET_SLUGS))
    print("REBUILT:", len(rebuilt))
    for s in sorted(rebuilt):
        print("   ", s)
    print("FAILED:", len(failed), failed)
    print("MISSING IN v6:", missing)
    report = {
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "source": src,
        "targets": sorted(TARGET_SLUGS),
        "rebuilt": sorted(rebuilt),
        "failed": failed,
        "missing_in_v6": missing,
    }
    with open("/home/team/shared/wave7_reconcile_report.json", "w") as f:
        json.dump(report, f, indent=1)
    print("report -> /home/team/shared/wave7_reconcile_report.json")


if __name__ == "__main__":
    main()
