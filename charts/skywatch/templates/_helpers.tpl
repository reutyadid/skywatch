{{/*
Shared names and labels. Each template passes a dict: (dict "root" . "component" "backend").
*/}}

{{/* Prefix for every resource name, e.g. release "skywatch" -> "skywatch-backend". */}}
{{- define "skywatch.fullname" -}}
{{- .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- end -}}

{{/* Labels that pick one component's pods. Used by the Deployment selector and the Service. */}}
{{- define "skywatch.selectorLabels" -}}
app.kubernetes.io/name: {{ .root.Chart.Name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/* Selector labels plus descriptive ones, on every resource. */}}
{{- define "skywatch.labels" -}}
{{ include "skywatch.selectorLabels" . }}
app.kubernetes.io/part-of: skywatch
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
helm.sh/chart: {{ .root.Chart.Name }}-{{ .root.Chart.Version }}
{{- end -}}
