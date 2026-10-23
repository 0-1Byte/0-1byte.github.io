$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$port = 48731
$prefix = "http://127.0.0.1:$port/"

$listener = [System.Net.HttpListener]::new()
$listener.Prefixes.Add($prefix)
try {
    $listener.Start()
} catch {
    Write-Host "无法启动本地预览服务：$($_.Exception.Message)" -ForegroundColor Red
    Write-Host '请关闭占用端口的程序后重试。管理器不会修改或终止其他进程。'
    Read-Host '按 Enter 退出'
    exit 1
}

$null = Start-Process $prefix
Write-Host "Read 文章管理器仅在本机运行：$prefix"
Write-Host '关闭此窗口即可停止本地服务。按 Ctrl+C 停止。'

$allowed = @{
    '/' = @{ File = 'index.html'; Type = 'text/html; charset=utf-8' }
    '/index.html' = @{ File = 'index.html'; Type = 'text/html; charset=utf-8' }
    '/core.js' = @{ File = 'core.js'; Type = 'text/javascript; charset=utf-8' }
    '/manager.js' = @{ File = 'manager.js'; Type = 'text/javascript; charset=utf-8' }
}

try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        try {
            $request = $context.Request
            $response = $context.Response
            $response.Headers['X-Content-Type-Options'] = 'nosniff'
            $response.Headers['Cache-Control'] = 'no-store'
            if ($request.HttpMethod -notin @('GET', 'HEAD')) {
                $response.StatusCode = 405
                $response.Close()
                continue
            }
            $path = [Uri]::UnescapeDataString($request.Url.AbsolutePath)
            if (-not $allowed.ContainsKey($path)) {
                $response.StatusCode = 404
                $response.Close()
                continue
            }
            $file = Join-Path $root $allowed[$path].File
            $bytes = [System.IO.File]::ReadAllBytes($file)
            $response.ContentType = $allowed[$path].Type
            $response.ContentLength64 = $bytes.Length
            if ($request.HttpMethod -eq 'GET') {
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
        } catch {
            try {
                $context.Response.StatusCode = 500
                $context.Response.Close()
            } catch {}
            Write-Host "请求处理失败：$($_.Exception.Message)" -ForegroundColor Red
        }
    }
} finally {
    $listener.Stop()
    $listener.Close()
}
