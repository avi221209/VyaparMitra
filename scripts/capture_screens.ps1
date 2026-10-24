$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$outDir = "docs/screens"
if (!(Test-Path $outDir)) { New-Item -ItemType Directory -Force -Path $outDir }

$urls = @{
    "01_data_screen.png" = "http://localhost:5173/data";
    "02_plan_screen.png" = "http://localhost:5173/plan";
    "03_dispatch_slip_drawer.png" = "http://localhost:5173/plan?line=PLAN-20261024-1792880580-L0001";
    "04_review_screen.png" = "http://localhost:5173/review";
    "05_evaluate_screen.png" = "http://localhost:5173/evaluate";
    "06_audit_screen.png" = "http://localhost:5173/audit";
    "07_design_system.png" = "http://localhost:5173/design"
}

foreach ($item in $urls.GetEnumerator()) {
    $filename = $item.Key
    $url = $item.Value
    $tempFile = "$env:TEMP\$filename"
    Write-Host "Capturing $filename from $url ..."
    & $edge --headless=new --no-sandbox --window-size=1440,900 --user-data-dir="$env:TEMP\edge_profile_$filename" --screenshot="$tempFile" $url
    Start-Sleep -Milliseconds 1500
    if (Test-Path $tempFile) {
        Copy-Item $tempFile "$outDir\$filename" -Force
        $len = (Get-Item "$outDir\$filename").Length
        Write-Host "Captured $filename ($len bytes)"
    } else {
        Write-Host "Warning: $tempFile not generated"
    }
}
