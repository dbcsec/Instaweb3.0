// POST /api/lead-intake/validate — Validate batch of leads
// POST /api/lead-intake/import — Import approved leads

const DB_URL = process.env.TEAM_DB_URL || 'libsql://agent-team-84564803-cto.aws-us-west-2.turso.io';
const DB_TOKEN = process.env.TEAM_DB_AUTH_TOKEN || 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODEyMDMxMDcsImlkIjoiMDE5ZWI3ZmEtN2UwMS03NDg4LWEyODctMjIzOWNkMWQxZWU0IiwicmlkIjoiY2Q5MDIyYTItMmFmMS00NmY0LWIyYTUtZDc1ODQxNTk0YTI0In0.I74NzuKD7PUSeNbJjA9b8jbZhUywKjbM4QIl0oDFCMs6rLtfToT7Cj25LGXh2zsw2759tLL5mPRsr4GsyOpYBQ';
const apiUrl = DB_URL.replace('libsql://', 'https://');

function val(cell, fallback) {
  if (cell && typeof cell === 'object' && cell.value !== undefined) {
    return cell.value;
  }
  return cell ?? fallback ?? null;
}

async function dbQuery(sql) {
  const resp = await fetch(apiUrl + '/v2/pipeline', {
    method: 'POST',
    headers: { 'Authorization': 'Bearer ' + DB_TOKEN, 'Content-Type': 'application/json' },
    body: JSON.stringify({ requests: [{ type: 'execute', stmt: { sql: sql } }] })
  });
  return await resp.json();
}

// Turso /v2/pipeline REQUIRES typed Value args ({type:'text',value:...}),
// NOT plain strings — plain strings fail with "expected Value enum".
function tv(s) {
  return { type: 'text', value: s === null || s === undefined ? '' : String(s) };
}

/**
 * Execute a parameterized write (insert/update) with TYPED args and validate the
 * response. Returns { ok: true } or { ok: false, error: string }. Never reports
 * success on a silent DB failure.
 */
async function dbWrite(sql, args) {
  const resp = await fetch(apiUrl + '/v2/pipeline', {
    method: 'POST',
    headers: { 'Authorization': 'Bearer ' + DB_TOKEN, 'Content-Type': 'application/json' },
    body: JSON.stringify({ requests: [{ type: 'execute', stmt: { sql, args: (args || []).map(tv) } }] })
  });
  const out = await resp.json();
  if (!out || !out.results || !Array.isArray(out.results)) {
    return { ok: false, error: 'unexpected DB response structure' };
  }
  const first = out.results[0];
  if (!first || first.type === 'error') {
    return { ok: false, error: 'DB error: ' + ((first && first.error && first.error.message) || 'unknown') };
  }
  return { ok: true };
}

/**
 * Check whether a Turso pipeline response contains an error in the first result.
 * Returns { ok: true } or { ok: false, error: string }.
 */
function checkDbResult(dbResp, context) {
  if (!dbResp || !dbResp.results || !Array.isArray(dbResp.results)) {
    return { ok: false, error: context + ': unexpected response structure' };
  }
  const first = dbResp.results[0];
  if (first.type === 'error') {
    return { ok: false, error: context + ': ' + (first.error?.message || 'unknown DB error') };
  }
  return { ok: true };
}

function escape(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/'/g, "''");
}

function normalizePhone(phone) {
  if (!phone) return '';
  let digits = phone.replace(/\D/g, '');
  if (digits.length === 10) digits = '1' + digits;
  if (digits.length === 11 && digits[0] === '1') return '+' + digits;
  return '+' + digits;
}

function extractDomain(url) {
  if (!url) return '';
  try {
    const u = new URL(url.startsWith('http') ? url : 'https://' + url);
    return u.hostname.replace(/^www\./, '').toLowerCase();
  } catch { return ''; }
}

// Suspicious patterns for quarantine
const SUSPICIOUS_PATTERNS = [
  /test/i, /fake/i, /demo/i, /example/i, /xxx/i, /porn/i,
  /asdf/i, /qwerty/i, /aaaa/i, /zzzz/i, /test[0-9]/i,
];

