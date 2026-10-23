$ErrorActionPreference = 'Continue'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }
$uuid = '7lnwdgdqpattc6bhkcij5d9w'

$pruebas = @(
  "$api/api/v1/deployments/1655/logs",
  "$api/api/v1/deploy/logs?uuid=$uuid&lines=60",
  "$api/api/v1/applications/$uuid/deploy",
  "$api/api/v1/queue"
)
foreach ($p in $pruebas) {
  try {
    $r = Invoke-RestMethod -Uri $p -Headers $h -Method Get
    Write-Output "== $p -> OK"
    ($r | ConvertTo-Json -Depth 4).Substring(0, [Math]::Min(2500, ($r | ConvertTo-Json -Depth 4).Length))
  } catch {
    Write-Output "== $p -> $($_.Exception.Message)"
  }
  Write-Output ''
}
