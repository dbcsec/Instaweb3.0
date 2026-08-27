/**
 * POST /api/resend-webhook — Resend delivery/engagement webhook receiver.
 *
 * Persists Resend email events (sent, delivered, opened, clicked, bounced,
 * complained, delivery_delayed) into the shared Turso table `email_events` so
 * the team has REAL delivery/engagement data, not just "202 accepted".
 *
 * Configured in Resend to point at https://instaweb.agency/api/resend-webhook
 * with a shared webhook secret. Signature is verified when headers/secret are
 * present (HMAC-SHA256 over raw body + timestamp, hex or base64).
 */
const DB_URL = process.env.TEAM_DB_URL || 'libsql://agent-team-84564803-cto.aws-us-west-2.turso.io';
const DB_TOKEN = process.env.TEAM_DB_AUTH_TOKEN || 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODEyMDMxMDcsImlkIjoiMDE5ZWI3ZmEtN2UwMS03NDg4LWEyODctMjIzOWNkMWQxZWU0IiwicmlkIjoiY2Q5MDIyYTItMmFmMS00NmY0LWIyYTUtZDc1ODQxNTk0YTI0In0.I74NzuKD7PUSeNbJjA9b8jbZhUywKjbM4QIl0oDFCMs6rLtfToT7Cj25LGXh2zsw2759tLL5mPRsr4GsyOpYBQ';
// Resend assigns its OWN signing secret (whsec_...) at webhook creation —
// verify real events with that exact secret. Override via env if Resend rotates it.
const WEBHOOK_SECRET = process.env.RESEND_WEBHOOK_SECRET || 'whsec_zSzcCsIHBH+PnJnaoLvIojt1oe1hkd4P';

const apiUrl = DB_URL.replace('libsql://', 'https://');

function toList(emails) {
  if (!emails) return '';
  if (Array.isArray(emails)) return emails.join(', ');
  return String(emails);
}

// Turso /v2/pipeline requires typed Value arguments ({type:'text', value:...}),
// NOT plain strings — plain strings cause a silent "expected Value enum" failure.
function tv(s) {
  return { type: 'text', value: s === null || s === undefined ? '' : String(s) };
}

async function persist(eventType, emailId, createdAt, toEmail, subject, lastEvent, raw) {
  const resp = await fetch(apiUrl + '/v2/pipeline', {
    method: 'POST',
    headers: { 'Authorization': 'Bearer ' + DB_TOKEN, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      requests: [
        {
          type: 'execute',
          stmt: { sql: `CREATE TABLE IF NOT EXISTS email_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT,
            event_type TEXT,
            created_at TEXT,
            to_email TEXT,
            subject TEXT,
            last_event TEXT,
            raw TEXT
          )` }
        },
        {
          type: 'execute',
          stmt: {
            sql: `INSERT INTO email_events (email_id, event_type, created_at, to_email, subject, last_event, raw)
                  VALUES (?, ?, ?, ?, ?, ?, ?)`,
            args: [tv(emailId), tv(eventType), tv(createdAt), tv(toEmail), tv(subject), tv(lastEvent), tv(raw)]
          }
        }
      ]
    })
  });
  const out = await resp.json();
  // Validate — if any request errored, surface it so callers aren't misled.
  const results = (out && out.results) || [];
  const err = results.find(r => r && r.type === 'error');
  if (err) throw new Error((err.error && err.error.message) || 'turso pipeline error');
  return !!results.find(r => r && r.type === 'ok');
}

module.exports = async function handler(req, res) {
  if (req.method !== 'POST') { res.status(405).end(); return; }

  // Capture raw body so we can verify the signature byte-exactly.
  const chunks = [];
  try {
    for await (const c of req) chunks.push(c);
  } catch (e) {}
  const raw = Buffer.concat(chunks).toString('utf8');

  const ts = String(req.headers['x-resend-timestamp'] || '');
  const sig = String(req.headers['x-resend-signature'] || '');
  if (WEBHOOK_SECRET && ts && sig) {
    const crypto = require('crypto');
    const payload = String(raw) + String(ts);
    const expectedHex = crypto.createHmac('sha256', WEBHOOK_SECRET).update(payload).digest('hex');
    const expectedB64 = crypto.createHmac('sha256', WEBHOOK_SECRET).update(payload).digest('base64');
    const valid = (expectedHex === sig) || (expectedB64 === sig);
    if (!valid) { res.status(401).json({ error: 'invalid signature' }); return; }
  }

  let data;
  try { data = raw ? JSON.parse(raw) : (req.body || {}); }
  catch (e) { res.status(400).json({ error: 'invalid JSON' }); return; }
  if (!data || typeof data !== 'object') { res.status(400).json({ error: 'missing payload' }); return; }

  const type = data.type || (data.data && data.data.type) || 'email.unknown';
  const d = data.data || data;
  const emailId = d.email_id || '';
  const createdAt = d.created_at || data.created_at || new Date().toISOString();
  const toEmail = toList(d.to);
  const subject = d.subject || '';
  const lastEvent = d.last_event || '';

  try {
    await persist(type, emailId, createdAt, toEmail, subject, lastEvent, JSON.stringify(data));
  } catch (e) {
    // Event storage must not cause Resend to mark the delivery failed.
    res.status(200).json({ ok: false, error: e.message });
    return;
  }
  res.status(200).json({ ok: true, event: type, email_id: emailId });
};
