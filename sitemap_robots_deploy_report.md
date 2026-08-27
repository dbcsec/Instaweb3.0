# sitemap.xml + robots.txt — Deploy Report (2026-08-16)

Task: b99c29bd-3be6-492b-ab8a-2aa637bdb448 (scope changed → deploy OWNER's files as-is)

## What was done
- Fetched the owner's files verbatim from https://temp.instaweb.agency/:
  - `sitemap.xml` (10,032 bytes) → `/home/team/shared/instaweb3.0/sitemap.xml`
  - `robots.txt` (166 bytes) → `/home/team/shared/instaweb3.0/robots.txt`
- **No content modified** — deployed exactly as served (owner decision).
- Deploy-race rule honored: confirmed full file set on disk before deploy
  (mass_output = **2,527 demos**, caller.html Top-10 tab present, VERCEL_TOKEN env verified).
- Single deploy via `bunx vercel deploy --prod` from `/home/team/shared/instaweb3.0`:
  - Production URL: `https://instaweb3-0-85xuoasl4-rjm-llc-projects.vercel.app`
  - **✓ Ready in 37s**, aliased to `https://instaweb.agency`

## Live verification (post-deploy)
### /sitemap.xml → **HTTP 200**
- Size: 10,032 bytes — **byte-identical to owner's file** (`diff` clean)
- XML parses OK (Python ElementTree): 58 `<url>` children
- **58 `<loc>` URLs** (under 50k limit, no index needed)
- First few: `https://instaweb.agency` (home), `/pricing`, `/industries`, `/locations`, `/contact`, `/industries/hvac`, ...
- Last few: `/locations/phoenix/electrical`, `/restaurants`, `/salons`, `/cleaning`, `/landscaping`
- Note: sitemap contains **0 demo URLs** — pure page sitemap (owner's file)

### /robots.txt → **HTTP 200**
- Owner's 8 lines present verbatim at the end of the served file:
  ```
  User-Agent: *
  Allow: /
  Disallow: /admin/
  Disallow: /dashboard/
  Disallow: /api/
  Disallow: /checkout/
  Disallow: /preview/
  Sitemap: https://instaweb.agency/sitemap.xml
  ```
- **CDN note:** live response (70 lines total) has a 61-line **Cloudflare-managed prefix** prepended
  (AI-bot disallows + Content-Signal block). This is injected by Cloudflare at the edge on
  instaweb.agency, NOT part of the deployed file — `diff` shows additions only (0a1,61),
  nothing from the owner's file was changed or dropped. Crawlers are still allowed generally;
  AI bots get blocked by Cloudflare, owner's disallow paths preserved.

### Demo corpus (deploy must not break it) — **3/3 spot-checks HTTP 200**
| slug | HTTP | size | title |
|------|------|------|-------|
| demo/plumber-3230-east-charleston-boulevard | 200 | 22,804B | Plumber 3230 East Charleston Boulevard — Trusted Plumbing Service |
| demo/all-the-time-plumbing | 200 | 22,672B | All The Time Plumbing — Trusted Plumbing Service |
| demo/sponsored | 200 | 22,574B | Sponsored — Trusted Roofing Service |

## Known caveat (owner's decision — reported, NOT fixed)
57 of the 58 sitemap URLs point at pages that **currently 404 on instaweb.agency**
(verified live: `/pricing` → 404, `/industries/hvac` → 404, `/locations/phoenix/hvac` → 404,
`/contact` → 404; only `/` → 200). These pages exist on the expanded temp.instaweb.agency
build only. The sitemap is the owner's "future-ready" file — deployed as-is per instruction.

## Files
- `/home/team/shared/instaweb3.0/sitemap.xml` (owner file, 10,032 B)
- `/home/team/shared/instaweb3.0/robots.txt` (owner file, 166 B)
- This report: `/home/team/shared/instaweb3.0/sitemap_robots_deploy_report.md`

## Follow-up
- When the expanded site (pricing/industries/locations/contact pages) is deployed to
  instaweb.agency, the 57 sitemap URLs will resolve — no sitemap change needed then.
- Cloudflare-managed robots.txt prefix is additive; if the owner wants it removed, that's a
  Cloudflare dashboard setting (AI/Bot management), not a repo change.
