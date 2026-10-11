const SCALE = { n: 1e-9, u: 1e-6, m: 1e-3, '': 1, k: 1e3, K: 1e3,
  M: 1e6, G: 1e9, T: 1e12, P: 1e15, E: 1e18,
  Ki: 2 ** 10, Mi: 2 ** 20, Gi: 2 ** 30, Ti: 2 ** 40, Pi: 2 ** 50, Ei: 2 ** 60 };

// Kubernetes quantities are not plain numbers (CPU: 12345n, memory: 96Mi).
export function quantity(value) {
  const match = String(value ?? '').match(/^([+]?(?:\d+(?:\.\d*)?|\.\d+))([eE][+-]?\d+|[numkKMGTPE]i?|)$/);
  if (!match) throw new Error('Invalid quantity');
  const suffix = match[2];
  const scale = /^[eE][+-]?\d+$/.test(suffix) ? 10 ** Number(suffix.slice(1)) : SCALE[suffix];
  const result = Number(match[1]) * scale;
  if (!Number.isFinite(result) || result < 0 || result > Number.MAX_SAFE_INTEGER) throw new Error('Invalid quantity');
  return result;
}

const matches = (labels, selector) => selector && Object.keys(selector).length > 0 &&
  Object.entries(selector).every(([key, value]) => labels?.[key] === value);
const iso = (time) => time == null ? null : new Date(time).toISOString();
const state = (time, now, ttl, failed = false) => time == null ? 'unavailable' :
  failed || now - time > ttl ? 'stale' : 'fresh';

function durationSeconds(value) {
  const input = String(value ?? '');
  const units = { ns: 1e-9, us: 1e-6, 'µs': 1e-6, ms: 1e-3, s: 1, m: 60, h: 3600 };
  const parts = [...input.matchAll(/(\d+(?:\.\d+)?)(ns|us|µs|ms|s|m|h)/g)];
  if (!parts.length || parts.map((p) => p[0]).join('') !== input) return NaN;
  return parts.reduce((sum, p) => sum + Number(p[1]) * units[p[2]], 0);
}

function resourceTotal(containers, kind, resource, multiplier) {
  if (!containers.length || containers.some((c) => c.resources?.[kind]?.[resource] == null)) return null;
  return containers.reduce((sum, c) => sum + quantity(c.resources[kind][resource]) * multiplier, 0);
}

function podView(pod, active, preview) {
  const { metadata, spec, status = {} } = pod;
  const containers = spec.containers ?? [];
  const labels = metadata.labels ?? {};
  return {
    uid: metadata.uid, name: metadata.name,
    version: metadata.annotations?.['one-tatchi.dev/app-version'] || null,
    revision: labels['rollouts-pod-template-hash'] || null,
    trafficRole: matches(labels, active?.spec?.selector) ? 'active' :
      matches(labels, preview?.spec?.selector) ? 'preview' : 'inactive',
    phase: status.phase || 'Unknown',
    ready: (status.conditions ?? []).some((c) => c.type === 'Ready' && c.status === 'True'),
    terminating: Boolean(metadata.deletionTimestamp),
    restartCount: (status.containerStatuses ?? []).reduce((sum, c) => sum + (c.restartCount ?? 0), 0),
    resources: {
      cpuRequestMillicores: resourceTotal(containers, 'requests', 'cpu', 1000),
      cpuLimitMillicores: resourceTotal(containers, 'limits', 'cpu', 1000),
      memoryRequestBytes: resourceTotal(containers, 'requests', 'memory', 1),
      memoryLimitBytes: resourceTotal(containers, 'limits', 'memory', 1),
    },
  };
}

export class RuntimeStatus {
  constructor({ read, namespace, serviceName, now = Date.now }) {
    if (![namespace, serviceName].every((s) => typeof s === 'string' && /^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$/.test(s) && s.length <= 63)) {
      throw new Error('Invalid namespace or service name');
    }
    this.read = read;
    this.namespace = namespace;
    this.serviceName = serviceName;
    this.now = now;
    this.pods = [];
    this.metrics = new Map();
    this.inventoryAt = null;
    this.inventoryError = false;
    this.metricsError = false;
    this.busyInventory = false;
    this.busyMetrics = false;
    this.selector = `labelSelector=${encodeURIComponent(`app.kubernetes.io/name=${serviceName}`)}`;
    this.base = `/api/v1/namespaces/${namespace}`;
  }

