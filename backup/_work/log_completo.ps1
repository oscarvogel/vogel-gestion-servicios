$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }
$back = 'ssknzmign82c2uapblj1x8le'
$front = '7lnwdgdqpattc6bhkcij5d9w'

Write-Output '== BACKEND: ultimas lineas (INFO del acceso)'
$logs = Invoke-RestMethod -Uri "$api/api/v1/applications/$back/logs?lines=400" -Headers $h -Method Get
$lineas = $logs.logs -split "`n" | Where-Object { $_ -match '\S' }
Write-Output "total lineas: $($lineas.Count)"
$lineas | Select-Object -Last 25

Write-Output ''
Write-Output '== FRONTEND (nginx): ultimas lineas'
$flogs = Invoke-RestMethod -Uri "$api/api/v1/applications/$front/logs?lines=400" -Headers $h -Method Get
$flineas = $flogs.logs -split "`n" | Where-Object { $_ -match '\S' }
Write-Output "total lineas: $($flineas.Count)"
$flineas | Select-Object -Last 25
