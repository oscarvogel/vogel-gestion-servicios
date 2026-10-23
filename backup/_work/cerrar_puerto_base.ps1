$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }
$db = 'diamcot1wyytezyasugd5biv'

Write-Output '== estado de la base antes de cerrar el puerto'
$d = Invoke-RestMethod -Uri "$api/api/v1/databases/$db" -Headers $h -Method Get
"status=$($d.status) is_public=$($d.is_public) public_port=$($d.public_port)"

Write-Output '== se cierra el puerto público'
$body = @{ is_public = $false; public_port = '' } | ConvertTo-Json
$null = Invoke-RestMethod -Uri "$api/api/v1/databases/$db" -Headers $h -Method Patch -Body $body -ContentType 'application/json'

$d2 = Invoke-RestMethod -Uri "$api/api/v1/databases/$db" -Headers $h -Method Get
"is_public=$($d2.is_public) public_port=$($d2.public_port) status=$($d2.status)"
