$ErrorActionPreference = 'Continue'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }
$front = '7lnwdgdqpattc6bhkcij5d9w'

$deps = Invoke-RestMethod -Uri "$api/api/v1/deployments" -Headers $h -Method Get
Write-Output '== un deployment completo (el primero)'
($deps | Select-Object -First 1) | ConvertTo-Json -Depth 5

Write-Output ''
Write-Output '== probando endpoints de cancelacion / cola'
$candidatos = @(
  "$api/api/v1/deployments/1655/cancel",
  "$api/api/v1/deploy/cancel",
  "$api/api/v1/applications/$front/cancel",
  "$api/api/v1/deployments/cancel"
)
foreach ($c in $candidatos) {
  foreach ($m in @('Post', 'Get')) {
    try {
      $r = Invoke-RestMethod -Uri $c -Headers $h -Method $m -Body '{}' -ContentType 'application/json'
      Write-Output "OK $m $c -> $($r | ConvertTo-Json -Compress -Depth 3)"
    } catch {
      $msg = $_.Exception.Message
      if ($msg -notmatch '404') { Write-Output "$m $c -> $msg" }
    }
  }
}
