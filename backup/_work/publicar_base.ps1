$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }
$db = 'diamcot1wyytezyasugd5biv'

# Publicar SOLO para trabajar (se cierra al terminar).
$body = @{ is_public = $true; public_port = 33061 } | ConvertTo-Json
$null = Invoke-RestMethod -Uri "$api/api/v1/databases/$db" -Headers $h -Method Patch -Body $body -ContentType 'application/json'
Write-Output 'puerto pedido; recreando el contenedor de la base...'
$null = Invoke-RestMethod -Uri "$api/api/v1/databases/$db/stop" -Headers $h -Method Post -ContentType 'application/json'
$null = Invoke-RestMethod -Uri "$api/api/v1/deploy?uuid=$db&force=true" -Headers $h -Method Post -ContentType 'application/json'
Start-Sleep -Seconds 45
for ($i = 0; $i -lt 20; $i++) {
  $d = Invoke-RestMethod -Uri "$api/api/v1/databases/$db" -Headers $h -Method Get
  Write-Output ("[{0:HH:mm:ss}] status={1} public_port={2}" -f (Get-Date), $d.status, $d.public_port)
  if ($d.status -match 'running:healthy') { Write-Output 'LISTA'; break }
  Start-Sleep -Seconds 10
}
