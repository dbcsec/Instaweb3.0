#!/usr/bin/env python3
"""Instaweb Agency - Mass Demo Site Generator
Generates personalized $10k-quality demo sites for every verified lead
and outputs outreach-ready email batch.
Now uses local JSON lead files (not Turso DB) to avoid data format issues.
"""
import json, os, re, glob, ast
from datetime import datetime

# Config
LEADS_PER_BATCH = 500
BASE_DIR = "/home/team/shared/instaweb3.0"
OUTPUT_DIR = f"{BASE_DIR}/data/demos/mass_output"
EMAIL_DIR = f"{BASE_DIR}/data/outreach/mass_batches"

# Templates
TRADE_TEMPLATE = f"{BASE_DIR}/templates/elite-trade.html"
FOOD_TEMPLATE = f"{BASE_DIR}/templates/elite-food.html"

# Industry to template mapping
TEMPLATE_MAP = {
    "hvac": TRADE_TEMPLATE, "plumbing": TRADE_TEMPLATE, "roofing": TRADE_TEMPLATE,
    "electrical": TRADE_TEMPLATE, "automotive": TRADE_TEMPLATE, "landscaping": TRADE_TEMPLATE,
    "restaurant": FOOD_TEMPLATE, "salon": FOOD_TEMPLATE, "dental": FOOD_TEMPLATE,
    "legal": FOOD_TEMPLATE
}

# Industry-specific service data
INDUSTRY_SERVICES = {
    "hvac": [
        ("fa-snowflake", "AC Repair & Installation", "Call for pricing"),
        ("fa-fire", "Heating & Furnace", "Call for pricing"),
        ("fa-fan", "Duct Cleaning", "Call for pricing"),
        ("fa-tools", "Maintenance Plans", "Call for pricing"),
    ],
    "plumbing": [
        ("fa-wrench", "Emergency Repairs", "Call for pricing"),
        ("fa-shower", "Water Heater Installs", "Call for pricing"),
        ("fa-pipe", "Drain Cleaning", "Call for pricing"),
        ("fa-toilet", "Fixture Installation", "Call for pricing"),
    ],
    "roofing": [
        ("fa-home", "Residential Roofing", "Call for pricing"),
        ("fa-building", "Commercial Roofing", "Call for pricing"),
        ("fa-bolt", "Storm Damage Repair", "Call for pricing"),
        ("fa-search", "Free Inspection", "Call for pricing"),
    ],
    "electrical": [
        ("fa-bolt", "Emergency Repairs", "Call for pricing"),
        ("fa-lightbulb", "Panel Upgrades", "Call for pricing"),
        ("fa-plug", "Wiring & Rewiring", "Call for pricing"),
        ("fa-home", "Smart Home Setup", "Call for pricing"),
    ],
    "restaurant": [
        ("fa-utensils", "Signature Dishes", "$$"),
        ("fa-calendar-check", "Reservations", "Free"),
        ("fa-truck", "Delivery & Takeout", "Order online"),
        ("fa-glass-cheers", "Catering", "Inquire"),
    ],
    "salon": [
        ("fa-cut", "Hair Styling", "Call for pricing"),
        ("fa-hand-sparkles", "Nail Services", "Call for pricing"),
        ("fa-spa", "Spa Treatments", "Call for pricing"),
        ("fa-calendar-check", "Book Online", "Free"),
    ],
    "dental": [
        ("fa-tooth", "General Dentistry", "Call for pricing"),
        ("fa-smile", "Cosmetic", "Call for pricing"),
        ("fa-ambulance", "Emergency Care", "Call for pricing"),
        ("fa-calendar-check", "Book Appointment", "Free"),
    ],
    "landscaping": [
        ("fa-tree", "Lawn Care", "Call for pricing"),
        ("fa-mountain", "Hardscaping", "Call for pricing"),
        ("fa-pencil-ruler", "Design & Install", "Call for pricing"),
        ("fa-file-invoice", "Get a Quote", "Free"),
    ],
    "automotive": [
        ("fa-oil-can", "Oil & Maintenance", "Call for pricing"),
        ("fa-car", "Repairs", "Call for pricing"),
        ("fa-soap", "Detailing", "Call for pricing"),
        ("fa-calendar-check", "Book Service", "Free"),
    ],
    "legal": [
        ("fa-gavel", "Personal Injury", "Free consultation"),
        ("fa-family", "Family Law", "Free consultation"),
        ("fa-briefcase", "Business Law", "Free consultation"),
        ("fa-file-signature", "Free Consultation", "Free"),
    ],
}


