$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }
$front = '7lnwdgdqpattc6bhkcij5d9w'

$d = Invoke-RestMethod -Uri "$api/api/v1/applications/$front" -Headers $h -Method Get
$json = $d | ConvertTo-Json -Depth 8
$json | Out-File 'C:\Programacion\vogel-gestion\backup\_work\front_app.json' -Encoding utf8

Write-Output '== lineas con BACKEND / build / env / network'
($json -split "`n") | Where-Object { $_ -match 'BACKEND|build|env|network|alias|docker' } | Select-Object -First 45
