import test from 'node:test';
import assert from 'node:assert/strict';
import { quantity, RuntimeStatus } from '../src/runtime.mjs';

const start = Date.parse('2026-10-11T00:00:00Z');
const container = (name = 'app') => ({ name, resources: {
  requests: { cpu: '100m', memory: '128Mi' }, limits: { memory: '256Mi' },
} });
function pod(name, uid = name, revision = 'blue') {
  return { metadata: { name, uid, creationTimestamp: new Date(start - 60000).toISOString(),
    labels: { 'app.kubernetes.io/name': 'demo-app-be', 'rollouts-pod-template-hash': revision },
    annotations: { 'one-tatchi.dev/app-version': revision === 'blue' ? 'v1' : 'v2' },
  }, spec: { containers: [container()] }, status: { phase: 'Running',
    conditions: [{ type: 'Ready', status: 'True' }], containerStatuses: [{ restartCount: 2 }],
  } };
}
const service = (revision) => ({ spec: { selector: {
  'app.kubernetes.io/name': 'demo-app-be', 'rollouts-pod-template-hash': revision,
} } });
function fixture() {
  const data = { time: start, pods: [pod('a'), pod('b', 'b', 'green')],
    active: service('blue'), preview: service('green'), failInventory: false, failMetrics: false,
    samples: ['a', 'b'].map((name) => ({ metadata: { name }, timestamp: new Date(start).toISOString(), window: '15s',
      containers: [{ name: 'app', usage: { cpu: '125000000n', memory: '96Mi' } }],
    })), calls: [] };
  const runtime = new RuntimeStatus({ namespace: 'test', serviceName: 'demo-app-be', now: () => data.time,
    read: async (path, options) => {
      data.calls.push([path, options]);
      if (path.startsWith('/apis/metrics')) {
        if (data.failMetrics) throw new Error('private upstream diagnostic');
        return { items: data.samples };
      }
      if (data.failInventory) throw new Error('private upstream diagnostic');
      if (path.includes('/pods?')) return { items: data.pods };
      return path.endsWith('-preview') ? data.preview : data.active;
    },
  });
  return { data, runtime };
}

test('Kubernetes CPU and memory quantities, exponent and zero', () => {
  for (const [input, expected] of [['125000000n', .125], ['250u', .00025], ['125m', .125],
    ['2', 2], ['96Mi', 100663296], ['1Gi', 1073741824], ['1e3', 1000], ['0', 0]]) {
    assert.equal(quantity(input), expected);
  }
  for (const value of ['garbage', '-1', undefined, 'Infinity', '1e1000', '1mi']) {
    assert.throws(() => quantity(value));
  }
});

test('inventory contains every BE without relying on HTTP traffic; blue/green and Pod version', async () => {
  const { data, runtime } = fixture();
  data.pods.push({ ...pod('other'), metadata: { ...pod('other').metadata,
    labels: { 'app.kubernetes.io/name': 'other' } } });
  await runtime.refreshInventory();
  await runtime.refreshMetrics();
  const result = runtime.snapshot();
  assert.equal(result.pods.length, 2);
  assert.deepEqual(result.pods.map((p) => [p.trafficRole, p.version]), [['active', 'v1'], ['preview', 'v2']]);
  assert.equal(result.pods[0].metrics.cpuMillicores, 125);
  assert.equal(result.pods[0].metrics.memoryBytes, 96 * 2 ** 20);
  assert.equal(result.pods[0].resources.cpuLimitMillicores, null);
  assert.equal(result.pods[0].restartCount, 2);
  assert.ok(!JSON.stringify(result).includes('spec'));
});

test('successful empty inventory removes pods; failed inventory keeps last list and marks stale', async () => {
  const { data, runtime } = fixture();
  await runtime.refreshInventory();
  data.failInventory = true;
  await runtime.refreshInventory();
  assert.equal(runtime.snapshot().inventoryStatus, 'stale');
  assert.equal(runtime.snapshot().pods.length, 2);
  assert.ok(!JSON.stringify(runtime.snapshot()).includes('private'));
  data.failInventory = false;
  data.pods = [];
  await runtime.refreshInventory();
  assert.equal(runtime.snapshot().pods.length, 0);
  assert.equal(runtime.snapshot().inventoryStatus, 'fresh');
});

test('missing metrics and metrics outage preserve inventory, never report fabricated zero', async () => {
  const { data, runtime } = fixture();
  assert.equal(runtime.snapshot().inventoryStatus, 'unavailable');
  await runtime.refreshInventory();
  data.samples = [];
  await runtime.refreshMetrics();
  assert.equal(runtime.snapshot().pods[0].metrics.cpuMillicores, null);
  data.failMetrics = true;
  await runtime.refreshMetrics();
  assert.equal(runtime.snapshot().pods.length, 2);
  assert.equal(runtime.snapshot().inventoryStatus, 'fresh');
});

