param(
 [Parameter(Mandatory=$true)][ValidateSet('02','03','04')][string]$Node,
 [Parameter(Mandatory=$true)][ValidatePattern('^COM[0-9]+$')][string]$Port,
 [Parameter(Mandatory=$true)][ValidatePattern('^[a-zA-Z0-9_]+$')][string]$RunName
)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if($root -ne 'D:\Eye_Tracker_Upgrade_Version'){throw 'Upgrade root required'}
$stage=Join-Path $root 'build\receiver_upgrade_20261102'
$identity=Get-Content (Join-Path $stage 'hardware_before.json') -Raw | ConvertFrom-Json
if($identity.nodes.$Node -ne $Port){throw 'Port must match this session verified node identity'}
$record=Get-Content (Join-Path $stage 'result.json') -Raw | ConvertFrom-Json
$artifact=@($record.builds.$Node.artifacts | Where-Object path -eq 'ws63-liteos-app_all.fwpkg')
if($artifact.Count -ne 1){throw 'Expected one reviewed firmware artifact'}
$package=Join-Path $stage ('firmware\'+$Node+'_care_ui_final\ws63-liteos-app_all.fwpkg')
if((Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash.ToLowerInvariant() -ne $artifact[0].sha256){throw 'Firmware hash mismatch'}
$run=Join-Path $stage ('flash\'+$RunName)
if(Test-Path -LiteralPath $run){throw 'Evidence path already exists'}
if(Get-Process BurnTool -ErrorAction SilentlyContinue){throw 'Another BurnTool is running'}
New-Item -ItemType Directory -Path $run -Force | Out-Null
$burnDir=Join-Path $root 'comm\tools\BurnTool'
[IO.File]::WriteAllText((Join-Path $burnDir 'configure\config_chip_type.ini'),"[ChipType]`r`nCurrentChipTypeId=13`r`n",[Text.Encoding]::ASCII)
$burnArgs=@('-console','-chiptype:WS63',('-com:'+$Port.Substring(3)),'-signalbaud:115200','-timeout:300000','-erasemode:0','-forceread:10','-reset',('-bin:'+$package))
$started=(Get-Date).ToString('o')
$proc=Start-Process -FilePath (Join-Path $burnDir 'BurnTool.exe') -ArgumentList $burnArgs -WorkingDirectory $burnDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $run 'stdout.txt') -RedirectStandardError (Join-Path $run 'stderr.txt') -PassThru
$null=$proc.Handle
Write-Output ('WAIT_RESET node='+$Node+' port='+$Port+' pid='+$proc.Id)
$proc.WaitForExit()
$text=Get-Content (Join-Path $run 'stdout.txt') -Raw
$success=($proc.ExitCode -eq 0 -and $text.Contains('All images burn successfully'))
$result=@{node=$Node;port=$Port;started=$started;ended=(Get-Date).ToString('o');exit_code=$proc.ExitCode;passed=$success;sha256=$artifact[0].sha256;firmware=$package;arguments=$burnArgs;output_mode='direct files, no PowerShell stdout pipeline';boot_verified=$false}
$result | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $run 'result.json') -Encoding utf8
Write-Output ($result | ConvertTo-Json -Compress -Depth 5)
if(-not $success){exit 1}
