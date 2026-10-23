$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }
$front = '7lnwdgdqpattc6bhkcij5d9w'

$logs = Invoke-RestMethod -Uri "$api/api/v1/applications/$front/logs?lines=200" -Headers $h -Method Get
$lineas = $logs.logs -split "`n" | Where-Object { $_ -match '\S' }
Write-Output '== las 60 lineas mas recientes:'
$lineas | Select-Object -First 60
