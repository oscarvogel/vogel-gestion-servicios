$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }

foreach ($uuid in @('ssknzmign82c2uapblj1x8le', '7lnwdgdqpattc6bhkcij5d9w')) {
  $d = Invoke-RestMethod -Uri "$api/api/v1/deployments?uuid=$uuid&perPage=1" -Headers $h -Method Get
  $ult = @($d)[0]
  Write-Output "== uuid=$uuid id=$($ult.id) deployment_id=$($ult.deployment_uuid) status=$($ult.status) commit=$($ult.commit)"
  $id = $ult.id
  try {
    $logs = Invoke-RestMethod -Uri "$api/api/v1/deployments/$id/logs?lines=60" -Headers $h -Method Get
    $texto = ($logs | ForEach-Object { $_.output }) -join "`n"
    ($texto -split "`n") | Select-Object -Last 25
  } catch {
    Write-Output "   (logs no disponibles: $($_.Exception.Message))"
  }
}
