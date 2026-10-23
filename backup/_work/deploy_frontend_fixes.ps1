$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }

# Solo el frontend cambio en este commit (WorkOrdersView.vue + test + bitacora).
$uuid = '7lnwdgdqpattc6bhkcij5d9w'

$current = Invoke-RestMethod -Uri "$api/api/v1/applications/$uuid" -Headers $h -Method Get
Write-Output "== antes: branch=$($current.git_branch) sha=$($current.git_commit_sha) status=$($current.status)"

$body = @{ git_branch = 'feature/cyberbrain-migracion'; git_commit_sha = 'HEAD' } | ConvertTo-Json
$null = Invoke-RestMethod -Uri "$api/api/v1/applications/$uuid" -Headers $h -Method Patch -Body $body -ContentType 'application/json'
Write-Output "== branch y commit actualizados"

$null = Invoke-RestMethod -Uri "$api/api/v1/deploy?uuid=$uuid&force=true" -Headers $h -Method Post -ContentType 'application/json'
Write-Output "== deploy pedido"
