import os
import time
import random
import glob
import re
import csv
import pygame
import pytchat
import asyncio
import edge_tts
import shutil
from datetime import datetime, timezone, timedelta
from google import genai

# ==========================================
# 1. 基本設定エリア
# ==========================================
api_key = os.environ.get("GEMINI_API_KEY")

# --- 選曲モード設定 ---
RANDOM_MODE = False # Trueでランダム選曲    
UTC_OFFSET = 9 # JSTなら9 ESTなら-5      
BOOST_2 = 3.0 # play_flagに2をつけた場合の重み
# --------------------

# --- YouTube設定 ----
USE_YOUTUBE = True         # True（配信用）ならYouTube、Falseならcomment.txtを使用
VIDEO_ID = "KnTxV_s8l5g"     # YouTubeの動画ID（URLの最後にある英数字）ダブルクォーテーションで囲むこと
comment_buffer = []      # YouTube用バッファ
# --------------------

MUSIC_FOLDER = r"D:/Music"  # 音楽ファイルのフォルダ
CSV_PATH = "musicdata.csv"  # 音楽データのCSVファイル
MODEL_NAME = 'gemini-2.5-flash' # LLMのモデル名（2026年2月現在'gemini-2.5-flash'は存在する）
VOICE_NAME = "en-US-ChristopherNeural"

if api_key:
    client = genai.Client(api_key=api_key)
else:
    print("【Error】APIキーが設定されていません。")
    exit()

# --- 安定性のための定数 ---
MAX_RETRIES = 3     # 最大リトライ回数
RETRY_DELAY = 2.0   # リトライ待機時間（秒）
TIMEOUT_SEC = 15.0  # API待機上限（秒）
DEFAULT_SCRIPT = "The stars are always there. Let the music speak for its essence."     #AIスクリプト生成失敗時のデフォルトスクリプト
# --------------------

# --- 音の設定 ---
VOICE_LEVEL = 1.0    # DJ音量
MUSIC_LEVEL = 0.8    # 音楽音量
MAX_PLAY_TIME = 180  # 最大再生時間
POST_TALK_WAIT = 3.0 # 話後待機時間
# --------------------

# ==========================================
# 2. File & Metadata Management
# ==========================================

def load_persona(): # AIペルソナの読み込み    
    if os.path.exists("persona.txt"):
        with open("persona.txt", "r", encoding="utf-8") as f:
            return f.read().strip() # persona.txtがない場合は、以下のデフォルトのペルソナを使用する
    return "You are Silas Requiem, a sophisticated AI DJ for a classical program. Use elegant, philosophical English only."

