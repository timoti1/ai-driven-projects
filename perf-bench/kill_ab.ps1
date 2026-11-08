$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*ab.py*' }
if (-not $procs) { Write-Output "no ab.py process found"; exit 0 }
foreach ($p in $procs) {
    Write-Output ("killing PID " + $p.ProcessId)
    Stop-Process -Id $p.ProcessId -Force
}