  async refreshInventory() {
    if (this.busyInventory) return;
    this.busyInventory = true;
    try {
      const [list, active, preview] = await Promise.all([
        this.read(`${this.base}/pods?${this.selector}`),
        this.read(`${this.base}/services/${this.serviceName}`, { optional: true }),
        this.read(`${this.base}/services/${this.serviceName}-preview`, { optional: true }),
      ]);
      if (!Array.isArray(list.items)) throw new Error('Invalid PodList');
      // Only publish a complete successful inventory. An API error is never an empty list.
      const pods = list.items.filter((p) => p.metadata?.labels?.['app.kubernetes.io/name'] === this.serviceName);
      const views = pods.map((p) => podView(p, active, preview));
      this.pods = pods.map((p, i) => ({ pod: p, view: views[i] }));
      const uids = new Set(views.map((p) => p.uid));
      for (const uid of this.metrics.keys()) if (!uids.has(uid)) this.metrics.delete(uid);
      this.inventoryAt = this.now();
      this.inventoryError = false;
    } catch {
      this.inventoryError = true;
    } finally {
      this.busyInventory = false;
    }
  }

  async refreshMetrics() {
    if (this.busyMetrics || this.inventoryAt == null) return;
    this.busyMetrics = true;
    // Keep the UID from query start: a same-name replacement must not inherit an old sample.
    const inventory = this.pods;
    try {
      const list = await this.read(`/apis/metrics.k8s.io/v1beta1/namespaces/${this.namespace}/pods?${this.selector}`);
      if (!Array.isArray(list.items)) throw new Error('Invalid PodMetricsList');
      const byName = new Map(list.items.map((m) => [m.metadata?.name, m]));
      const currentUids = new Set(this.pods.map(({ view }) => view.uid));
      const metrics = new Map();
      for (const { pod, view } of inventory) {
        const m = byName.get(view.name);
        if (!m || !currentUids.has(view.uid)) continue;
        const observedAt = Date.parse(m.timestamp);
        const createdAt = Date.parse(pod.metadata.creationTimestamp);
        const windowSeconds = durationSeconds(m.window);
        if (!Number.isFinite(observedAt) || !Number.isFinite(createdAt) ||
            !Number.isFinite(windowSeconds) || windowSeconds <= 0 ||
            observedAt - windowSeconds * 1000 < createdAt || observedAt > this.now() + 5000) continue;
        const samples = new Map((m.containers ?? []).map((c) => [c.name, c]));
        const containers = pod.spec.containers ?? [];
        if (!containers.length || containers.some((c) => !samples.has(c.name))) continue;
        try {
          metrics.set(view.uid, {
            observedAt: iso(observedAt), windowSeconds,
            cpuMillicores: containers.reduce((sum, c) => sum + quantity(samples.get(c.name).usage?.cpu) * 1000, 0),
            memoryBytes: containers.reduce((sum, c) => sum + quantity(samples.get(c.name).usage?.memory), 0),
          });
        } catch { /* An invalid/partial sample is unavailable, not zero. */ }
      }
      this.metrics = metrics;
      this.metricsError = false;
    } catch {
      this.metricsError = true;
    } finally {
      this.busyMetrics = false;
    }
  }

  snapshot() {
    const now = this.now();
    return {
      inventoryStatus: state(this.inventoryAt, now, 15000, this.inventoryError),
      inventoryObservedAt: iso(this.inventoryAt),
      pods: this.pods.map(({ view }) => {
        const m = this.metrics.get(view.uid);
        return { ...view, metrics: m ? {
          ...m, status: state(Date.parse(m.observedAt), now, 45000, this.metricsError),
        } : { status: 'unavailable', observedAt: null, windowSeconds: null, cpuMillicores: null, memoryBytes: null } };
      }).sort((a, b) => a.name.localeCompare(b.name)),
    };
  }
}