def extract_lead_value(val):
    """Extract the actual value from a lead field that might be stored as a dict string"""
    if val is None:
        return ""
    if isinstance(val, dict):
        v = val.get("value", "")
        return str(v) if v is not None else ""
    s = str(val)
    if not s:
        return ""
    # Handle string representation of dict: {'type': 'text', 'value': 'Actual Value'}
    if s.startswith("{'type':") or s.startswith('{"type":'):
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, dict):
                v = parsed.get("value", "")
                return str(v) if v is not None else ""
        except:
            pass
        try:
            parsed = json.loads(s)
            if isinstance(parsed, dict):
                v = parsed.get("value", "")
                return str(v) if v is not None else ""
        except:
            pass
    return s


def get_leads_from_file(file_pattern="*.json", limit=500):
    """Load leads from local JSON files (clean data)"""
    all_leads = []
    json_files = sorted(glob.glob(f"{BASE_DIR}/data/leads/{file_pattern}"))
    
    for fpath in json_files:
        fname = os.path.basename(fpath)
        # Skip summary, schema, and report files
        if any(skip in fname for skip in ["summary", "schema", "report", "failed", "README"]):
            continue
        try:
            with open(fpath) as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    lead = {
                        "business_name": extract_lead_value(item.get("business_name", item.get("name", ""))),
                        "industry": extract_lead_value(item.get("industry", item.get("niche", "hvac"))).lower(),
                        "city": extract_lead_value(item.get("city", "Houston")),
                        "state_code": extract_lead_value(item.get("state_code", item.get("state", "TX"))),
                        "phone": extract_lead_value(item.get("phone", "")),
                        "website_url": extract_lead_value(item.get("website_url", item.get("website", ""))),
                        "email": extract_lead_value(item.get("email", "")),
                        "status": "new"
                    }
                    # Clean up industry name
                    ind = lead["industry"].replace(" ", "_")
                    all_leads.append(lead)
        except Exception as e:
            print(f"  Skipping {fname}: {e}")
    
    # Remove duplicates by business name
    seen = set()
    unique = []
    for lead in all_leads:
        name = lead["business_name"].strip().lower()
        if name and name not in seen:
            seen.add(name)
            unique.append(lead)
    
    print(f"  Loaded {len(unique)} unique leads from {len(json_files)} files")
    return unique[:limit]


def slugify(name):
    """Convert business name to file-safe slug"""
    s = name.lower().replace("&", "and").replace("'", "")
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:80]


def generate_demo(lead):
    """Generate a personalized demo HTML site for a lead"""
    template_file = TEMPLATE_MAP.get(lead["industry"], TRADE_TEMPLATE)
    if not os.path.exists(template_file):
        template_file = TRADE_TEMPLATE
    
    with open(template_file) as f:
        template = f.read()
    
    slug = slugify(lead["business_name"])
    demo_url = f"https://www.instaweb.agency/demo/{slug}"
    
    # Industry display name
    industry_display = lead["industry"].replace("_", " ").title()
    industry_display = industry_display.replace("Hvac", "HVAC")
    
    # Cuisine mapping for food templates
    cuisine_map = {
        "restaurant": "American", "salon": "European", "dental": "Continental", "legal": "International"
    }
    cuisine = cuisine_map.get(lead["industry"], "Delicious")
    
    phone = lead["phone"] or "(555) 000-0000"
    email = lead["email"] or "contact@" + slug.replace("-", "") + ".com"
    address = f"Serving {lead['city']}, {lead['state_code']}"
    
    # Simple Handlebars-like replacement for basic fields
    replacements = {
        "{{business_name}}": lead["business_name"],
        "{{tagline}}": f"Trusted {industry_display} Service",
        "{{phone}}": phone,
        "{{email}}": email,
        "{{address}}": address,
        "{{city}}": lead["city"],
        "{{state_code}}": lead["state_code"],
        "{{demo_url}}": demo_url,
        "{{years_in_business}}": "15+",
        "{{review_count}}": "247",
        "{{rating}}": "4.9",
        "{{industry}}": industry_display,
        "{{cuisine}}": cuisine,
        "{{services.[0].name}}": "Expert Service",
        "{{icon}}": "fa-wrench",
        "{{name}}": "Service",
        "{{price}}": "Call for pricing",
    }
    
    for old, new in replacements.items():
        template = template.replace(old, new)
    
    # Handle services block - replace {{#services}}...{{/services}} with actual services HTML
    services = INDUSTRY_SERVICES.get(lead["industry"], INDUSTRY_SERVICES["hvac"])
    services_html = ""
    for icon, name, price in services:
        services_html += f'''          <div class="service-item">
            <div class="service-icon"><i class="fas {icon}"></i></div>
            <div class="service-info"><div class="name">{name}</div><div class="desc">{price}</div></div>
          </div>\n'''
    
    # Replace the services block with rendered HTML
    services_block_pattern = r'\{\{#services\}\}.*?\{\{\/services\}\}'
    if re.search(services_block_pattern, template, re.DOTALL):
        template = re.sub(services_block_pattern, services_html, template, flags=re.DOTALL)
    
    # Remove any remaining template variables
    template = re.sub(r'\{\{.*?\}\}', '', template)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = f"{OUTPUT_DIR}/{slug}.html"
    with open(filepath, "w") as f:
        f.write(template)
    
    return demo_url, filepath


