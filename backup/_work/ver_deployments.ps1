$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }

$deps = Invoke-RestMethod -Uri "$api/api/v1/deployments" -Headers $h -Method Get
foreach ($d in ($deps | Select-Object -First 6)) {
  Write-Output ("id={0} status={1} app={2} server={3} created={4} finished={5}" -f `
    $d.id, $d.status, $d.application_uuid, $d.server_uuid, $d.created_at, $d.finished_at)
}

Write-Output ''
Write-Output '== detalle de cada uno'
foreach ($id in @($deps | Select-Object -First 4 | ForEach-Object { $_.id })) {
  try {
    $one = Invoke-RestMethod -Uri "$api/api/v1/deployments/$id" -Headers $h -Method Get
    Write-Output ("-- id={0} status={1} app={2} sha={3} branch={4}" -f $one.id, $one.status, $one.application_uuid, $one.git_commit_sha, $one.git_branch)
    Write-Output ("   script: {0}" -f ($one.script | Out-String).Trim())
  } catch {
    Write-Output "-- id=$id : $($_.Exception.Message)"
  }
}
