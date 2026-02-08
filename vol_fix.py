# --- Python 3.13/3.14 救済パッチ ---
try:
    import audioop
except ImportError:
    import sys
    from audioop_lts import audioop
    sys.modules["audioop"] = audioop
# --------------------------------

from pydub import AudioSegment
import os

AudioSegment.converter = r"C:/ffmpeg/bin/ffmpeg.exe"
AudioSegment.ffprobe = r"C:/ffmpeg/bin/ffprobe.exe"

def normalize_with_report(folder_path, target_dbfs=-20.0):
    """
    フォルダ内のMP3の音量を報告し、一定に揃えて上書きする
    """
    # フォルダが存在するか確認
    if not os.path.exists(folder_path):
        print(f"エラー: フォルダ '{folder_path}' が見つかりません。")
        return

    print(f"--- 音量調整ミッション開始（目標: {target_dbfs} dBFS） ---")

    for filename in os.listdir(folder_path):
        if filename.endswith(".mp3"):
            file_path = os.path.join(folder_path, filename)
            
            # 1. 音声ファイルを読み込む
            song = AudioSegment.from_file(file_path, format="mp3")
            
            # 2. 現在の音量を取得（組み込みポイント！）
            before_dbfs = song.dBFS
            
            # 3. 目標値との差分を計算して調整
            change_in_dbfs = target_dbfs - before_dbfs
            normalized_song = song.apply_gain(change_in_dbfs)
            
            # 4. 上書き保存
            normalized_song.export(file_path, format="mp3")
            
            # 5. 結果を報告
            print(f"【{filename}】")
            print(f"  調整前: {before_dbfs:.2f} dB")
            print(f"  調整後: {normalized_song.dBFS:.2f} dB (差分: {change_in_dbfs:+.2f} dB)")
            print("-" * 30)

    print("--- すべての曲の調整が完了しました！ ---")

# --- 実行セクション ---
# あなたの音楽フォルダのパスに書き換えてください
music_folder = "D:/Music" 
normalize_with_report(music_folder, target_dbfs=-20.0)