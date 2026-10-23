$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }
$uuid = '7lnwdgdqpattc6bhkcij5d9w'

Write-Output '== deployments recientes (endpoint global)'
try {
  $deps = Invoke-RestMethod -Uri "$api/api/v1/deployments" -Headers $h -Method Get
  $deps | Select-Object -First 6 | ForEach-Object {
    "id=$($_.id) uuid=$($_.application_uuid) status=$($_.status) created=$($_.created_at)"
  }
} catch { "global: $($_.Exception.Message)" }

Write-Output '== estado de la app'
$d = Invoke-RestMethod -Uri "$api/api/v1/applications/$uuid" -Headers $h -Method Get
"status=$($d.status) sha=$($d.git_commit_sha) branch=$($d.git_branch)"
"force_build=$($d.force_build) build_pack=$($d.build_pack)"

Write-Output '== re-disparo del deploy'
$body = '{}'
$null = Invoke-RestMethod -Uri "$api/api/v1/deploy?uuid=$uuid&force=true" -Headers $h -Method Post -Body $body -ContentType 'application/json'
Write-Output 'deploy pedido'

Start-Sleep -Seconds 25
$logs = Invoke-RestMethod -Uri "$api/api/v1/applications/$uuid/logs?lines=40" -Headers $h -Method Get
Write-Output '== logs (primeras lineas = lo mas reciente)'
($logs.logs -split "`n") | Where-Object { $_ -match '\S' } | Select-Object -First 25
