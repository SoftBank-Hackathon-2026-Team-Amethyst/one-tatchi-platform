#!/usr/bin/env python3
"""Generate the provisioned dashboard. Keep metrics and evidence in distinct rows."""
import json
from pathlib import Path

PROM = {"type": "prometheus", "uid": "prometheus"}
CW = {"type": "cloudwatch", "uid": "cloudwatch"}
GCP = {"type": "stackdriver", "uid": "cloud-monitoring"}
panels = []
y = 0


def row(title):
    global y
    panels.append({"id": len(panels) + 1, "type": "row", "title": title,
                   "collapsed": False, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}})
    y += 1


def panel(title, targets, unit, x=0, width=8, description="", kind="timeseries", height=8):
    panels.append({"id": len(panels) + 1, "type": kind, "title": title,
                   "description": description,
                   "gridPos": {"x": x, "y": y, "w": width, "h": height},
                   "datasource": {"type": "datasource", "uid": "-- Mixed --"},
                   "targets": [{**t, "refId": chr(65 + i)} for i, t in enumerate(targets)],
                   "fieldConfig": {"defaults": {"unit": unit, "noValue": "데이터 없음",
                       "custom": {"spanNulls": False}}, "overrides": []},
                   "options": {"legend": {"displayMode": "table", "placement": "bottom"},
                               "tooltip": {"mode": "multi"}}})


def prom(expr, legend="{{target}} · {{service}} · {{environment}} · {{cluster}}"):
    return {"datasource": PROM, "expr": expr, "legendFormat": legend}


def gcp(expr):
    # Keep the inactive editor model: Cloud Monitoring's legacy migration
    # otherwise treats a PromQL-only target as an old metric query.
    return {"datasource": GCP, "queryType": "promQL", "hide": "__GCP_HIDE__",
            "timeSeriesList": {},
            "promQLQuery": {"projectName": "${gcp_project}", "expr": expr, "step": "30s"}}


sel = 'target=~"${target:regex}",environment=~"${environment:regex}",cluster=~"$cluster",service=~"$service"'
group = "target,cluster,environment,service"
count = f'sum by ({group}) (rate(app_http_response_count_total{{{sel}}}[$__rate_interval]))'
errors = f'sum by ({group}) (rate(app_http_response_count_total{{{sel},status=~"5.."}}[$__rate_interval]))'
p95 = f'histogram_quantile(0.95, sum by (le,{group}) (rate(app_http_response_time_seconds_hist_bucket{{{sel}}}[$__rate_interval]))) * 1000'


def stat(title, expr, unit, x, steps, description):
    # One tile per deployment target (target · cluster). GCP comes from Cloud Monitoring, the rest from Prometheus.
    panel(title, [prom(expr, "{{target}} · {{cluster}}"), gcp(expr)], unit, x=x, width=8,
          description=description, kind="stat", height=6)
    panels[-1]["options"] = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                             "textMode": "value_and_name", "colorMode": "background", "graphMode": "area",
                             "justifyMode": "auto", "orientation": "auto"}
    panels[-1]["fieldConfig"]["defaults"]["decimals"] = 1
    panels[-1]["fieldConfig"]["defaults"]["thresholds"] = {"mode": "absolute", "steps": [
        {"color": color, "value": value} for value, color in steps]}


# Multi-target view (T39): the same service on aws · gcp · onprem side by side, then the latest deploy per target.
multi = 'target=~"${target:regex}",environment=~"${environment:regex}",cluster=~"$cluster",service=~"$service"'
by_target = "target,cluster"
m_count = f'sum by ({by_target}) (rate(app_http_response_count_total{{{multi}}}[5m]))'
m_errors = f'sum by ({by_target}) (rate(app_http_response_count_total{{{multi},status=~"5.."}}[5m]))'
row("멀티클라우드 · 배포 대상 상태")
# 1 = every app pod scraped, 0 = seen in the last 24h but silent now (device off or link down).
# The 24h fallback keeps a tile for a target that went dark instead of letting it disappear.
up = f'up{{{multi},job="application"}}'
alive = (f'(sum by ({by_target}) ({up}) / count by ({by_target}) ({up})) '
         f'or (max by ({by_target}) (max_over_time({up}[24h])) * 0)')
panel("배포 대상 켜짐 · 꺼짐", [prom(alive, "{{target}} · {{cluster}}"), gcp(alive)], "percentunit", width=24,
      kind="stat", height=4,
      description="배포 대상(target · cluster)마다 앱 파드 지표가 지금 수집되는 비율입니다. 최근 24시간 안에 보였다가 끊긴 대상은 꺼짐으로 남고, 24시간 넘게 끊긴 대상은 보이지 않습니다. GitHub runner 상태와 배포 설정 오류는 여기에 나오지 않습니다.")
panels[-1]["options"] = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                         "textMode": "value_and_name", "colorMode": "background", "graphMode": "none",
                         "justifyMode": "center", "orientation": "vertical"}
