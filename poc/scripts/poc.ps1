# ERPNext 中文轻制造 POC — 本机运维脚本（PowerShell）
# 用法： .\poc.ps1 <命令>
#   start / stop / restart / status / logs / shell
#   backup / restore / bench "<bench 命令>" / copysrc
#
# 所有资源均以 poc- 前缀命名，端口只绑定 127.0.0.1，
# 与 D:\ERP 下 ai-erp / openclaw 等既有项目完全隔离。

param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "restart", "status", "logs", "shell",
                 "backup", "restore", "bench", "copysrc", "help")]
    [string]$Action = "help",

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"

$RUNTIME_DIR = "D:\ERP\poc\frappe_docker"
$COMPOSE     = Join-Path $RUNTIME_DIR "docker-compose.yml"
$BACKUP_DIR  = "D:\ERP\poc\backup"
$SHARE_DIR   = "D:\ERP\poc\share"
$SITE        = "erpnext-poc.localhost"
$CONTAINER   = "poc-frappe"
$BENCH_DIR   = "/workspace/development/frappe-bench"
$URL         = "http://erpnext-poc.localhost:18000"

function Invoke-Compose {
    param([string[]]$Args)
    Push-Location $RUNTIME_DIR
    try { & docker compose @Args } finally { Pop-Location }
}

function Show-Help {
    Write-Host @"
可用命令：
  .\poc.ps1 start            启动 POC 全部容器 + 启动 bench web/worker/schedule
  .\poc.ps1 stop             停止 bench 进程与容器（数据保留在 volume）
  .\poc.ps1 restart          重启
  .\poc.ps1 status           查看容器状态与站点可达性
  .\poc.ps1 logs [服务]      查看日志（默认 frappe）
  .\poc.ps1 shell            进入 frappe 容器 bash（frappe 用户，位于 bench 目录）
  .\poc.ps1 bench "<命令>"   在容器内执行 bench 命令，例：.\poc.ps1 bench "version"
  .\poc.ps1 backup           备份站点（数据库 + 文件）到 $BACKUP_DIR
  .\poc.ps1 restore          从 $BACKUP_DIR 最新备份恢复
  .\poc.ps1 copysrc          把容器内自定义 app 源码同步回 D:\ERP\poc\share\apps

访问地址：$URL
"@
}

switch ($Action) {
    "start" {
        Invoke-Compose @("up", "-d")
        Start-Sleep -Seconds 8
        & $MyInvocation.MyCommand.Path bench "start-bench-services"
        Write-Host "ERPNext 启动完成，浏览器打开 $URL"
    }
    "stop" {
        try { & $MyInvocation.MyCommand.Path bench "stop-bench-services" } catch { }
        Invoke-Compose @("down")
    }
    "restart" {
        & $MyInvocation.MyCommand.Path stop
        & $MyInvocation.MyCommand.Path start
    }
    "status" {
        Invoke-Compose @("ps")
        try {
            $r = Invoke-WebRequest -Uri $URL -UseBasicParsing -TimeoutSec 15
            Write-Host "站点 $URL -> HTTP $($r.StatusCode)"
        } catch {
            Write-Host "站点 $URL 暂不可达：$($_.Exception.Message)"
        }
        & $MyInvocation.MyCommand.Path bench "version"
    }
    "logs" {
        $svc = if ($Rest) { $Rest[0] } else { "frappe" }
        Invoke-Compose @("logs", "--tail=100", "-f", $svc)
    }
    "shell" {
        & docker exec -it $CONTAINER bash -lc "cd $BENCH_DIR && exec bash"
    }
    "bench" {
        $cmd = ($Rest -join " ")
        & docker exec $CONTAINER bash -lc "cd $BENCH_DIR && $cmd"
    }
    "backup" {
        if (-not (Test-Path $BACKUP_DIR)) { New-Item -ItemType Directory -Path $BACKUP_DIR | Out-Null }
        $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $target = "/hostshare/backup-$stamp"
        Write-Host "备份到 $BACKUP_DIR\backup-$stamp ..."
        & docker exec $CONTAINER bash -lc "cd $BENCH_DIR && bench --site $SITE backup --with-files --backup-path $target"
        Write-Host "完成：$BACKUP_DIR\backup-$stamp"
    }
    "restore" {
        $latest = Get-ChildItem $BACKUP_DIR -Directory | Sort-Object Name | Select-Object -Last 1
        if (-not $latest) { throw "没有找到备份" }
        $sql = Get-ChildItem (Join-Path $latest.FullName "*-database.sql.gz") | Select-Object -First 1
        Write-Host "恢复 $($latest.Name) ..."
        & docker exec $CONTAINER bash -lc "cd $BENCH_DIR && bench --site $SITE restore /hostshare/$($latest.Name)/$($sql.Name)"
    }
    "copysrc" {
        $dest = Join-Path $SHARE_DIR "apps"
        if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }
        & docker cp "${CONTAINER}:${BENCH_DIR}/apps/." $dest
        Write-Host "已导出到 $dest"
    }
    default { Show-Help }
}
