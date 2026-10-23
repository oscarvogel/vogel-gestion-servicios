$ErrorActionPreference = 'Continue'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }

$r = Invoke-WebRequest -Uri "$api/api/v1/applications/ssknzmign82c2uapblj1x8le/logs?lines=200" -Headers $h -Method Get -UseBasicParsing -TimeoutSec 60
$json = $r.Content | ConvertFrom-Json
$texto = $json.logs
$lineas = $texto -split "`n"
Write-Output "total lineas: $($lineas.Count)"
$lineas | Select-Object -Last 120