panels[-1]["fieldConfig"]["defaults"]["thresholds"] = {"mode": "absolute", "steps": [
    {"color": "red", "value": None}, {"color": "orange", "value": 0.01}, {"color": "green", "value": 0.999}]}
panels[-1]["fieldConfig"]["defaults"]["mappings"] = [
    {"type": "value", "options": {"0": {"text": "꺼짐", "index": 0}}},
    {"type": "range", "options": {"from": 0.01, "to": 0.999, "result": {"text": "일부", "index": 1}}},
    {"type": "range", "options": {"from": 0.999, "to": 1, "result": {"text": "켜짐", "index": 2}}}]
y += 4
stat("대상별 요청 / 초", m_count, "reqps", 0, [(None, "blue")],
     "배포 대상(target · cluster)마다 최근 5분 완료 요청. 선택한 환경 · 서비스를 합산합니다.")
stat("대상별 HTTP 5xx 비율", f'100 * ({m_errors} or ({m_count} * 0)) / ({m_count} > 0)', "percent", 8,
     [(None, "green"), (1, "orange"), (5, "red")], "5xx / 전체 요청. 1% 이상 주황, 5% 이상 빨강. 요청이 없으면 데이터 없음.")
stat("대상별 응답시간 p95",
     f'histogram_quantile(0.95, sum by (le,{by_target}) (rate(app_http_response_time_seconds_hist_bucket{{{multi}}}[5m]))) * 1000',
     "ms", 16, [(None, "green"), (500, "orange"), (1000, "red")], "실제 요청 histogram의 추정 p95. 500ms 이상 주황, 1초 이상 빨강.")
y += 6
latest = ('filter target like /^${target:regex}$/ and environment like /^${environment:regex}$/ '
          'and service like /$service/ and cluster like /$cluster/ '
          '| stats latest(@timestamp) as last_deploy, latest(sha) as sha, latest(decision) as decision, '
          'latest(metrics.error_rate) as error_rate, latest(metrics.p95_ms) as p95_ms, latest(run_url) as run_url '
          'by target, cluster, environment, service | sort target, cluster, environment, service')
panel("대상별 마지막 배포 · 같은 커밋인지 확인", [{"datasource": CW, "queryMode": "Logs", "region": "default",
      "logGroupNames": ["${evidence_log_group}"], "expression": latest}], "none", width=24, kind="table",
      description="대상 · 환경 · 서비스마다 마지막 AI 배포 검사 기록입니다. sha가 같으면 여러 대상에 같은 커밋이 배포됐습니다. 판단 결과가 실제 승격을 뜻하지는 않습니다.")
panels[-1]["options"] = {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}
panels[-1]["fieldConfig"]["overrides"] = [{
    "matcher": {"id": "byName", "options": "run_url"}, "properties": [{
        "id": "links", "value": [{"title": "Actions 실행", "url": "${__value.raw}", "targetBlank": True}]
    }]
}]
y += 8
row("실제 사용자 트래픽 · smoke / kube-probe 제외")
for i, (title, expr, unit, desc) in enumerate([
    ("요청 / 초", count, "reqps", "서비스별 완료 요청. FE와 BE의 값을 합산하지 않습니다."),
    ("HTTP 5xx 비율", f'100 * ({errors} or ({count} * 0)) / ({count} > 0)', "percent", "5xx / 전체 요청. 요청이 없으면 데이터 없음."),
    ("응답시간 p95", p95, "ms", "실제 요청 histogram의 추정 p95. AI smoke의 nearest-rank와 구분합니다."),
]):
    panel(title, [prom(expr), gcp(expr.replace("$__rate_interval", "5m"))], unit, x=i*8, description=desc)
y += 8
row("AWS · 온프레미스 리소스")
base = 'target=~"${target:regex}",cluster=~"$cluster",namespace=~"${environment:regex}"'
identity = f'label_replace(kube_pod_labels{{{base},label_app_kubernetes_io_name=~"$service"}}, "service", "$1", "label_app_kubernetes_io_name", "(.*)")'
join = f'* on(target,cluster,namespace,pod) group_left(service) {identity}'
resource_legend = "{{target}} · {{service}} · {{namespace}} · {{cluster}}"
panel("CPU 사용량", [prom(f'sum by(target,cluster,namespace,service) (rate(container_cpu_usage_seconds_total{{{base}}}[5m]) {join})', resource_legend)], "cores")
panel("메모리 사용량", [prom(f'sum by(target,cluster,namespace,service) (container_memory_working_set_bytes{{{base}}} {join})', resource_legend)], "bytes", x=8)
panel("컨테이너 재시작 · 최근 5분", [prom(f'sum by(target,cluster,namespace,service) (increase(kube_pod_container_status_restarts_total{{{base}}}[5m]) {join})', resource_legend)], "short", x=16)
y += 8
panel("수집 연결 상태", [prom(f'up{{{sel},job="application"}}')], "short", width=12,
      description="1=수집 성공, 0=수집 실패. 원격 수집기가 끊기면 데이터가 비게 됩니다.")
