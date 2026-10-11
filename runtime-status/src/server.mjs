import { readFileSync } from 'node:fs';
import https from 'node:https';
import http from 'node:http';
import { RuntimeStatus } from './runtime.mjs';

const credentials = '/var/run/secrets/kubernetes.io/serviceaccount';
const ca = readFileSync(`${credentials}/ca.crt`);
const namespace = process.env.NAMESPACE || readFileSync(`${credentials}/namespace`, 'utf8').trim();
const host = process.env.KUBERNETES_SERVICE_HOST;
const port = Number(process.env.KUBERNETES_SERVICE_PORT_HTTPS || 443);
if (!host) throw new Error('Kubernetes service address is missing');

function read(path, { optional = false } = {}) {
  return new Promise((resolve, reject) => {
    // Projected tokens rotate; never cache the token across requests.
    const token = readFileSync(`${credentials}/token`, 'utf8').trim();
    const req = https.get({ hostname: host, port, path, ca,
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
      signal: AbortSignal.timeout(3000),
    }, (res) => {
      if (optional && res.statusCode === 404) { res.resume(); resolve(null); return; }
      if (res.statusCode !== 200) { res.resume(); reject(new Error('Kubernetes read failed')); return; }
      let bytes = 0;
      const chunks = [];
      res.on('data', (chunk) => {
        bytes += chunk.length;
        if (bytes > 4 * 1024 * 1024) res.destroy(new Error('Response too large'));
        else chunks.push(chunk);
      });
      res.on('error', reject);
      res.on('end', () => {
        try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); } catch { reject(new Error('Invalid response')); }
      });
    });
    req.on('error', reject);
  });
}

const runtime = new RuntimeStatus({ read, namespace, serviceName: process.env.SERVICE_NAME });
const server = http.createServer((req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('Content-Type', 'application/json');
  if (req.method !== 'GET') { res.writeHead(405, { Allow: 'GET' }).end('{}'); return; }
  if (req.url === '/healthz') { res.end('{"status":"ok"}'); return; }
  if (req.url !== '/api/runtime') { res.writeHead(404).end('{}'); return; }
  const body = runtime.snapshot();
  res.writeHead(body.inventoryStatus === 'unavailable' ? 503 : 200).end(JSON.stringify(body));
});

// Health is independent of upstream availability so an API outage does not restart the cache.
server.listen(8080, '0.0.0.0');
await runtime.refreshInventory();
await runtime.refreshMetrics();
const inventoryTimer = setInterval(() => void runtime.refreshInventory(), 5000);
const metricsTimer = setInterval(() => void runtime.refreshMetrics(), 15000);
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => {
  clearInterval(inventoryTimer);
  clearInterval(metricsTimer);
  server.close(() => process.exit(0));
});
