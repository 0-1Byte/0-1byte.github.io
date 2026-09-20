param(
    [Parameter(Mandatory = $true)]
    [string]$Artist,

    [Parameter(Mandatory = $true)]
    [string]$Title,

    [string]$Country = "US",

    [switch]$NoCover
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# 从脚本所在位置推导 Hugo 根目录：<repo>\scripts\add-song.ps1
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$musicDir = Join-Path $repoRoot "static\music"
$assetsDir = Join-Path $musicDir "assets"
$jsonPath = Join-Path $musicDir "songs.json"

if (-not (Test-Path $musicDir)) {
    throw "找不到 Hugo 音乐目录：$musicDir"
}

if (-not (Test-Path $assetsDir)) {
    New-Item -ItemType Directory -Path $assetsDir -Force | Out-Null
}

function Write-Utf8NoBom {
    param([string]$Path, [string]$Content)
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Normalize-Text {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return "" }

    $normalized = $Value.ToLowerInvariant()
    return ($normalized -replace '[^\p{L}\p{Nd}]', '')
}

function Sanitize-FileName {
    param([string]$Value)

    $invalid = [IO.Path]::GetInvalidFileNameChars()
    $result = $Value

    foreach ($char in $invalid) {
        $result = $result.Replace([string]$char, "_")
    }

    return (($result -replace '\s+', ' ').Trim())
}

function Get-Year {
    param([string]$DateString)

    if ([string]::IsNullOrWhiteSpace($DateString)) { return $null }

    if ($DateString -match '^(\d{4})') {
        return [int]$Matches[1]
    }

    return $null
}

function Read-SongsJson {
    if (-not (Test-Path $jsonPath)) {
        return @()
    }

    $raw = Get-Content -Path $jsonPath -Raw -Encoding UTF8

    if ([string]::IsNullOrWhiteSpace($raw)) {
        return @()
    }

    $parsed = $raw | ConvertFrom-Json

    # 兼容 Windows PowerShell 5.1 在某些情况下对顶层 JSON 数组的包装形式。
    if ($null -eq $parsed) {
        return @()
    }

    if ($parsed -is [System.Array]) {
        return @($parsed)
    }

    $propertyNames = @($parsed.PSObject.Properties.Name)

    if ($propertyNames -contains "value" -and $propertyNames -contains "Count") {
        if ($null -ne $parsed.value) {
            return @($parsed.value)
        }
    }

    # 正常的单个歌曲对象也兼容。
    if ($propertyNames -contains "title") {
        return @($parsed)
    }

    throw "songs.json 格式无法识别。请检查是否为 JSON 数组，例如：[ { ... }, { ... } ]"
}

function Write-SongsJson {
    param([object[]]$Songs)

    # 每个歌曲对象单独转 JSON，再手动拼成数组。
    # 这样在 Windows PowerShell 5.1 中即使只有 1 首歌，也不会丢掉 []。
    $items = @(
        foreach ($song in $Songs) {
            $song | ConvertTo-Json -Depth 10 -Compress
        }
    )

    $jsonText = "[`r`n" + ($items -join ",`r`n") + "`r`n]"

    Write-Utf8NoBom -Path $jsonPath -Content $jsonText
}

# 1. 搜索歌曲
$term = [uri]::EscapeDataString("$Artist $Title")
$url = "https://itunes.apple.com/search?term=$term&media=music&entity=song&limit=10&country=$Country"

Write-Host ""
Write-Host "正在搜索：" -NoNewline
Write-Host " $Artist - $Title" -ForegroundColor Cyan
Write-Host ""

$response = Invoke-RestMethod -Uri $url -Method Get -Headers @{
    "User-Agent" = "Chen-Music-Library/1.0"
}

$results = @(
    $response.results |
    Where-Object {
        $_.kind -eq "song" -and $_.trackName -and $_.artistName
    }
)

if ($results.Count -eq 0) {
    throw "没有找到结果。可以换一个更接近商店名称的歌名，或者尝试：-Country CN / JP / US"
}

# 2. 选择正确版本
Write-Host "找到 $($results.Count) 个候选："
Write-Host ""

for ($i = 0; $i -lt $results.Count; $i++) {
    $item = $results[$i]
    $year = Get-Year $item.releaseDate

    Write-Host ("[{0}] {1}" -f ($i + 1), $item.trackName)
    Write-Host ("    {0}  ·  {1}" -f $item.artistName, $(if ($item.collectionName) { $item.collectionName } else { "Single" })) -ForegroundColor DarkGray

    if ($item.primaryGenreName -or $year) {
        $genre = if ($item.primaryGenreName) { $item.primaryGenreName } else { "" }
        $separator = if ($item.primaryGenreName -and $year) { "  ·  " } else { "" }
        $yearText = if ($year) { $year } else { "" }

        Write-Host ("    {0}{1}{2}" -f $genre, $separator, $yearText) -ForegroundColor DarkGray
    }

    Write-Host ""
}

do {
    $selection = Read-Host "选择一个结果 [1-$($results.Count)]"
    $selectedNumber = 0
    $valid = [int]::TryParse($selection, [ref]$selectedNumber)
} while (-not $valid -or $selectedNumber -lt 1 -or $selectedNumber -gt $results.Count)

$selected = $results[$selectedNumber - 1]

# 3. 读取已有歌曲
$songs = @(Read-SongsJson)

$artistKey = Normalize-Text $selected.artistName
$titleKey = Normalize-Text $selected.trackName

$duplicate = $songs |
    Where-Object {
        (Normalize-Text $_.artist) -eq $artistKey -and
        (Normalize-Text $_.title) -eq $titleKey
    } |
    Select-Object -First 1

if ($duplicate) {
    Write-Host ""
    Write-Host "这首歌已经存在：" -ForegroundColor Yellow
    Write-Host ("  {0} - {1}" -f $duplicate.artist, $duplicate.title)

    $answer = Read-Host "是否跳过？[Y/n]"

    if ([string]::IsNullOrWhiteSpace($answer) -or $answer -match '^[Yy]$') {
        Write-Host "已跳过，没有修改。" -ForegroundColor Green
        exit 0
    }

    $songs = @(
        $songs | Where-Object {
            -not (
                (Normalize-Text $_.artist) -eq $artistKey -and
                (Normalize-Text $_.title) -eq $titleKey
            )
        }
    )
}

# 4. 下载封面
$baseName = Sanitize-FileName ("{0} - {1}" -f $selected.artistName, $selected.trackName)
$coverFileName = "$baseName.jpg"
$coverPath = Join-Path $assetsDir $coverFileName

if (-not $NoCover -and $selected.artworkUrl100) {
    $coverUrl = [string]$selected.artworkUrl100
    $largeUrl = $coverUrl -replace '\d+x\d+', '600x600'

    try {
        Invoke-WebRequest `
            -Uri $largeUrl `
            -OutFile $coverPath `
            -Headers @{ "User-Agent" = "Chen-Music-Library/1.0" } `
            -UseBasicParsing
    }
    catch {
        Invoke-WebRequest `
            -Uri $coverUrl `
            -OutFile $coverPath `
            -Headers @{ "User-Agent" = "Chen-Music-Library/1.0" } `
            -UseBasicParsing
    }
}

# 5. 创建歌曲记录
$record = [ordered]@{
    id     = ((Normalize-Text $selected.artistName) + "-" + (Normalize-Text $selected.trackName))
    title  = [string]$selected.trackName
    artist = [string]$selected.artistName
    cover  = "/music/assets/$([uri]::EscapeDataString($coverFileName))"
}

if ($selected.collectionName) {
    $record.album = [string]$selected.collectionName
}

$year = Get-Year $selected.releaseDate
if ($year) {
    $record.year = $year
}

if ($selected.primaryGenreName) {
    $record.tags = @([string]$selected.primaryGenreName)
}

if ($selected.trackViewUrl) {
    $record.url = [string]$selected.trackViewUrl
}

# 6. 追加并写回
$songs = @($songs) + $record
Write-SongsJson -Songs $songs

Write-Host ""
Write-Host "✓ 添加完成" -ForegroundColor Green
Write-Host ("  歌曲：{0} - {1}" -f $record.artist, $record.title)
Write-Host ("  封面：{0}" -f $coverFileName)
Write-Host ("  当前歌曲数：{0}" -f $songs.Count)
Write-Host ("  数据：static/music/songs.json")
Write-Host ""
Write-Host "下一步："
Write-Host "  hugo server"
Write-Host "  http://localhost:1313/music/"
