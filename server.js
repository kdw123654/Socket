import 'dotenv/config';
import express from 'express';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const app = express();
const root = path.dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.PORT || 3000);

app.use('/.proxy/backend', async (req, res) => {
  const backendUrl = process.env.BACKEND_URL;
  if (!backendUrl) return res.status(503).json({ error: 'BACKEND_URL is not configured' });

  const target = new URL(req.originalUrl.replace('/.proxy/backend', '') || '/', backendUrl);
  const headers = { ...req.headers };
  delete headers.host;

  try {
    const response = await fetch(target, {
      method: req.method,
      headers,
      body: ['GET', 'HEAD'].includes(req.method) ? undefined : req,
      duplex: 'half',
    });

    res.status(response.status);
    response.headers.forEach((value, key) => {
      if (!['content-encoding', 'transfer-encoding'].includes(key.toLowerCase())) res.setHeader(key, value);
    });
    res.send(Buffer.from(await response.arrayBuffer()));
  } catch (error) {
    res.status(502).json({ error: 'Backend proxy request failed', detail: error.message });
  }
});

app.use(express.json());

app.post(['/api/token', '/.proxy/api/token'], async (req, res) => {
  if (!req.body?.code) return res.status(400).json({ error: 'authorization code is required' });
  if (!process.env.DISCORD_CLIENT_ID || !process.env.DISCORD_CLIENT_SECRET) {
    return res.status(500).json({ error: 'Discord credentials are not configured' });
  }

  const body = new URLSearchParams({
    client_id: process.env.DISCORD_CLIENT_ID,
    client_secret: process.env.DISCORD_CLIENT_SECRET,
    grant_type: 'authorization_code',
    code: req.body.code,
  });
  const response = await fetch('https://discord.com/api/oauth2/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  const data = await response.json();
  return res.status(response.status).json(data);
});

app.use(express.static(path.join(root, 'dist')));
app.get(/.*/, (_req, res) => res.sendFile(path.join(root, 'dist', 'index.html')));
app.listen(port, () => console.log(`Prain Activity listening on ${port}`));
