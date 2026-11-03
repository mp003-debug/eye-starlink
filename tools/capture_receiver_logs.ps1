param(
 [Parameter(Mandatory=$true)][ValidatePattern('^[a-zA-Z0-9_]+$')][string]$RunName,
 [Parameter(Mandatory=$true)][string]$Ports,
 [ValidateRange(10,3600)][int]$Seconds=1800
)
$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if($taskRoot -ne 'D:\Eye_Tracker_Upgrade_Version'){throw 'Upgrade root required'}
$stage=Join-Path $taskRoot ('build\receiver_upgrade_20261102\serial\'+$RunName)
$portNames=@($Ports.Split(','))
if($portNames.Count -lt 1 -or $portNames.Count -gt 4 -or @($portNames|Select-Object -Unique).Count -ne $portNames.Count){throw 'One to four distinct ports required'}
foreach($name in $portNames){if($name -notmatch '^COM[0-9]+$'){throw 'Invalid port name'}}
if(Test-Path -LiteralPath $stage){throw 'Evidence directory already exists'}
New-Item -ItemType Directory -Path $stage -Force | Out-Null
$items=@();$timer=[Diagnostics.Stopwatch]::StartNew();$started=(Get-Date).ToString('o')
$captureError=$null;$chunks=$null
try {
 foreach($name in $portNames){
  $p=[IO.Ports.SerialPort]::new($name,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
  $item=@{name=$name;port=$p;stream=$null;bytes=0L};$items+=$item
  $p.DtrEnable=$false;$p.RtsEnable=$false;$p.Handshake=[IO.Ports.Handshake]::None;$p.ReadTimeout=100
  $p.Open()
  $item.stream=[IO.File]::Open((Join-Path $stage ($name+'.bin')),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::ReadWrite)
 }
 $chunks=[IO.StreamWriter]::new((Join-Path $stage 'chunks.jsonl'),$false,[Text.UTF8Encoding]::new($false))
 Write-Output ('OPEN '+$Ports+'; 115200 8N1 read-only, DTR/RTS false; identities not inferred from COM number.')
 $buffer=[byte[]]::new(16384)
 while($timer.Elapsed.TotalSeconds -lt $Seconds -and -not(Test-Path -LiteralPath (Join-Path $stage 'stop'))){
  foreach($i in $items){
   $count=$i.port.BytesToRead
   if($count -gt 0){
    $n=$i.port.Read($buffer,0,[Math]::Min($count,$buffer.Length))
    if($i.bytes+$n -gt 16777216){throw 'Per-port capture limit reached'}
    $i.stream.Write($buffer,0,$n);$i.stream.Flush()
    $chunks.WriteLine((@{port=$i.name;seconds=$timer.Elapsed.TotalSeconds;offset=$i.bytes;length=$n}|ConvertTo-Json -Compress));$chunks.Flush();$i.bytes+=$n
   }
  }
  Start-Sleep -Milliseconds 15
 }
} catch {$captureError=$_.Exception.Message;Write-Output "CAPTURE ERROR $captureError"}
finally {
 if($chunks){$chunks.Dispose()}
 foreach($i in $items){if($i.stream){$i.stream.Dispose()};$i.port.Close();$i.port.Dispose()}
 $timer.Stop()
 $meta=@{started=$started;seconds=$timer.Elapsed.TotalSeconds;read_only=$true;closed=$true;error=$captureError;ports=@($items|ForEach-Object {@{name=$_.name;bytes=$_.bytes}})}
 $meta|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $stage 'result.json') -Encoding utf8
 $meta|ConvertTo-Json -Depth 5
}
if($captureError){exit 1}

