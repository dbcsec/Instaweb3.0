// POST /api/caller/leads — Ingest leads with dedup per Instaweb Lead Protocol v1.1
// GET /api/caller/leads — List leads (paginated, optional ?source= filter)
// GET /api/caller/leads/:id — Get single lead by lead_id

// Helper: extract plain value from Turso typed cell
function val(cell, fallback = 0) {
  if (cell && typeof cell === 'object' && cell.value !== undefined) {
    const v = cell.value;
    if (cell.type === 'integer') return Number(v);
    return v;
  }
  return cell ?? fallback;
}

// Normalize business name per protocol: lowercase, strip punctuation, strip suffixes
function normalizeName(name) {
  if (!name) return '';
  const suffixes = ['llc','inc','co','the','&','corp','corporation','ltd','limited'];
  let s = name.toLowerCase().replace(/[^a-z0-9\s]/g, '').replace(/\s+/g, ' ').trim();
  for (const suffix of suffixes) {
    const re = new RegExp('\\s+' + suffix + '$');
    s = s.replace(re, '');
  }
  return s.trim();
}

// Normalize phone to E.164
function normalizePhone(phone) {
  if (!phone) return '';
  let digits = phone.replace(/\D/g, '');
  if (digits.length === 10) digits = '1' + digits;
  if (digits.length === 11 && digits[0] === '1') return '+' + digits;
  return '+' + digits;
}

function normalizeCity(city) {
  if (!city) return '';
  return city.toLowerCase().replace(/[^a-z\s]/g, '').trim();
}

function normalizeState(state) {
  if (!state) return '';
  return state.toLowerCase().slice(0, 2);
}

