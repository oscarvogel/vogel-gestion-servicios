$ErrorActionPreference = 'Continue'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }
$db = 'diamcot1wyytezyasugd5biv'

$deps = Invoke-RestMethod -Uri "$api/api/v1/deployments?uuid=$db&perPage=3" -Headers $h -Method Get
foreach ($d in @($deps)) { Write-Output "deploy id=$($d.id) uuid=$($d.deployment_uuid) status=$($d.status)" }

$ids = @($deps | ForEach-Object { $_.id })
$ids += @($deps | ForEach-Object { $_.deployment_uuid })

$candidatas = @(
  "$api/api/v1/databases/$db/logs?lines=80",
  "$api/api/v1/databases/$db/logs?lines=80&type=container",
  "$api/api/v1/applications/$db/logs?lines=80"
)
foreach ($id in $ids) { $candidatas += "$api/api/v1/deployments/$id/logs?lines=80" }

foreach ($u in $candidatas) {
  try {
    $r = Invoke-WebRequest -Uri $u -Headers $h -Method Get -UseBasicParsing -TimeoutSec 60
    Write-Output "=== OK $u (len $($r.RawContentLength)) ==="
    $c = $r.Content
    Write-Output $c.Substring(0, [Math]::Min(4000, $c.Length))
    break
  } catch {
    Write-Output "FALLA $u -> $($_.Exception.Message)"
  }
}
