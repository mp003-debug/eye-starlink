param([Parameter(Mandatory=$true)][string]$CatalogPath,
      [Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskOutput = [IO.Path]::GetFullPath($OutputDirectory)
if (-not $taskOutput.StartsWith($taskRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Speech output must stay inside the upgrade workspace'
}
$catalog = Get-Content -LiteralPath $CatalogPath -Raw -Encoding UTF8 | ConvertFrom-Json
$voice = New-Object -ComObject SAPI.SpVoice
$selected = $null
foreach ($token in $voice.GetVoices()) {
    if ($token.GetDescription() -like '*Huihui*') { $selected = $token; break }
}
if ($null -eq $selected) { throw 'Microsoft Huihui Desktop voice is required; no language fallback' }
$voice.Voice = $selected
$voice.Rate = 0
$voice.Volume = 100
[IO.Directory]::CreateDirectory($taskOutput) | Out-Null
foreach ($entry in $catalog) {
    if ($entry.key -notmatch '^(yes|no|please_stop|reposition|toilet|unwell)$') { throw 'Unexpected quick phrase key' }
    $stream = New-Object -ComObject SAPI.SpFileStream
    $stream.Format.Type = 18
    try {
        $stream.Open((Join-Path $taskOutput ($entry.key + '.wav')), 3, $false)
        $voice.AudioOutputStream = $stream
        [void]$voice.Speak([string]$entry.text, 0)
    } finally {
        $stream.Close()
    }
}
$selected.GetDescription()
