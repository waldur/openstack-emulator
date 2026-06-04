{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "openstack-emulator.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Fully qualified app name. Truncated at 63 chars for DNS-1123 compliance.
*/}}
{{- define "openstack-emulator.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Chart name + version label.
*/}}
{{- define "openstack-emulator.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels.
*/}}
{{- define "openstack-emulator.labels" -}}
helm.sh/chart: {{ include "openstack-emulator.chart" . }}
{{ include "openstack-emulator.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels (stable across upgrades).
*/}}
{{- define "openstack-emulator.selectorLabels" -}}
app.kubernetes.io/name: {{ include "openstack-emulator.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Resolve the image tag, defaulting to .Chart.AppVersion when empty.
*/}}
{{- define "openstack-emulator.imageTag" -}}
{{- default .Chart.AppVersion .Values.image.tag -}}
{{- end -}}

{{/*
The directory portion of persistence.path, used as the PVC volumeMount.mountPath.
e.g. "/data/emulator-db.json" -> "/data".
*/}}
{{- define "openstack-emulator.persistence.dir" -}}
{{- $parts := splitList "/" .Values.persistence.path -}}
{{- $dropLast := slice $parts 0 (sub (len $parts) 1) -}}
{{- $dir := join "/" $dropLast -}}
{{- if eq $dir "" -}}/{{- else -}}{{ $dir }}{{- end -}}
{{- end -}}
