$ErrorActionPreference = 'Continue'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }

$r = Invoke-WebRequest -Uri "$api/api/v1/databases/diamcot1wyytezyasugd5biv/logs?lines=400" -Headers $h -Method Get -UseBasicParsing -TimeoutSec 60
$texto = ($r.Content | ConvertFrom-Json).logs
$lineas = $texto -split "`n"
Write-Output "lineas: $($lineas.Count)"
Write-Output '--- ultimas 45 ---'
$lineas | Select-Object -Last 45
Write-Output '--- errores/shutdown ---'
$lineas | Where-Object { $_ -match 'ERROR|Error|error|Shutdown|shutdown|abort|Abort|Killed|exit|mysqld_safe|SIGTERM|Permission' } | Select-Object -Last 30
