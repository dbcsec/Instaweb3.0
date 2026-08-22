module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 'no-cache');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).end({error:'POST only'});

  const DB_URL = process.env.TEAM_DB_URL || 'libsql://agent-team-84564803-cto.aws-us-west-2.turso.io';
  const DB_TOKEN = process.env.TEAM_DB_AUTH_TOKEN || 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODEyMDMxMDcsImlkIjoiMDE5ZWI3ZmEtN2UwMS03NDg4LWEyODctMjIzOWNkMWQxZWU0IiwicmlkIjoiY2Q5MDIyYTItMmFmMS00NmY0LWIyYTUtZDc1ODQxNTk0YTI0In0.I74NzuKD7PUSeNbJjA9b8jbZhUywKjbM4QIl0oDFCMs6rLtfToT7Cj25LGXh2zsw2759tLL5mPRsr4GsyOpYBQ';
  const apiUrl = DB_URL.replace('libsql://', 'https://');

  try {
    const body = req.body || [];
    if (!Array.isArray(body)) return res.status(400).json({ ok: false, error: 'body must be an array' });
    const timestamp = new Date().toISOString();

    // Turso /v2/pipeline REQUIRES typed Value args ({type:'text',value:...}),
    // NOT plain strings — plain strings fail with "expected Value enum".
    const tv = (s) => ({ type: 'text', value: s === null || s === undefined ? '' : String(s) });

    const queries = [{
      type: 'execute',
      stmt: { sql: "CREATE TABLE IF NOT EXISTS call_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, business_name TEXT, phone TEXT, contact_name TEXT, email TEXT, status TEXT, notes TEXT, synced_at TEXT)" }
    }];

    for (const log of body) {
      queries.push({
        type: 'execute',
        stmt: {
          sql: "INSERT INTO call_logs (business_name, phone, contact_name, email, status, notes, synced_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
          args: [tv(log.business), tv(log.phone), tv(log.contact), tv(log.email), tv(log.status), tv(log.notes), tv(timestamp)]
        }
      });
    }

    const resp = await fetch(`${apiUrl}/v2/pipeline`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${DB_TOKEN}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ requests: queries })
    });
    const out = await resp.json();

    // Validate the actual DB response — do NOT report success on silent failure.
    const results = (out && out.results) || [];
    const err = results.find(r => r && r.type === 'error');
    const okCount = results.filter(r => r && r.type === 'ok').length;
    if (err) {
      const msg = (err.error && err.error.message) || 'turso pipeline error';
      res.status(200).json({ ok: false, error: msg, saved: 0, total: body.length, timestamp });
      return;
    }
    // Expect 1 CREATE + N INSERT ok results.
    const expected = 1 + body.length;
    if (body.length > 0 && okCount < expected) {
      res.status(200).json({ ok: false, error: `only ${okCount}/${expected} queries succeeded`, saved: okCount - 1, total: body.length, timestamp });
      return;
    }

    res.status(200).json({ ok: true, saved: body.length, ok_results: okCount, timestamp });
  } catch(err) {
    res.status(200).json({ ok: false, error: err.message });
  }
};
