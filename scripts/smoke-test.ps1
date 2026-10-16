# Smoke test for the local stack (Windows PowerShell). Run from the project root:
#   powershell -ExecutionPolicy Bypass -File scripts\smoke-test.ps1
$ErrorActionPreference = "Continue"
$env:PATH = "$env:USERPROFILE\.local\ddev;$env:PATH"
$site = "http://allsaints.ddev.site"
$failed = 0
function Check($name, [scriptblock]$test) {
  try { $ok = & $test } catch { $ok = $false }
  if ($ok) { Write-Host "  [ok]   $name" -ForegroundColor Green } else { Write-Host "  [FAIL] $name" -ForegroundColor Red; $script:failed++ }
}
Write-Host "Environment"
Check "DDEV project running"        { (ddev describe -j | ConvertFrom-Json).raw.status -eq "running" }
Check "WordPress reachable"         { (Invoke-WebRequest "$site/" -UseBasicParsing).StatusCode -eq 200 }
Check "WP-CLI works"                { (ddev wp core version) -match "^\d" }
Write-Host "Plugin"
Check "plugin active"               { (ddev wp plugin is-active asc-digital-ministry); $LASTEXITCODE -eq 0 }
Check "Sermon CPT exists"           { (ddev wp post-type get sermon --field=name) -eq "sermon" }
Check "Church Knowledge CPT exists"  { (ddev wp post-type get church_kb --field=name) -eq "church_kb" }
$routes = (Invoke-RestMethod "$site/wp-json/").routes.PSObject.Properties.Name
Check "chat REST route exists"      { $routes -contains "/asc/v1/chat" }
Check "sermon REST support exists"  { ($routes -contains "/wp/v2/sermons") -and ($routes -contains "/asc/v1/sermons/exists") }
Check "sermon archive renders"      { (Invoke-WebRequest "$site/sermons/" -UseBasicParsing).Content -match "asc-sermon-card" }
Check "KB has indexed passages"     { (ddev wp asc kb status) -match "Passages:\s+[1-9]" }
Write-Host "Worker + tests"
Push-Location worker\sermon_flywheel
Check "Python worker imports"       { python -c "import sermon_worker.cli, sermon_worker.pipeline"; $LASTEXITCODE -eq 0 }
Check "Python tests pass"           { python -m pytest -q | Out-Host; $LASTEXITCODE -eq 0 }
Pop-Location
Check "WordPress tests pass"        { ddev wp eval-file wp-content/plugins/asc-digital-ministry/tests/run-tests.php | Out-Host; $LASTEXITCODE -eq 0 }
if ($failed) { Write-Host "`n$failed check(s) failed" -ForegroundColor Red; exit 1 } else { Write-Host "`nAll smoke checks passed" -ForegroundColor Green }