function isSuspicious(lead) {
  const name = (lead.business_name || '').toLowerCase();
  const phone = (lead.phone || '');
  
  // Repeated characters in name (>5 same char)
  if (/(.)\1{5,}/.test(name)) return 'Repeated characters in name';
  
  // Known fake patterns
  for (const pat of SUSPICIOUS_PATTERNS) {
    if (pat.test(name)) return 'Matches junk pattern: ' + pat.source;
  }
  
  // All-numeric name
  if (/^\d+$/.test(name.replace(/\s/g, ''))) return 'All-numeric business name';
  
  // Phone is all zeros or sequential
  const digits = phone.replace(/\D/g, '');
  if (/^0{7,}$/.test(digits)) return 'Phone is all zeros';
  if (/^(\d)\1{6,}$/.test(digits)) return 'Phone is repeated digit';
  
  return null;
}

function validateLead(lead) {
  const errors = [];
  
  if (!lead.business_name || !lead.business_name.trim()) {
    errors.push('Missing business name');
  }
  
  // Phone validation (optional but validate format if present)
  if (lead.phone && lead.phone.trim()) {
    const digits = lead.phone.replace(/\D/g, '');
    if (digits.length < 10) errors.push('Phone too short (< 10 digits)');
  }
  
  // Email validation (optional but validate format)
  if (lead.email && lead.email.trim()) {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(lead.email)) {
      errors.push('Invalid email format');
    }
  }
  
  // URL validation (optional — website is stored in metadata JSON, not as a DB column)
  if (lead.website && lead.website.trim()) {
    try { new URL(lead.website.startsWith('http') ? lead.website : 'https://' + lead.website); }
    catch { errors.push('Invalid website URL'); }
  }
  
  return errors;
}

module.exports = async function handler(req, res) {
  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const url = new URL(req.url, 'http://localhost');
  const path = url.pathname.replace(/\/$/, '');

  try {
    if (path === '/api/lead-intake/validate') {
      return await handleValidate(req, res);
    }
    if (path === '/api/lead-intake/import') {
      return await handleImport(req, res);
    }
    return res.status(404).json({ error: 'Not found' });
  } catch (err) {
    return res.status(500).json({ status: 'error', message: err.message });
  }
};

