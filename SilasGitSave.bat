@echo off
:: 文字化け防止
chcp 65001 > nul
setlocal
echo === SilasRequiemDJ：GitHub保存開始 ===

cd /d %~dp0

echo [1/3] ファイルを準備中...
git add .

:: 日付と時刻を取得（バックアップ用）
set YYYY=%date:~0,4%
set MM=%date:~5,2%
set DD=%date:~8,2%
set HH=%time: =0%
set HH=%HH:~0,2%
set MIN=%time:~3,2%
set default_msg=DJ_Update_%YYYY%%MM%%DD%_%HH%%MIN%

echo.
echo --------------------------------------------------
echo コメントを入力してください（例：新曲追加、設定変更など）
echo ※何も入力せずにEnterを押すと、自動メッセージになります。
set /p user_msg="> "
echo --------------------------------------------------

:: 入力が空だった場合の処理
if "%user_msg%"=="" (
    set final_msg=%default_msg%
) else (
    set final_msg=%user_msg%
)

echo [2/3] 記録を作成中: %final_msg%
git commit -m "%final_msg%"

echo [3/3] GitHubへ送信中...
git push origin main

echo.
echo === 保存が完了しました！今日もナイスプレイ！ ===
pause