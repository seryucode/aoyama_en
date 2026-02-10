@echo off
:: ↓ これが文字化けを防ぐ魔法の呪文です
chcp 65001 > nul
setlocal
echo === SilasRequiemDJ：GitHub保存開始 ===

cd /d %~dp0

echo [1/3] ファイルを準備中...
git add .

:: 日付と時刻を取得
set YYYY=%date:~0,4%
set MM=%date:~5,2%
set DD=%date:~8,2%
set HH=%time: =0%
set HH=%HH:~0,2%
set MIN=%time:~3,2%

set commit_msg=DJ_Update_%YYYY%%MM%%DD%_%HH%%MIN%
echo [2/3] 記録を作成中: %commit_msg%
git commit -m "%commit_msg%"

echo [3/3] GitHubへ送信中...
git push origin main

echo.
echo === 保存が完了しました！ ===
pause