async function handleValidate(req, res) {
  let body = '';
  req.on('data', chunk => body += chunk);
  req.on('end', async () => {
    try {
      const { leads } = JSON.parse(body);
      if (!Array.isArray(leads) || leads.length === 0) {
        return res.status(422).json({ status: 'error', message: 'leads array required' });
      }
      
      const results = [];
      
      for (const lead of leads) {
        // Enforce consent defaults
        lead.consent_status = lead.consent_status || 'public_directory';
        lead.opted_in = lead.opted_in || 'false';
        
        // Validate
        const errors = validateLead(lead);
        if (errors.length > 0) {
          results.push({
            ...lead,
            status: 'error',
            errors,
            duplicates: [],
          });
          continue;
        }
        
        // Quarantine check
        const quarantineReason = isSuspicious(lead);
        if (quarantineReason) {
          results.push({
            ...lead,
            status: 'quarantine',
            errors: [quarantineReason],
            duplicates: [],
          });
          continue;
        }
        
        // Dedup checks — with explicit error surfacing
        const duplicates = [];
        const dedupErrors = [];
        const normPhone = normalizePhone(lead.phone);
        const domain = extractDomain(lead.website);
        
        // Check phone
        if (normPhone && normPhone !== '+') {
          const phoneResp = await dbQuery(
            "SELECT lead_id, business_name, phone FROM leads_pool WHERE phone = '" + escape(normPhone) + "' LIMIT 3"
          );
          const phoneCheck = checkDbResult(phoneResp, 'Phone dedup query');
          if (!phoneCheck.ok) {
            dedupErrors.push(phoneCheck.error);
          } else {
            const phoneRows = phoneResp.results[0].response.result.rows || [];
            for (const row of phoneRows) {
              duplicates.push({
                type: 'phone_match',
                lead_id: val(row[0]),
                business_name: val(row[1]),
                phone: val(row[2]),
              });
            }
          }
        }
        
        // Check domain from website (stored in metadata JSON column)
        // Schema has NO dedicated 'website' column — match api/caller/leads.js convention
        if (domain) {
          const domainResp = await dbQuery(
            "SELECT lead_id, business_name, metadata FROM leads_pool WHERE metadata LIKE '%" + escape(domain) + "%' LIMIT 3"
          );
          const domainCheck = checkDbResult(domainResp, 'Domain dedup query');
          if (!domainCheck.ok) {
            dedupErrors.push(domainCheck.error);
          } else {
            const domainRows = domainResp.results[0].response.result.rows || [];
            for (const row of domainRows) {
              if (!duplicates.find(d => d.lead_id === val(row[0]))) {
                duplicates.push({
                  type: 'domain_match',
                  lead_id: val(row[0]),
                  business_name: val(row[1]),
                });
              }
            }
          }
        }
        
        // Check name+city
        if (lead.business_name && lead.city) {
          const nameNorm = lead.business_name.toLowerCase().replace(/[^a-z0-9]/g, '');
          const cityNorm = lead.city.toLowerCase().replace(/[^a-z]/g, '');
          // Use 4 single quotes ('''') in SQL — produces one literal apostrophe char
          // for REPLACE search. Previously used double-quoted \"'\" which SQLite
          // interprets as an identifier, causing: no such column: \"'\"
          const nameResp = await dbQuery(
            "SELECT lead_id, business_name, city FROM leads_pool WHERE LOWER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(business_name,' ',''),'-',''),'''' ,''),'.',''),',','')) = '" +
            escape(nameNorm) + "' AND LOWER(REPLACE(REPLACE(city,' ',''),'-','')) = '" + escape(cityNorm) + "' LIMIT 1"
          );
          const nameCheck = checkDbResult(nameResp, 'Name+city dedup query');
          if (!nameCheck.ok) {
            dedupErrors.push(nameCheck.error);
          } else {
            const nameRows = nameResp.results[0].response.result.rows || [];
            for (const row of nameRows) {
              if (!duplicates.find(d => d.lead_id === val(row[0]))) {
                duplicates.push({
                  type: 'name_location_match',
                  lead_id: val(row[0]),
                  business_name: val(row[1]),
                  city: val(row[2]),
                });
              }
            }
          }
        }
        
        // Determine status: if dedup errors occurred, surface them
        let status;
        if (dedupErrors.length > 0 && duplicates.length === 0) {
          status = 'dedup_error';
        } else {
          status = duplicates.length > 0 ? 'duplicate' : 'ok';
        }
        
        results.push({
          ...lead,
          status,
          errors: dedupErrors,
          duplicates,
        });
      }
      
      return res.status(200).json({ status: 'ok', results });
    } catch (e) {
      return res.status(500).json({ status: 'error', message: e.message });
    }
  });
}

