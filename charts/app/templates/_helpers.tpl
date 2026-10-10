{{- define "app.name" -}}
{{- .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- end -}}

{{- define "app.labels" -}}
app.kubernetes.io/name: {{ include "app.name" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "app.selector" -}}
app.kubernetes.io/name: {{ include "app.name" . }}
{{- end -}}

{{- define "app.isBlueGreen" -}}
{{- if eq .Values.deployStrategy "blueGreen" }}true{{ end -}}
{{- end -}}

{{- define "app.validate" -}}
{{- $supported := list "blueGreen" "rolling" -}}
{{- if not (has .Values.deployStrategy $supported) -}}
{{- fail (printf "deployStrategy %q is not supported (supported: %s)" .Values.deployStrategy (join ", " $supported)) -}}
{{- end -}}
{{- $_ := required "image.repository is required" .Values.image.repository -}}
{{- if .Values.image.digest -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" .Values.image.digest) -}}
{{- fail "image.digest must be sha256:<64 lowercase hex characters>" -}}
{{- end -}}
{{- else -}}
{{- $_ = required "image.tag or image.digest is required" .Values.image.tag -}}
{{- end -}}
{{- end -}}

{{- define "app.securityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
runAsNonRoot: true
capabilities:
  drop: ["ALL"]
{{- end -}}

{{/* ALB/Ingress annotations shared by the active and authenticated preview Ingresses. */}}
{{- define "app.ingressAnnotations" -}}
{{- $root := .root -}}
{{- if eq $root.Values.ingress.className "alb" }}
alb.ingress.kubernetes.io/scheme: internet-facing
alb.ingress.kubernetes.io/target-type: ip
alb.ingress.kubernetes.io/group.name: {{ required "ingress.group is required" $root.Values.ingress.group }}
alb.ingress.kubernetes.io/group.order: {{ $root.Values.ingress.order | quote }}
{{- if not $.host }}
alb.ingress.kubernetes.io/listen-ports: {{ printf "[{\"HTTP\": %v}]" 80 | squote }}
{{- else }}
alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}, {"HTTPS": 443}]'
alb.ingress.kubernetes.io/ssl-redirect: "443"
{{- end }}
{{- if $.host }}
alb.ingress.kubernetes.io/ssl-policy: {{ $root.Values.ingress.sslPolicy }}
{{- end }}
alb.ingress.kubernetes.io/healthcheck-path: {{ $.healthcheckPath }}
{{- end }}
{{- with $root.Values.ingress.annotations }}
{{ toYaml . }}
{{- end }}
{{- end -}}
