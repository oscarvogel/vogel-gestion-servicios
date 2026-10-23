$ErrorActionPreference = 'Continue'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }

Write-Output '=== campos de la base ==='
$db = Invoke-RestMethod -Uri "$api/api/v1/databases/diamcot1wyytezyasugd5biv" -Headers $h -Method Get
$db | Get-Member -MemberType NoteProperty | Select-Object -ExpandProperty Name | Sort-Object | ForEach-Object { Write-Output "  $_ = $($db.$_)" }

Write-Output '=== probando endpoints de logs ==='
foreach ($u in @(
  "$api/api/v1/databases/diamcot1wyytezyasugd5biv/logs",
  "$api/api/v1/containers/diamcot1wyytezyasugd5biv/logs",
  "$api/api/v1/applications/ssknzmign82c2uapblj1x8le/logs",
  "$api/api/v1/applications/ssknzmign82c2uapblj1x8le/logs?lines=50"
)) {
  try {
    $r = Invoke-RestMethod -Uri $u -Headers $h -Method Get
    Write-Output "OK $u"
    $txt = ($r | ForEach-Object { if ($_.output) { $_.output } elseif ($_ -is [string]) { $_ } }) -join "`n"
    Write-Output ($txt.Substring(0, [Math]::Min(3000, $txt.Length)))
    break
  } catch {
    Write-Output "FALLA $u -> $($_.Exception.Message)"
  }
}