def get_and_clear_comments(): # 配信スイッチに基づいてコメント取得先を自動で切り替える
    if USE_YOUTUBE: # YouTubeモード：メモリ上のコメントバッファを返す
        global comment_buffer
        if not comment_buffer: return ""
        content = "\n".join(comment_buffer)
        comment_buffer.clear()
        return content
    else: # ローカルモード：既存のcomment.txtを読み込む
        src = "comment.txt"
        tmp = "comment_work.txt"
        content = ""
        
        if os.path.exists(src):
            try:
                # ファイル名を変更することで、外部ツールからの追記を遮断し、占有権を確保する
                shutil.move(src, tmp)
                with open(tmp, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    content = "".join(lines[-100:]).strip()  # 最後の100行だけ読み込む
                os.remove(tmp) # 処理後に削除
            except Exception as e:
                print(f"   [System] File sync error: {e}")
        return content

async def fetch_comments(video_id): # YouTubeコメントのバックグラウンド取得
    if not USE_YOUTUBE: return
    try:
        chat = pytchat.create(video_id)
        while chat.is_alive():
            for c in chat.get().items:
                comment_buffer.append(f"{c.author.name}: {c.message}")
                if len(comment_buffer) > 100: comment_buffer.pop(0)
        
        await asyncio.sleep(1)
    except Exception as e:
        print(f"   [System] YouTube Chat monitor error: {e}")        

def load_song_database(): # 音楽CSVの読み込み
    song_db = {}
    if not os.path.exists(CSV_PATH): 
        return song_db
    try:
        with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    key_id = int(row['id'])
                    song_db[key_id] = {
                        'play_flag': int(row.get('play_flag', 0)),
                        'time_scale': float(row.get('time_scale', 5)), 
                        'last_played': row.get('last_played', ''),
                        'title': row.get('title', 'Unknown Title'),
                        'composer': row.get('composer', 'Unknown Composer'),
                        'performer': row.get('performer', 'Unknown Performer'),
                    }
                except ValueError: continue
    except Exception as e: print(f"   [Error] CSV Load Failed: {e}")
    return song_db

def scan_music_files(): # 音楽ファイルのスキャン    
    files_map = {}
    all_files = glob.glob(os.path.join(MUSIC_FOLDER, "*.mp3"))
    for path in all_files:
        match = re.match(r"(\d+)", os.path.basename(path))
        if match: files_map[int(match.group(1))] = path
    return files_map

def get_song_info(song_id): # 曲情報の取得
    if song_id in SONG_DB:
        return SONG_DB[song_id]
    if song_id in SONG_FILES:
        fn = os.path.basename(SONG_FILES[song_id])
        return {'title': fn, 'composer': 'Unknown', 'performer': 'Unknown'}
    return None

# --- 選曲エンジン ---

def get_now_jst(): # 現在時刻の取得
    return datetime.now(timezone(timedelta(hours=UTC_OFFSET)))

def get_target_scale(): # 目標スケールの取得
    now = get_now_jst()
    # 1日の経過秒数を算出（0〜86400）
    seconds = now.hour * 3600 + now.minute * 60 + now.second
    # 正午（43200秒）との距離に基づき、1.0から9.0の間で変動させる
    return 9.0 - (abs(43200 - seconds) / 43200.0) * 8.0

def select_next_song_weighted(song_db, available_ids): # 選曲エンジン   
    t_target = get_target_scale()
    now_ts = get_now_jst().timestamp()
    
    candidates, weights = [], []
    for sid in available_ids:
        song = song_db.get(sid)
        if not song or song.get('play_flag', 0) == 0: continue
        
        p_logic = BOOST_2 if song.get('play_flag') == 2 else 1.0
        s_val = song.get('time_scale', 5.0)
        
        lp = song.get('last_played', '')
        try:
            time_diff = (now_ts - datetime.fromisoformat(lp).timestamp()) if lp else 86400.0
        except:
            time_diff = 86400.0
        
        if RANDOM_MODE: 
            w = p_logic * time_diff
        else:
            # 指定されたスケールと曲のスケールの距離を算出
            dist = abs(t_target - s_val)
            # 距離が近いほど重みを指数関数的に増大させる
            w = (p_logic / ((dist + 1.0) ** 2)) * time_diff # 2をつけると重みが増える   
            if dist > 3.0:
                w *= 0.000001
        
        candidates.append(sid)
        weights.append(w)
        
    if not candidates: 
        return random.choice(available_ids) if available_ids else None # 重み付け選曲ができない場合はランダム選曲
    return random.choices(candidates, weights=weights, k=1)[0]

def mark_as_played(song_id):
    """ファイルへの書き込みを排除し、メモリ上のデータベースのみを更新する"""
    now_str = get_now_jst().isoformat()
    if song_id in SONG_DB:
        SONG_DB[song_id]['last_played'] = now_str

def save_song_database():
    """蓄積されたメモリ上の情報を、一度だけファイルへ記録する"""
    if not os.path.exists(CSV_PATH) or not SONG_DB:
        return
    
    fieldnames = []
    with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames

    with open(CSV_PATH, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for sid, info in SONG_DB.items():
            row = {'id': sid}
            row.update(info)
            writer.writerow(row)

# ----------------------------

SONG_DB = load_song_database()
SONG_FILES = scan_music_files()

# ==========================================
# 3. AI Script Generation & Voice Synthesis
# ==========================================

async def generate_script_async(prompt_type, current_info=None, next_info=None, comments=None): #トークスクリプトを生成する
    persona_setting = load_persona()
    comment_part = ""

    is_seasonal = (prompt_type in ["opening", "closing"]) or (random.random() < 0.3) # 30%の確率で季節の挨拶を含める
    now_local = get_now_jst()  # 現在時刻
    time_context = f"Briefly touch upon the feeling of this hour: {now_local.strftime('%Y-%m-%d %H')} (UTC{UTC_OFFSET:+}). Do not mention exact time." if is_seasonal else ""
    
    if prompt_type == "opening":
        instruction = f"Write a program opening. Greet listeners. {time_context} Approx 100 words. Do NOT describe sound effects (e.g. 'music starts'). Write ONLY the spoken English words."
    elif prompt_type == "closing":
        instruction = f"Write a program closing. Bid farewell to the day. Approx 100 words. Do NOT describe sound effects. Write ONLY the spoken English words."
    else:
        c_text = f"'{current_info['title']}' by {current_info['composer']}, performed by {current_info['performer']}"
        n_text = f"'{next_info['title']}' by {next_info['composer']}, performed by {next_info['performer']}"
        if comments:
            comment_part = f"\n【Messages from Unpurified Souls】\n{comments}\n"
            instruction = (
                f"[SPEECH SECTION]\n"
                f"Write a 150-word script. Briefly Reflect on {c_text}. "
                f"Then, summarize the essence of one listener's message and offer a warm, thoughtful response that provides genuine comfort. "
                f"Finally, Briefly introduce {n_text}.\n"
                f"CRITICAL: Use ONLY English. NO other languages, and NO non-English characters are allowed in this section. Do NOT use numbering, bullet points, or separators.\n\n"
                f"[LOG SECTION]\n"
                f"Provide a brief Japanese translation of your response to the listener, prefixed with '[LOG]'.\n\n"
                f"Messages from Unpurified Souls:\n{comments if comments else 'None'}"
            )
        else:
            instruction = f"Briefly reflect on {c_text}. {time_context} Then provide a sophisticated introduction for {n_text}. Approx 150 words. Do NOT include sound effects. Write ONLY the spoken words."

    prompt = f"{persona_setting}\n\n{comment_part}\n\n[Request]\n{instruction}\n\n*Write in elegant English only (except after [LOG] if requested). Strictly NO sound effects or stage directions."

    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        return response.text.strip()
    except Exception as e: return f"System Error: {e}"

async def prepare_next_talk(prompt_type, current_info, next_info, comments, output_file):
    # 台本生成から音声合成までを一括して管理する。
    # 通信失敗時はデフォルトの台本を適用し、番組の停止を回避する。

    # 1. 台本生成（リトライとタイムアウトを適用）
    full_response = await safe_call(generate_script_async, prompt_type, current_info, next_info, comments)
    
    if not full_response: 
        # 通信全滅時のフォールバック
        speech_text = DEFAULT_SCRIPT
        log_text = "API connection failed. Used default fallback script."
    else:
        # [LOG] セクションの分離
        parts = re.split(r'\[LOG\]', full_response, flags=re.IGNORECASE)
        speech_text = parts[0].strip()
        speech_text = re.sub(r'\[.*?\]', '', speech_text).strip()
        log_text = parts[1].strip() if len(parts) > 1 else ""

    # ログの出力（デバッグ用）
    print(f"\n[Future Script Prepared]\n{speech_text}")
    if log_text:
        print(f"\n[Translation Log]\n{log_text}\n")

    # 2. 音声合成（リトライを適用）
    async def synthesize():
        communicate = edge_tts.Communicate(speech_text, VOICE_NAME, rate="-10%")
        await communicate.save(output_file)
        return True

    success = await safe_call(synthesize)
    
    if not success:
        print(f"  [System Error] Failed to generate audio file: {output_file}")
        if os.path.exists(output_file): os.remove(output_file)
        return None

    return speech_text

async def safe_call(func, *args, **kwargs):
    # 指数バックオフを用いたリトライ実行
    for i in range(MAX_RETRIES):
        try:
            return await asyncio.wait_for(func(*args, **kwargs), timeout=TIMEOUT_SEC)
        except Exception as e:
            if i == MAX_RETRIES - 1:
                print(f"  [System Error] Final failure: {e}")
                return None
            wait_time = RETRY_DELAY * (2 ** i)
            print(f"  [Warning] Connection failed. Retrying in {wait_time}s... ({i+1})")
            await asyncio.sleep(wait_time)
    return None

# ==========================================
# 4. Graceful Execution Engine
# ==========================================

async def main_loop():
    pygame.mixer.pre_init(44100, -16, 2, 4096) 
    pygame.mixer.init()

    # --- チャット取得タスクのバックグラウンド起動 ---
    if USE_YOUTUBE:
        print(f"   [System] Connecting to YouTube Live: {VIDEO_ID}")
        asyncio.create_task(fetch_comments(VIDEO_ID))
    # ----------------------------------------------

    available_ids = list(SONG_FILES.keys())
    next_talk_audio = "next_talk.mp3"
    final_audio = "final.mp3"

    played_in_session = []
    
    if not available_ids:
        print("音楽ファイルが見つかりません。")
        return

    # --- クロージングの言葉を最初に用意し、メモリへ保持する ---
    print("  [System] Preparing final script in advance...")
    ed_script = await generate_script_async("closing")
    await edge_tts.Communicate(ed_script, VOICE_NAME, rate="-10%").save(final_audio)
    final_voice_obj = pygame.mixer.Sound(final_audio) 
    # ---------------------------------------------------------  

    mode_text = "RANDOM" if RANDOM_MODE else "TIME-SYNC"
    print(f"\n† Silas Requiem Online ({mode_text} / UTC+{UTC_OFFSET}) †\n")

    try:
        # --- オープニング ---
        op_script = await generate_script_async("opening")
        print(f"[Opening Script]\n{op_script}\n")
        await edge_tts.Communicate(op_script, VOICE_NAME, rate="-10%").save(next_talk_audio)
        
        voice = pygame.mixer.Sound(next_talk_audio)
        voice.set_volume(VOICE_LEVEL)
        voice.play()
        while pygame.mixer.get_busy(): await asyncio.sleep(0.5)

        current_id = select_next_song_weighted(SONG_DB, available_ids)

        while True:
            mark_as_played(current_id)
            played_in_session.append(current_id)
            current_info = get_song_info(current_id)
            sound_temp = pygame.mixer.Sound(SONG_FILES[current_id])
            duration = sound_temp.get_length()

            print(f"\n♪ Now Playing: {current_info['title']} [{int(duration)//60:02}:{int(duration)%60:02}]")
            pygame.mixer.music.load(SONG_FILES[current_id])
            pygame.mixer.music.set_volume(MUSIC_LEVEL)
            pygame.mixer.music.play()

            remaining_ids = [i for i in available_ids if i not in played_in_session]
        
            if not remaining_ids:
                last_played = played_in_session[-1] if played_in_session else None
                played_in_session.clear()
                if last_played:
                    played_in_session.append(last_played)
                remaining_ids = [i for i in available_ids if i not in played_in_session]

            next_id = select_next_song_weighted(SONG_DB, remaining_ids)
            next_info = get_song_info(next_id)
            
            prep_task = asyncio.create_task(
                prepare_next_talk("talk", current_info, next_info, get_and_clear_comments(), next_talk_audio)
            )

            start_time = time.time()
            while pygame.mixer.music.get_busy():
                if MAX_PLAY_TIME > 0 and (time.time() - start_time) > MAX_PLAY_TIME:
                    break
                await asyncio.sleep(0.5)

            pygame.mixer.music.fadeout(2000)
            await asyncio.sleep(2)

            await prep_task 
            await asyncio.sleep(0.5)

            if os.path.exists(next_talk_audio) and os.path.getsize(next_talk_audio) > 100:    
                try: 
                    print(f"   [Play] Silas Requiem: Speaking after the music...")
                    voice = pygame.mixer.Sound(next_talk_audio) 
                    await asyncio.sleep(0.5)
                    voice.set_volume(VOICE_LEVEL)
                    voice.play(fade_ms=150)

                    while pygame.mixer.get_busy(): 
                        await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"  [System] Audio load failed: {e}. Skipping talk to maintain flow.")
            else:
                print("  [System] Audio file missing or empty. Skipping talk to maintain flow.")
            
            await asyncio.sleep(POST_TALK_WAIT)
            current_id = next_id

    except (asyncio.CancelledError, KeyboardInterrupt):
        print("\n   [System] Finalizing...")

        for i in range(40):
            pygame.mixer.music.set_volume(MUSIC_LEVEL * (1.0 - i * 0.015))
            await asyncio.sleep(0.05)

        await asyncio.sleep(1.0)

        voice_channel = final_voice_obj.play(fade_ms=300)
        voice_channel.set_volume(VOICE_LEVEL * 0.9)

        while voice_channel.get_busy():
            await asyncio.sleep(0.5)

        print("   [System] Speech finished. Fading out music...")
        pygame.mixer.music.fadeout(10000)
        
        await asyncio.sleep(10.0)

    finally:
        save_song_database()
        pygame.mixer.quit()
        for temp_file in ["next_talk.mp3", "final.mp3"]:
            if os.path.exists(temp_file):
                try: os.remove(temp_file)
                except: pass

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        pass