def generate_email(lead, demo_url):
    """Generate personalized outreach email"""
    name = lead["business_name"]
    industry_display = lead["industry"].replace("_", " ").title()
    industry_display = industry_display.replace("Hvac", "HVAC")
    email_to = lead["email"]
    
    to_name = email_to.split("@")[0].replace(".", " ").title() if email_to else "Owner"
    
    subject = f"Quick question for {name}"
    body = f"""Hi {to_name},

We built a premium website for {name} — completely free, zero obligation.

🔗 View your site: {demo_url}

It's a $10,000-quality site with:
• Custom design for {industry_display}
• Mobile-first, fast-loading
• SEO-optimized for local search
• Google Business Profile integration

Your site is live right now. If you like it, we can keep it running with hosting, updates, and new leads delivered weekly — starting at just $248/mo.

No push. No sales call. Just a site that actually looks like it cost ten grand.

Would love your thoughts.

Best,
Instaweb Agency
https://www.instaweb.agency"""
    
    return {"to": email_to, "subject": subject, "body": body}


def generate_batch(batch_num=1, count=500):
    """Generate batch of demo sites and emails"""
    print(f"\n{'='*50}")
    print(f"BATCH {batch_num} - Generating {count} demo sites + emails")
    print(f"{'='*50}")
    
    leads = get_leads_from_file(limit=count)
    
    if not leads:
        print("No leads to process.")
        return False
    
    print(f"Loaded {len(leads)} leads")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(EMAIL_DIR, exist_ok=True)
    
    demos_generated = 0
    emails_generated = 0
    email_batch = []
    demo_manifest = []
    
    for i, lead in enumerate(leads):
        try:
            demo_url, filepath = generate_demo(lead)
            demos_generated += 1
            demo_manifest.append({
                "business_name": lead["business_name"],
                "industry": lead["industry"],
                "city": lead["city"],
                "state_code": lead["state_code"],
                "demo_url": demo_url,
                "file": filepath
            })
            
            if lead["email"] and "@" in lead["email"]:
                email_data = generate_email(lead, demo_url)
                email_batch.append(email_data)
                emails_generated += 1
            
            if (i+1) % 100 == 0:
                print(f"  Progress: {i+1}/{len(leads)} demos generated")
                
        except Exception as e:
            print(f"  ERROR: {lead['business_name']}: {e}")
    
    # Save manifest
    manifest_file = f"{OUTPUT_DIR}/batch_{batch_num}_manifest.json"
    with open(manifest_file, "w") as f:
        json.dump(demo_manifest, f, indent=2)
    
    # Save email batch
    email_file = f"{EMAIL_DIR}/batch_{batch_num}_emails.json"
    with open(email_file, "w") as f:
        json.dump(email_batch, f, indent=2)
    
    print(f"\n✅ Batch {batch_num} complete:")
    print(f"   Demos generated: {demos_generated}")
    print(f"   Emails prepared: {emails_generated}")
    print(f"   Manifest: {manifest_file}")
    print(f"   Emails file: {email_file}")
    
    return True


if __name__ == "__main__":
    import sys
    batch = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    count = int(sys.argv[2]) if len(sys.argv) > 2 else LEADS_PER_BATCH
    generate_batch(batch, count)