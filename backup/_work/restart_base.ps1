$ErrorActionPreference = 'Continue'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }
$db = 'diamcot1wyytezyasugd5biv'

Write-Output '=== restart ==='
try {
  $null = Invoke-RestMethod -Uri "$api/api/v1/databases/$db/restart" -Headers $h -Method Post -ContentType 'application/json'
  Write-Output 'restart pedido'
} catch { Write-Output "restart fallo: $($_.Exception.Message)" }

for ($i = 0; $i -lt 24; $i++) {
  Start-Sleep -Seconds 10
  $d = Invoke-RestMethod -Uri "$api/api/v1/databases/$db" -Headers $h -Method Get
  Write-Output ("[{0:HH:mm:ss}] status={1}" -f (Get-Date), $d.status)
  if ($d.status -match 'running:healthy') { Write-Output 'BASE LISTA'; break }
  if ($d.status -match 'exited') { Write-Output 'volvio a caer'; break }
}