async function computeLeadId(businessName, phone, city, state) {
  const input = normalizeName(businessName) + '|' + normalizePhone(phone) + '|' + normalizeCity(city) + ',' + normalizeState(state);
  const encoder = new TextEncoder();
  const data = encoder.encode(input);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

function escape(s) {
  return (s || '').replace(/'/g, "''");
}

function buildLeadObj(rows, cols) {
  if (!rows || rows.length === 0) return null;
  const obj = {};
  rows[0].forEach((cell, i) => { obj[cols[i]?.name || 'col' + i] = val(cell, null); });
  return obj;
}

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 'no-cache');
  if (req.method === 'OPTIONS') return res.status(200).end();

  const DB_URL = process.env.TEAM_DB_URL || 'libsql://agent-team-84564803-cto.aws-us-west-2.turso.io';
  const DB_TOKEN = process.env.TEAM_DB_AUTH_TOKEN || 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODEyMDMxMDcsImlkIjoiMDE5ZWI3ZmEtN2UwMS03NDg4LWEyODctMjIzOWNkMWQxZWU0IiwicmlkIjoiY2Q5MDIyYTItMmFmMS00NmY0LWIyYTUtZDc1ODQxNTk0YTI0In0.I74NzuKD7PUSeNbJjA9b8jbZhUywKjbM4QIl0oDFCMs6rLtfToT7Cj25LGXh2zsw2759tLL5mPRsr4GsyOpYBQ';
  const apiUrl = DB_URL.replace('libsql://', 'https://');

  async function dbQuery(sql) {
    const resp = await fetch(apiUrl + '/v2/pipeline', {
      method: 'POST',
      headers: {'Authorization': 'Bearer ' + DB_TOKEN, 'Content-Type': 'application/json'},
      body: JSON.stringify({requests: [{type:'execute', stmt:{sql: sql}}]})
    });
    return await resp.json();
  }

  try {
    // --- GET: List leads ---
    if (req.method === 'GET') {
      const url = new URL(req.url, 'http://localhost');
      const source = url.searchParams.get('source') || '';
      const page = parseInt(url.searchParams.get('page')) || 1;
      const limit = parseInt(url.searchParams.get('limit')) || 50;
      
      let where = '';
      if (source) where = " WHERE source = '" + source.replace(/'/g, "''") + "'";
      
      // All leads_pool rows (caller page fetches the full set)
      const listResp = await dbQuery("SELECT * FROM leads_pool" + where + " ORDER BY first_seen_at DESC");
      const rows = listResp?.results?.[0]?.response?.result?.rows || [];
      const cols = listResp?.results?.[0]?.response?.result?.cols || [];
      
      const leads = rows.map(row => {
        const obj = {};
        row.forEach((cell, i) => { obj[cols[i]?.name || 'col' + i] = val(cell, null); });
        return obj;
      });
      
      // Load per-email A/B/C send dates (sidecar table populated from email_send_log.json)
      let sendDates = new Map();
      try {
        const sdResp = await dbQuery("SELECT email, business, city, state, industry, demo_url, email_sent_a, email_sent_b, email_sent_c FROM lead_send_dates");
        const sdRows = sdResp?.results?.[0]?.response?.result?.rows || [];
        const sdCols = sdResp?.results?.[0]?.response?.result?.cols || [];
        sdRows.forEach(row => {
          const obj = {};
          row.forEach((cell, i) => { obj[sdCols[i]?.name || 'col' + i] = val(cell, null); });
          obj.key = (obj.email || '').toLowerCase().trim();
          sendDates.set(obj.key, obj);
        });
      } catch (e) {
        // table may not exist yet — degrade gracefully
        sendDates = new Map();
      }
      
      // Attach A/B/C to existing leads_pool leads by email
      const seen = new Set();
      for (const l of leads) {
        const key = (l.email || '').toLowerCase().trim();
        const sd = sendDates.get(key);
        if (sd) {
          l.email_sent_a = sd.email_sent_a || '';
          l.email_sent_b = sd.email_sent_b || '';
          l.email_sent_c = sd.email_sent_c || '';
          l.emailed = true;
          seen.add(key);
        }
      }
      
      // Append emailed-only leads (in send history but not in leads_pool) so ALL sent leads show
      for (const sd of sendDates.values()) {
        if (seen.has(sd.key)) continue;
        seen.add(sd.key);
        leads.push({
          business_name: sd.business || '',
          phone: '', city: sd.city || '', state: sd.state || '',
          industry: sd.industry || '', email: sd.email || '',
          demo_url: sd.demo_url || '',
          emailed: true, email_sent_a: sd.email_sent_a || '',
          email_sent_b: sd.email_sent_b || '', email_sent_c: sd.email_sent_c || ''
        });
      }
      
      // Paginate in memory over the merged set
      const total = leads.length;
      const offset = (page - 1) * limit;
      const pageLeads = leads.slice(offset, offset + limit);
      
      return res.status(200).json({leads: pageLeads, total, page, limit, total_pages: Math.ceil(total / limit)});
    }
    
    // --- POST: Ingest lead ---
    if (req.method === 'POST') {
      let body = '';
      await new Promise(resolve => { req.on('data', chunk => { body += chunk; }); req.on('end', resolve); });
      let input;
      try { input = JSON.parse(body); } catch(e) {
        return res.status(422).json({status: 'error', message: 'Invalid JSON body'});
      }
      
      // A-4: Validate source field — single-valued only, pattern ^[a-z0-9_]+$
      if (!input.source) {
        return res.status(422).json({status: 'error', message: 'Missing required field: source'});
      }
      if (input.source.includes(',') || input.source.includes(' ') || !/^[a-z0-9_]+$/.test(input.source)) {
        return res.status(422).json({status: 'error', message: 'Invalid source. Must be single-valued, pattern: ^[a-z0-9_]+$'});
      }
      const validSources = ['polsia', 'instaweb', 'manual', 'caller'];
      if (!validSources.includes(input.source)) {
        return res.status(422).json({status: 'error', message: 'Invalid source. Must be one of: ' + validSources.join(', ')});
      }
      
      // Validate required fields
      const required = ['business_name', 'phone', 'city', 'state', 'lead_id'];
      for (const field of required) {
        if (!input[field] || !input[field].toString().trim()) {
          return res.status(422).json({status: 'error', message: 'Missing required field: ' + field});
        }
      }
      
      const leadId = input.lead_id;
      const phone = normalizePhone(input.phone);
      const normName = normalizeName(input.business_name);
      const now = new Date().toISOString();
      const forceCreate = req.headers['x-lead-force-create'] === 'true';
      
      // Rule 1: Check exact match by lead_id
      const checkResp = await dbQuery("SELECT * FROM leads_pool WHERE lead_id = '" + escape(leadId) + "'");
      const existingRows = checkResp?.results?.[0]?.response?.result?.rows || [];
      const existingCols = checkResp?.results?.[0]?.response?.result?.cols || [];
      
      if (existingRows.length > 0) {
        return res.status(200).json({status: 'duplicate', lead_id: leadId});
      }
      
      // Check same phone for Rule 2 (conflict) and A-1 (dual-match)
      const phoneResp = await dbQuery("SELECT * FROM leads_pool WHERE phone = '" + escape(phone) + "'");
      const phoneRows = phoneResp?.results?.[0]?.response?.result?.rows || [];
      const phoneCols = phoneResp?.results?.[0]?.response?.result?.cols || [];
      
      if (phoneRows.length > 0) {
        const existing = buildLeadObj(phoneRows, phoneCols);
        const existingNorm = normalizeName(existing.business_name || '');
        
        // A-1: Dual-match — phone AND business_name both match, but lead_id differs
        if (existingNorm === normName && existing.lead_id !== leadId) {
          // Dual-match detected
          if (forceCreate) {
            // X-Lead-Force-Create: true — create new record, mark old as superseded
            const insertSql = "INSERT INTO leads_pool (lead_id, business_name, phone, city, state, industry, email, demo_url, source, notes, metadata, first_seen_at, last_updated_at) VALUES ('" +
              escape(leadId) + "','" + escape(input.business_name) + "','" + escape(phone) + "','" +
              escape(input.city) + "','" + escape(input.state) + "','" + escape(input.industry) + "','" +
              escape(input.email) + "','" + escape(input.demo_url) + "','" + escape(input.source) + "','" +
              escape(input.notes) + "','" + (input.metadata ? escape(JSON.stringify(input.metadata)) : '') + "','" +
              (input.first_seen_at || now) + "','" + now + "')";
            
            const insertResp = await dbQuery(insertSql);
            const insertResult = insertResp?.results?.[0];
            if (insertResult?.type === 'error') {
              return res.status(500).json({status: 'error', message: insertResult.error.message});
            }
            
            // Mark old record as superseded
            await dbQuery("UPDATE leads_pool SET superseded_by = '" + escape(leadId) + "', last_updated_at = '" + now + "' WHERE lead_id = '" + escape(existing.lead_id) + "'");
            
            // Log conflict
            await dbQuery("INSERT INTO conflict_log (lead_id_a, lead_id_b, business_name_a, business_name_b, phone, conflict_type) VALUES ('" +
              escape(existing.lead_id) + "','" + escape(leadId) + "','" + escape(existing.business_name) + "','" +
              escape(input.business_name) + "','" + escape(phone) + "','dual_match')");
            
            return res.status(200).json({status: 'inserted_force', lead_id: leadId, supersedes: existing.lead_id});
          } else {
            // Auto-merge into older record (append metadata to merge_history)
            const existingMeta = existing.merge_history || '[]';
            let mergeHistory;
            try { mergeHistory = JSON.parse(existingMeta); } catch(e) { mergeHistory = []; }
            mergeHistory.push({
              merged_at: now,
              inbound_lead_id: leadId,
              inbound_business_name: input.business_name,
              inbound_metadata: input.metadata || {}
            });
            
            const updateSql = "UPDATE leads_pool SET merge_history = '" + escape(JSON.stringify(mergeHistory)) + "', last_updated_at = '" + now + "' WHERE lead_id = '" + escape(existing.lead_id) + "'";
            await dbQuery(updateSql);
            
            // Log conflict
            await dbQuery("INSERT INTO conflict_log (lead_id_a, lead_id_b, business_name_a, business_name_b, phone, conflict_type) VALUES ('" +
              escape(existing.lead_id) + "','" + escape(leadId) + "','" + escape(existing.business_name) + "','" +
              escape(input.business_name) + "','" + escape(phone) + "','dual_match')");
            
            return res.status(200).json({status: 'merged', lead_id: existing.lead_id, merged_into: existing.lead_id});
          }
        }
        
        // Rule 2: Same phone, different name (not dual-match)
        if (existingNorm !== normName && existing.lead_id !== leadId) {
          await dbQuery("INSERT INTO conflict_log (lead_id_a, lead_id_b, business_name_a, business_name_b, phone, conflict_type) VALUES ('" +
            escape(existing.lead_id) + "','" + escape(leadId) + "','" + escape(existing.business_name) + "','" +
            escape(input.business_name) + "','" + escape(phone) + "','phone_match')");
          
          return res.status(409).json({
            status: 'conflict',
            message: 'Same phone, different business name',
            existing: {lead_id: existing.lead_id, business_name: existing.business_name},
            incoming: {lead_id: leadId, business_name: input.business_name}
          });
        }
      }
      
      // Insert new lead (Rule 3 or clean insert)
      const insertSql = "INSERT INTO leads_pool (lead_id, business_name, phone, city, state, industry, email, demo_url, source, notes, metadata, first_seen_at, last_updated_at, last_activity_at) VALUES ('" +
        escape(leadId) + "','" + escape(input.business_name) + "','" + escape(phone) + "','" +
        escape(input.city) + "','" + escape(input.state) + "','" + escape(input.industry) + "','" +
        escape(input.email) + "','" + escape(input.demo_url) + "','" + escape(input.source) + "','" +
        escape(input.notes) + "','" + (input.metadata ? escape(JSON.stringify(input.metadata)) : '') + "','" +
        (input.first_seen_at || now) + "','" + now + "','" + now + "')";
      
      const insertResp = await dbQuery(insertSql);
      const insertResult = insertResp?.results?.[0];
      
      if (insertResult?.type === 'error') {
        return res.status(500).json({status: 'error', message: insertResult.error.message});
      }
      
      return res.status(200).json({status: 'inserted', lead_id: leadId});
    }
    
    return res.status(405).json({error: 'Method not allowed'});
    
  } catch(err) {
    return res.status(500).json({status: 'error', message: err.message});
  }
};