$ErrorActionPreference = 'Continue'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }

$r = Invoke-WebRequest -Uri "$api/api/v1/applications/ssknzmign82c2uapblj1x8le/logs?lines=400" -Headers $h -Method Get -UseBasicParsing -TimeoutSec 60
$texto = ($r.Content | ConvertFrom-Json).logs
$lineas = $texto -split "`n"
Write-Output '--- requests (INFO) ---'
$lineas | Where-Object { $_ -match '"(GET|POST|PATCH|DELETE) ' } | Select-Object -Last 25
Write-Output '--- ultimos errores ---'
$lineas | Where-Object { $_ -match 'Error|error|Traceback|Exception' } | Select-Object -Last 8
