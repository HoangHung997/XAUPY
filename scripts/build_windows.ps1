#Requires -Version 7.0
param(
    [string]$Dotnet = 'dotnet',
    [string]$Python = 'python',
    [string]$MetaEditor = 'C:\Program Files\MetaTrader 5\MetaEditor64.exe',
    [string]$Iscc = '',
    [switch]$SkipTests
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
if (-not $IsWindows) { throw 'The Windows release must be built on Windows.' }
if (-not (Test-Path -LiteralPath $MetaEditor -PathType Leaf)) { throw 'MetaEditor is required to compile and verify the Bridge EA.' }
if ($Iscc -and -not (Test-Path -LiteralPath $Iscc -PathType Leaf)) { throw 'The specified Inno Setup compiler does not exist.' }
function Invoke-Checked([string]$File, [string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$File exited with $LASTEXITCODE" }
}
Invoke-Checked $Python @('-c', 'import MetaTrader5; print("MT5 history provider", MetaTrader5.__version__)')
Invoke-Checked $Python @('-m','pip','install','-r','python/requirements-runtime.txt','--disable-pip-version-check')
if (-not $SkipTests) {
    Invoke-Checked $Python @('-m','unittest','discover','-s','python/tests','-q')
    Invoke-Checked $Dotnet @('run','--project','tests/XAUPY.Ipc.ContractTests/XAUPY.Ipc.ContractTests.csproj','-c','Release')
}
$releaseRoot = Join-Path $projectRoot 'dist/XAUPY-win-x64'
$expectedStage = [IO.Path]::GetFullPath((Join-Path $projectRoot 'dist/XAUPY-win-x64'))
$distRoot = Join-Path $projectRoot 'dist'
if ((Test-Path -LiteralPath $distRoot) -and (Get-Item -LiteralPath $distRoot).LinkType) {
    throw 'Refusing to package through a linked dist directory.'
}
if (Test-Path -LiteralPath $releaseRoot) {
    $resolvedStage = (Resolve-Path -LiteralPath $releaseRoot).Path
    if ($resolvedStage -ne $expectedStage -or (Get-Item -LiteralPath $releaseRoot).LinkType) {
        throw 'Refusing to clean an unexpected or linked build directory.'
    }
    Remove-Item -LiteralPath $resolvedStage -Recurse -Force
}
New-Item -ItemType Directory -Force $releaseRoot | Out-Null
foreach ($tool in @(@('engine','engine_entry.py','xaupy-engine'), @('tools','config_entry.py','xaupy-config'))) {
    Invoke-Checked $Python @('-m','PyInstaller','--clean','--noconfirm','--onefile','--name',$tool[2],
        '--paths','python','--collect-data','tzdata','--distpath',"$releaseRoot/$($tool[0])",
        '--workpath',"artifacts/packaging/$($tool[2])",'--specpath',"artifacts/packaging/$($tool[2])","python/$($tool[1])")
}
Invoke-Checked $Dotnet @('publish','src/XAUPY.Desktop/XAUPY.Desktop.csproj','-c','Release','-r','win-x64','--self-contained','true','-o',$releaseRoot)
Invoke-Checked "$releaseRoot/engine/xaupy-engine.exe" @('--history-provider-check')
$profileRoot = Join-Path $releaseRoot 'profiles'
New-Item -ItemType Directory -Force $profileRoot | Out-Null
$configTool = Join-Path $releaseRoot 'tools/xaupy-config.exe'
Invoke-Checked $configTool @('defaults','--out',"$profileRoot/Baseline_M30_M5_M1.json")
Invoke-Checked $configTool @('validate',"$profileRoot/Baseline_M30_M5_M1.json")
Invoke-Checked $configTool @('export-set',"$profileRoot/Baseline_M30_M5_M1.json",'--out',"$profileRoot/Baseline_M30_M5_M1.set")
Invoke-Checked $configTool @('schema','--out',"$profileRoot/config-schema-v1.json")
foreach ($researchProfile in @(Get-ChildItem -LiteralPath 'profiles' -Filter '*.json' -File)) {
    Invoke-Checked $configTool @('validate',$researchProfile.FullName)
    Copy-Item -LiteralPath $researchProfile.FullName -Destination $profileRoot -Force
}
$mtRoot = Join-Path $releaseRoot 'mt5'
New-Item -ItemType Directory -Force $mtRoot | Out-Null
$mq5 = Join-Path $mtRoot 'XAUPY_Bridge_EA.mq5'
$mtLog = Join-Path $mtRoot ('compile-' + [guid]::NewGuid().ToString('N') + '.log')
Copy-Item -LiteralPath 'mql5/XAUPY_Bridge_EA.mq5' -Destination $mq5 -Force
Get-ChildItem -LiteralPath 'mql5' -Filter '*.mqh' -File | Copy-Item -Destination $mtRoot -Force
$editorArguments = @('/portable', ('/compile:"' + $mq5 + '"'), ('/log:"' + $mtLog + '"'))
Start-Process -FilePath $MetaEditor -WindowStyle Hidden -ArgumentList $editorArguments -Wait
if (-not (Test-Path -LiteralPath $mtLog)) { throw 'MetaEditor did not create the compile log.' }
$mtResult = Get-Content -LiteralPath $mtLog -Raw -Encoding Unicode
if ($mtResult -notmatch 'Result:\s*0 errors,\s*0 warnings' -or -not (Test-Path "$mtRoot/XAUPY_Bridge_EA.ex5")) { throw "Bridge compile failed: $mtResult" }
Copy-Item -LiteralPath $mtLog -Destination "$mtRoot/compile.log" -Force
if (-not $SkipTests) {
    foreach ($smoke in @('013_management','012_optimizer','011_backtest','010_journal','009_execution','007_engine')) {
        Invoke-Checked $Python @("scripts/smoke_task$smoke.py","$releaseRoot/engine/xaupy-engine.exe")
    }
    Invoke-Checked $Python @('scripts/smoke_config_exe.py',$configTool)
    Invoke-Checked $Python @('scripts/smoke_task014_015_maintenance.py',"$releaseRoot/engine/xaupy-engine.exe")
    Invoke-Checked $Python @('scripts/smoke_intrabar_engine.py',"$releaseRoot/engine/xaupy-engine.exe")
    Invoke-Checked $Python @('scripts/smoke_demo_once_engine.py',"$releaseRoot/engine/xaupy-engine.exe")
    Invoke-Checked $Python @('scripts/smoke_release_v1.py',"$releaseRoot/engine/xaupy-engine.exe")
    Invoke-Checked $Dotnet @('run','--project',"$projectRoot/tests/XAUPY.Desktop.InteractionTests/XAUPY.Desktop.InteractionTests.csproj",'-c','Release',
        '--','--engine',"$releaseRoot/engine/xaupy-engine.exe")
}
New-Item -ItemType Directory -Force "$releaseRoot/docs" | Out-Null
Get-ChildItem -LiteralPath 'docs' | Copy-Item -Destination "$releaseRoot/docs" -Recurse -Force
Copy-Item -LiteralPath 'README.md' -Destination "$releaseRoot/README.md" -Force
$revision = & git rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $revision -notmatch '^[0-9a-f]{40}$') { throw 'Could not identify the source commit.' }
$isDirty = [bool](& git status --porcelain)
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect source-tree status.' }
$requiredFiles = @('XAUPY.Desktop.exe', 'XAUPY.Desktop.dll', 'XAUPY.Ipc.dll',
    'engine/xaupy-engine.exe', 'tools/xaupy-config.exe',
    'profiles/Baseline_M30_M5_M1.json', 'profiles/Baseline_M30_M5_M1.set', 'profiles/config-schema-v1.json',
    'mt5/XAUPY_Bridge_EA.mq5', 'mt5/XAUPY_Bridge_EA.ex5', 'mt5/compile.log',
    'mt5/XAUPY_DemoOnce.mqh', 'mt5/XAUPY_Execution.mqh', 'mt5/XAUPY_MarketServices.mqh', 'mt5/XAUPY_StrictJson.mqh',
    'docs/TASK014_TOOLS_DIAGNOSTICS_SPEC.md', 'docs/TASK015_SETTINGS_RECOVERY_SPEC.md',
    'docs/TASK016_RELEASE_ACCEPTANCE.md', 'README.md')
foreach ($required in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $releaseRoot $required) -PathType Leaf)) { throw "Release file missing: $required" }
}
if (@(Get-ChildItem -LiteralPath "$releaseRoot/docs/ui-reference" -Filter '*.png' -File).Count -ne 10) { throw 'Release requires all ten approved UI reference images.' }
$manifest = [ordered]@{version='1.0.0-dev'; release_channel='development'; commit=$revision; working_tree_modified=$isDirty; built_at_utc=[DateTime]::UtcNow.ToString('o'); general_execution_capable=$true; execution_default_mode='OFF'; execution_requires_user_account_selection=$true; real_requires_explicit_local_permission=$true; demo_one_shot_capable=$true; demo_one_shot_requires_explicit_arm=$true; tests_executed=(-not [bool]$SkipTests); files=@()}
$manifest.files = @(Get-ChildItem -LiteralPath $releaseRoot -Recurse -File | Where-Object Name -ne 'build-manifest.json' | ForEach-Object {
    @{path=[IO.Path]::GetRelativePath($releaseRoot,$_.FullName).Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
})
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath "$releaseRoot/build-manifest.json" -Encoding utf8
$zipPath = Join-Path $distRoot 'XAUPY-1.0.0-dev-win-x64.zip'
Compress-Archive -Path "$releaseRoot/*" -DestinationPath $zipPath -Force
$archive = [IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    if (-not $archive.GetEntry('build-manifest.json')) { throw 'ZIP has no root build manifest.' }
    foreach ($file in $manifest.files) {
        $entry = $archive.GetEntry($file.path)
        if (-not $entry -or $entry.Length -ne $file.bytes) { throw "ZIP entry missing or truncated: $($file.path)" }
        $stream = $entry.Open()
        $hasher = [Security.Cryptography.SHA256]::Create()
        try { $actualHash = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
        finally { $stream.Dispose(); $hasher.Dispose() }
        if ($actualHash -ne $file.sha256) { throw "ZIP hash mismatch: $($file.path)" }
    }
} finally { $archive.Dispose() }
$artifactPaths = @($zipPath)
if ($Iscc) {
    $installerPath = Join-Path $distRoot 'XAUPY-1.0.0-dev-Setup.exe'
    if (Test-Path -LiteralPath $installerPath) { Remove-Item -LiteralPath $installerPath -Force }
    Invoke-Checked $Iscc @('installer/XAUPY.iss')
    if (-not (Test-Path -LiteralPath $installerPath -PathType Leaf)) { throw 'Inno Setup returned without the required installer.' }
    $artifactPaths += $installerPath
}
$checksums = @($artifactPaths | ForEach-Object { Get-FileHash -LiteralPath $_ -Algorithm SHA256 })
$checksums | ForEach-Object { "$($_.Hash.ToLowerInvariant())  $([IO.Path]::GetFileName($_.Path))" } | Set-Content -LiteralPath (Join-Path $distRoot 'SHA256SUMS.txt') -Encoding utf8
$checksums
