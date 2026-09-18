{{/*
Use the validated application name for application identity.
*/}}
{{- define "kube-app.name" -}}
{{- .Values.name }}
{{- end }}

{{/*
Resource names follow application intent, independently of the Helm release.
*/}}
{{- define "kube-app.fullname" -}}
{{- include "kube-app.name" . }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "kube-app.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "kube-app.labels" -}}
helm.sh/chart: {{ include "kube-app.chart" . }}
{{ include "kube-app.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "kube-app.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kube-app.name" . }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "kube-app.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "kube-app.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