panel("Ready 파드", [prom(f'sum by(target,cluster,namespace,service) (kube_pod_status_ready{{{base},condition="true"}} {join})', resource_legend)], "short", x=12, width=12)
y += 8
row("벤더 원본 지표 · CloudWatch / Cloud Monitoring")
for i, (title, metric, unit) in enumerate([
    ("AWS CPU · Container Insights", "pod_cpu_utilization", "percent"),
    ("AWS 메모리 · Container Insights", "pod_memory_utilization", "percent"),
]):
    panel(title, [{"datasource": CW, "queryMode": "Metrics", "metricQueryType": 0, "metricEditorMode": 1,
                  "region": "default", "expression": f'SEARCH(\'{{ContainerInsights,ClusterName,Namespace,PodName}} MetricName="{metric}" ClusterName="${{cluster_name}}"\', \'Average\', 60)'}], unit, x=i*12, width=12,
          description="AWS 원본 클러스터 지표입니다. 위의 Prometheus 서비스 지표와 별도로 확인합니다.")
y += 8
for i, (title, metric, unit, rate) in enumerate([
    ("GCP 컨테이너 CPU", "kubernetes.io/container/cpu/core_usage_time", "cores", True),
    ("GCP 컨테이너 메모리", "kubernetes.io/container/memory/used_bytes", "bytes", False),
]):
    # service is a textbox containing a regex (default demo-app-.*), not a multi-select.
    expr = '{"' + metric + '",monitored_resource="k8s_container",namespace_name=~"${environment:regex}",cluster_name=~"$cluster",pod_name=~"(${service:raw})-.*",container_name="app"}'
    if rate:
        expr = f'rate({expr}[5m])'
    panel(title, [gcp(f'sum by(cluster_name,namespace_name,pod_name) ({expr})')], unit, x=i*12, width=12)
y += 8
row("AI 배포 검사 · 실행별 원본 근거")
query = ('fields @timestamp, target, environment, service, run_id, run_attempt, sha, '
         'observation.started_at, observation.ended_at, metrics.requests, metrics.failed, '
         'metrics.error_rate, metrics.p95_ms, metrics.pods.ready, metrics.pods.restarts, '
         'metrics.thresholds.max_error_rate, metrics.thresholds.max_p95_ms, decision, reason, run_url, event_id '
         '| filter target like /^${target:regex}$/ and environment like /^${environment:regex}$/ and service like /$service/ '
         'and cluster like /$cluster/ and run_id like /$run/ | sort @timestamp desc | dedup event_id | limit 100')
panel("AI에 전달한 smoke 결과와 판단", [{"datasource": CW, "queryMode": "Logs", "region": "default",
      "logGroupNames": ["${evidence_log_group}"], "expression": query}], "none", width=24, kind="table",
      description="관찰 창별 원본값입니다. smoke 실패는 기대 응답 불일치(연결 실패 포함), p95는 nearest-rank입니다. 판단 결과가 실제 승격을 뜻하지는 않습니다. 실행 링크에서 실행 결과를 확인하세요.")
panels[-1]["options"] = {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}
panels[-1]["fieldConfig"]["overrides"] = [{
    "matcher": {"id": "byName", "options": "run_url"}, "properties": [{
        "id": "links", "value": [{"title": "Actions 실행", "url": "${__value.raw}", "targetBlank": True}]
    }]
}]


def custom(name, label, values):
    return {"name": name, "label": label, "type": "custom", "query": values,
            "multi": True, "includeAll": True, "allValue": ".*",
            "current": {"text": "All", "value": "$__all"}, "options": []}


dashboard = {"uid": "deploy-overview", "title": "Deploy Overview", "schemaVersion": 39,
             "timezone": "browser", "refresh": "30s", "time": {"from": "now-1h", "to": "now"},
             "tags": ["one-tatchi", "T17", "T39"], "panels": panels,
             "templating": {"list": [custom("target", "배포 대상", "aws,onprem,gcp"),
                 custom("environment", "환경", "test,prod"),
                 {"name": "service", "label": "서비스", "type": "textbox", "query": "demo-app-.*", "current": {"value": "demo-app-.*"}},
                 {"name": "cluster", "label": "클러스터", "type": "textbox", "query": ".*", "current": {"value": ".*"}},
                 {"name": "run", "label": "Actions 실행 ID", "type": "textbox", "query": ".*", "current": {"value": ".*"}}]}}
Path(__file__).with_name("aws").joinpath("dashboards/deploy-overview.json.tftpl").write_text(
    json.dumps(dashboard, ensure_ascii=False, indent=2).replace('${target:regex}', '$${target:regex}')
    .replace('${environment:regex}', '$${environment:regex}').replace('${__value.raw}', '$${__value.raw}')
    .replace('${service:raw}', '$${service:raw}')
    .replace('"__GCP_HIDE__"', '${gcp_hidden}') + "\n")