test('source timestamps and failed collection mark last metrics stale', async () => {
  const { data, runtime } = fixture();
  await runtime.refreshInventory();
  await runtime.refreshMetrics();
  data.time += 46000;
  await runtime.refreshInventory();
  assert.equal(runtime.snapshot().inventoryStatus, 'fresh');
  assert.equal(runtime.snapshot().pods[0].metrics.status, 'stale');
  data.time = start;
  data.failMetrics = true;
  await runtime.refreshMetrics();
  assert.equal(runtime.snapshot().pods[0].metrics.status, 'stale');
  assert.equal(runtime.snapshot().pods[0].metrics.cpuMillicores, 125);
});

test('same-name replacement does not inherit previous UID metrics', async () => {
  const { data, runtime } = fixture();
  await runtime.refreshInventory();
  await runtime.refreshMetrics();
  data.pods[0] = pod('a', 'replacement');
  data.pods[0].metadata.creationTimestamp = new Date(start).toISOString();
  await runtime.refreshInventory();
  await runtime.refreshMetrics();
  assert.equal(runtime.snapshot().pods[0].uid, 'replacement');
  assert.equal(runtime.snapshot().pods[0].metrics.status, 'unavailable');
});

test('sidecars are summed; partial metrics or limits are unavailable', async () => {
  const { data, runtime } = fixture();
  data.pods[0].spec.containers.push(container('sidecar'));
  data.samples[0].containers.push({ name: 'sidecar', usage: { cpu: '2', memory: '4Mi' } });
  await runtime.refreshInventory();
  await runtime.refreshMetrics();
  assert.equal(runtime.snapshot().pods[0].metrics.cpuMillicores, 2125);
  assert.equal(runtime.snapshot().pods[0].metrics.memoryBytes, 100 * 2 ** 20);
  assert.equal(runtime.snapshot().pods[0].resources.memoryLimitBytes, 512 * 2 ** 20);
  delete data.pods[0].spec.containers[1].resources;
  data.samples[0].containers.pop();
  await runtime.refreshInventory();
  await runtime.refreshMetrics();
  assert.equal(runtime.snapshot().pods[0].resources.memoryLimitBytes, null);
  assert.equal(runtime.snapshot().pods[0].metrics.status, 'unavailable');
});

test('pending, terminating and inactive pods remain visible; active wins identical selectors', async () => {
  const { data, runtime } = fixture();
  data.preview = service('blue');
  data.pods[0].metadata.deletionTimestamp = new Date(start).toISOString();
  data.pods[1].status = { phase: 'Pending' };
  await runtime.refreshInventory();
  const [a, b] = runtime.snapshot().pods;
  assert.equal(a.trafficRole, 'active');
  assert.equal(a.terminating, true);
  assert.equal(b.phase, 'Pending');
  assert.equal(b.ready, false);
  assert.equal(b.trafficRole, 'inactive');
});

test('invalid usage does not drop good samples or the inventory', async () => {
  const { data, runtime } = fixture();
  data.samples[0].containers[0].usage.cpu = 'invalid';
  await runtime.refreshInventory();
  await runtime.refreshMetrics();
  assert.equal(runtime.snapshot().pods[0].metrics.status, 'unavailable');
  assert.equal(runtime.snapshot().pods[1].metrics.status, 'fresh');
});

test('namespace and service cannot inject selectors or API paths', () => {
  for (const bad of ['../prod', 'test/pods', 'a,b', 'X']) {
    assert.throws(() => new RuntimeStatus({ namespace: bad, serviceName: 'demo-app-be', read() {} }));
    assert.throws(() => new RuntimeStatus({ namespace: 'test', serviceName: bad, read() {} }));
  }
});

test('Metrics API Duration can include minutes or subsecond units', async () => {
  const { data, runtime } = fixture();
  data.pods[0].metadata.creationTimestamp = new Date(start - 120000).toISOString();
  data.samples[0].window = '1m15.5s';
  data.samples[1].window = '15000ms';
  await runtime.refreshInventory();
  await runtime.refreshMetrics();
  assert.equal(runtime.snapshot().pods[0].metrics.windowSeconds, 75.5);
  assert.equal(runtime.snapshot().pods[1].metrics.windowSeconds, 15);
});

test('same-name replacement while a metric read is in flight cannot receive the old UID sample', async () => {
  const { data, runtime } = fixture();
  await runtime.refreshInventory();
  const originalRead = runtime.read;
  let finish;
  runtime.read = (path, options) => path.startsWith('/apis/metrics') ? new Promise((resolve) => { finish = resolve; }) : originalRead(path, options);
  const pending = runtime.refreshMetrics();
  await runtime.refreshMetrics(); // Duplicate invocation must not launch another request.
  data.pods[0] = pod('a', 'replacement');
  await runtime.refreshInventory();
  finish({ items: data.samples });
  await pending;
  assert.equal(runtime.snapshot().pods[0].metrics.status, 'unavailable');
  assert.equal(runtime.snapshot().pods[1].metrics.status, 'fresh');
});
