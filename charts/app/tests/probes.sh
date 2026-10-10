#!/usr/bin/env bash
# Regression: a DB-dependent readiness path must not force liveness restarts.
set -euo pipefail
chart="$(cd "$(dirname "$0")/.." && pwd)"
python3 - "$chart" <<'PY'
import re
import subprocess
import sys

chart = sys.argv[1]

def render(*values):
    command = ["helm", "template", "probes", chart,
               "--set", "image.repository=r", "--set", "image.tag=t"]
    for value in values:
        command += ["--set", value]
    return subprocess.check_output(command, text=True)

def paths(text):
    return re.findall(r"(?:readiness|liveness)Probe:\s+httpGet:\s+path: (\S+)", text)

baseline = render()
assert paths(baseline) == ["/health", "/health"]
for fallback in ["probe.livenessPath=", "probe.livenessPath=null"]:
    assert render(fallback) == baseline

legacy = render("probe.path=/ready")
assert paths(legacy) == ["/ready", "/ready"]
assert render("probe.path=/ready", "probe.livenessPath=") == legacy

split = render("probe.path=/ready", "probe.livenessPath=/healthz/liveness")
assert paths(split) == ["/ready", "/healthz/liveness"]
# Only the app liveness path may change: delays, port, resources and security stay identical.
expected = re.sub(r"(livenessProbe:\s+httpGet:\s+path: )/ready",
                  r"\g<1>/healthz/liveness", legacy, count=1)
assert split == expected

# FE keeps its own path, including with its metrics sidecar and preview authentication.
fe_values = ["probe.path=/", "metrics.enabled=true", "metrics.port=4040", "metrics.nginxLogExporter.enabled=true",
             "previewAuth.enabled=true", "previewAuth.host=green.example.test",
             "previewAuth.issuerUrl=https://issuer.example.test", "previewAuth.remoteKey=auth"]
fe = render(*fe_values)
assert paths(fe) == ["/ready", "/ping", "/", "/"]
assert render(*fe_values, "probe.livenessPath=") == fe
fe_split = render(*fe_values, "probe.livenessPath=/alive")
expected = re.sub(r"(livenessProbe:\s+httpGet:\s+path: )/\n",
                  r"\g<1>/alive\n", fe, count=1)
assert fe_split == expected  # Sidecar and oauth2-proxy probes are unchanged too.
print("Probe compatibility regression passed")
PY
