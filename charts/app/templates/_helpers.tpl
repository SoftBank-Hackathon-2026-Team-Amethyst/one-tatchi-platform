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
