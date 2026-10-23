$ErrorActionPreference = 'Continue'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }

$r = Invoke-WebRequest -Uri "$api/api/v1/applications/ssknzmign82c2uapblj1x8le/logs?lines=2000" -Headers $h -Method Get -UseBasicParsing -TimeoutSec 90
$texto = ($r.Content | ConvertFrom-Json).logs
$lineas = $texto -split "`n"
Write-Output '--- inicio del log (commit / rama) ---'
$lineas | Select-Object -First 25
Write-Output '--- lineas con commit/branch/checkout ---'
$lineas | Where-Object { $_ -match 'commit|branch|checkout|Checking out|Cloning|HEAD is now' } | Select-Object -First 12
