$conns = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
$pids = @()
foreach ($c in $conns) {
    if ($pids -notcontains $c.OwningProcess) {
        $pids += $c.OwningProcess
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "Killed PID $($c.OwningProcess)"
    }
}
Start-Sleep -Seconds 2
$check = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($check) { Write-Host "Still in use" } else { Write-Host "Port free" }