async function handleImport(req, res) {
  let body = '';
  req.on('data', chunk => body += chunk);
  req.on('end', async () => {
    try {
      const bodyParsed = JSON.parse(body);
      const { leads } = bodyParsed;
      if (!Array.isArray(leads) || leads.length === 0) {
        return res.status(422).json({ status: 'error', message: 'leads array required' });
      }
      
      // Server-side consent gate — client checkbox is not a security control
      if (bodyParsed.consent_confirmed !== true) {
        return res.status(422).json({ status: 'error', message: 'consent_confirmed=true required' });
      }
      
      let imported = 0;
      const errors = [];
      const now = new Date().toISOString();
      
      for (const lead of leads) {
        try {
          // Enforce consent defaults
          lead.consent_status = lead.consent_status || 'public_directory';
          lead.opted_in = lead.opted_in || 'false';
          
          // Server-side re-validation — do not trust client blindly
          const valErrors = validateLead(lead);
          if (valErrors.length > 0) {
            errors.push({ business_name: lead.business_name, error: 'Validation failed: ' + valErrors.join('; ') });
            continue;
          }
          
          const quarantineReason = isSuspicious(lead);
          if (quarantineReason) {
            errors.push({ business_name: lead.business_name, error: 'Quarantined: ' + quarantineReason });
            continue;
          }
          
          // Server-side dedup check (phone match only — fast check before import)
          const normPhone = normalizePhone(lead.phone);
          if (normPhone && normPhone !== '+') {
            const phoneResp = await dbQuery(
              "SELECT lead_id, business_name FROM leads_pool WHERE phone = '" + escape(normPhone) + "' LIMIT 1"
            );
            const phoneCheck = checkDbResult(phoneResp, 'Import phone dedup');
            if (phoneCheck.ok) {
              const phoneRows = phoneResp.results[0].response.result.rows || [];
              if (phoneRows.length > 0) {
                errors.push({
                  business_name: lead.business_name,
                  error: 'Duplicate phone: ' + val(phoneRows[0][1]) + ' (' + val(phoneRows[0][0]) + ')'
                });
                continue;
              }
            }
          }
          
          const leadId = lead.lead_id || 
            require('crypto').createHash('sha256')
              .update((lead.business_name + '|' + (lead.phone || '') + '|' + (lead.city || '') + ',' + (lead.state || '')).toLowerCase())
              .digest('hex');
          
          // Check if already exists
          const checkResp = await dbQuery(
            "SELECT lead_id FROM leads_pool WHERE lead_id = '" + escape(leadId) + "'"
          );
          const checkResult = checkDbResult(checkResp, 'Existence check');
          if (!checkResult.ok) {
            errors.push({ business_name: lead.business_name, error: checkResult.error });
            continue;
          }
          const existingRows = checkResp.results[0].response.result.rows || [];
          if (existingRows.length > 0) {
            errors.push({ business_name: lead.business_name, error: 'Already exists (lead_id match)' });
            continue;
          }
          
          // Build metadata JSON — store extras here since the schema has no
          // dedicated columns for website, consent_status, or opted_in.
          // api/caller/leads.js does NOT use these as columns; neither do we.
          const metadataObj = {
            scrape_date: lead.scrape_date || null,
            source_url: lead.source_url || null,
            import_method: 'lead_intake_form',
            website: lead.website || null,
            consent_status: lead.consent_status || 'public_directory',
            opted_in: lead.opted_in || 'false',
          };
          
          // NOTE: Schema has NO 'website' column (confirmed via PRAGMA table_info).
          // Columns: id, lead_id, business_name, phone, city, state, industry, email,
          //   demo_url, source, status, notes, metadata, first_seen_at, last_updated_at,
          //   contacted_at, conflict_flag, last_activity_at, merge_history,
          //   superseded_by, outage_queued, stale
          const insertSql =
            "INSERT INTO leads_pool (lead_id, business_name, phone, city, state, industry, email, demo_url, source, notes, metadata, first_seen_at, last_updated_at, last_activity_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)";
          const insertArgs = [
            leadId,
            lead.business_name,
            normalizePhone(lead.phone),
            lead.city,
            lead.state,
            lead.trade || lead.industry || '',
            lead.email,
            lead.demo_url,
            lead.source_url || 'owner_upload',
            lead.notes,
            JSON.stringify(metadataObj),
            lead.scrape_date ? lead.scrape_date + 'T00:00:00Z' : now,
            now,
            now
          ];

          const insertCheck = await dbWrite(insertSql, insertArgs);
          if (!insertCheck.ok) {
            errors.push({ business_name: lead.business_name, error: insertCheck.error });
            continue;
          }
          
          imported++;
        } catch (e) {
          errors.push({ business_name: lead.business_name, error: e.message });
        }
      }
      
      return res.status(200).json({
        status: 'ok',
        imported,
        errors: errors.length > 0 ? errors : undefined,
        message: `Imported ${imported} leads` + (errors.length > 0 ? `, ${errors.length} errors` : ''),
      });
    } catch (e) {
      return res.status(500).json({ status: 'error', message: e.message });
    }
  });
}
