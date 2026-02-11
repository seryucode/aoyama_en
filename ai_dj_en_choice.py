import os
import time
import random
import glob
import re
import csv
import pygame
import asyncio
import edge_tts
from datetime import datetime, timezone, timedelta
from google import genai

# ==========================================
# 1. 基本設定エリア
# ==========================================
api_key = os.environ.get("GEMINI_API_KEY")

# --- 選曲モード設定 ---
RANDOM_MODE = False  # True: 時間を無視してランダム / False: 時間に合わせる
UTC_OFFSET = 9      # 日本なら 9
BOOST_2 = 10.0      # play_flag=2 の時の倍率
# --------------------

MUSIC_FOLDER = r"D:/Music"  
CSV_PATH = "musicdata.csv" 
VOICEVOX_URL = "http://127.0.0.1:50021"
SPEAKER_ID = 13  
MODEL_NAME = 'gemini-2.5-flash' 
VOICE_NAME = "en-US-ChristopherNeural"

if api_key:
    client = genai.Client(api_key=api_key)
else:
    print("【Error】APIキーが設定されていません。")
    exit()

VOICE_LEVEL = 1.0      
MUSIC_LEVEL = 0.8      
MAX_PLAY_TIME = 200
POST_TALK_WAIT = 5.0  

# ==========================================
# 2. File & Metadata Management
# ==========================================

def load_persona():
    if os.path.exists("persona.txt"):
        with open("persona.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    return "You are Silas Requiem, a sophisticated AI DJ for a nocturnal classical program. Use elegant, philosophical English."

def get_and_clear_comments():
    content = ""
    if os.path.exists("comment.txt"):
        try:
            with open("comment.txt", "r", encoding="utf-8") as f:
                lines = f.readlines()
            content = "".join(lines[-10:]).strip()
            with open("comment.txt", "w", encoding="utf-8") as f:
                pass 
        except Exception as e:
            print(f"   [System] Comment retrieval error: {e}")
    return content

def load_song_database():
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

def scan_music_files():
    files_map = {}
    all_files = glob.glob(os.path.join(MUSIC_FOLDER, "*.mp3"))
    for path in all_files:
        match = re.match(r"(\d+)", os.path.basename(path))
        if match: files_map[int(match.group(1))] = path
    return files_map

# --- 知的選曲エンジンの核 ---

def get_now_jst():
    return datetime.now(timezone(timedelta(hours=UTC_OFFSET)))

def get_target_scale():
    now = get_now_jst()
    seconds = now.hour * 3600 + now.minute * 60 + now.second
    return 1.0 + (seconds / 86400.0) * 8.0

def select_next_song_weighted(song_db, available_ids):
    t_target = get_target_scale()
    now_ts = get_now_jst().timestamp()
    
    candidates, weights = [], []
    
    for sid in available_ids:
        song = song_db.get(sid)
        if not song or song.get('play_flag', 0) == 0: continue
        
        p_logic = BOOST_2 if song.get('play_flag') == 2 else 1.0
        s_val = song.get('time_scale', 5.0)
        
        lp = song.get('last_played', '')
        time_diff = (now_ts - datetime.fromisoformat(lp).timestamp()) if lp else 86400.0
        
        if RANDOM_MODE:
            w = p_logic * time_diff
        else:
            dist = abs(t_target - s_val)
            w = (p_logic / ((dist + 1.0) ** 10)) * time_diff
            if dist > 3.0:
                w *= 0.000001 
        
        candidates.append(sid)
        weights.append(w)
        
    if not candidates: return random.choice(available_ids)
    return random.choices(candidates, weights=weights, k=1)[0]

def mark_as_played(song_id):
    now_str = get_now_jst().isoformat()
    if song_id in SONG_DB:
        SONG_DB[song_id]['last_played'] = now_str
    
    if not os.path.exists(CSV_PATH): return
    rows = []
    with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if int(row['id']) == song_id: row['last_played'] = now_str
            rows.append(row)
    with open(CSV_PATH, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader(); writer.writerows(rows)

# ----------------------------

SONG_DB = load_song_database()
SONG_FILES = scan_music_files()

def get_song_info(song_id):
    if song_id in SONG_DB: return SONG_DB[song_id]
    if song_id in SONG_FILES:
        fn = os.path.basename(SONG_FILES[song_id])
        return {'title': fn, 'composer': 'Unknown', 'performer': 'Unknown'}
    return None

# ==========================================
# 3. AI Script Generation & Voice Synthesis
# ==========================================

async def generate_script_async(prompt_type, current_info=None, next_info=None, comments=None):
    persona_setting = load_persona()
    comment_part = ""

    if prompt_type == "opening":
        instruction = "Write a program opening. Greet listeners in the silence of the night. Approx 100 words."
    elif prompt_type == "closing":
        instruction = "Write a program closing. Bid farewell to the day. Approx 100 words."
    else:
        c_text = f"'{current_info['title']}' by {current_info['composer']}, performed by {current_info['performer']}"
        n_text = f"'{next_info['title']}' by {next_info['composer']}, performed by {next_info['performer']}"
        if comments:
            comment_part = f"\n【Messages from Unpurified Souls】\n{comments}\n"
            instruction = f"Briefly reflect on {c_text}. Then, address one listener's message. Finally, introduce {n_text}. Approx 200 words."
        else:
            instruction = f"Briefly reflect on {c_text}. Then provide a sophisticated introduction for {n_text}. Approx 200 words."

    # ログ用の日本語訳を求める指示を追加
    instruction += "\nAfter the English script, add a brief Japanese translation/summary for the console log. Prefix it with '[LOG]'."

    prompt = f"{persona_setting}\n\n{comment_part}\n\n[Request]\n{instruction}\n\n*Write in elegant English only, except for the section after [LOG]."

    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        return response.text.strip()
    except Exception as e: return f"System Error: {e}"

async def prepare_next_talk(prompt_type, current_info, next_info, comments, output_file):
    # 台本の生成
    full_response = await generate_script_async(prompt_type, current_info, next_info, comments)
    
    # [LOG] タグで分割（大文字小文字を問わず分割）
    parts = re.split(r'\[LOG\]', full_response, flags=re.IGNORECASE)
    speech_text = parts[0].strip()
    log_text = parts[1].strip() if len(parts) > 1 else "No translation available."

    # ログ画面にだけ日本語を出す
    print("-" * 30)
    print(f"[Future Speech]\n{speech_text}")
    print(f"\n[Translation Log]\n{log_text}")
    print("-" * 30)

    # 音声合成は英語部分のみを使用
    communicate = edge_tts.Communicate(speech_text, VOICE_NAME, rate="-10%")
    await communicate.save(output_file)
    return speech_text

# ==========================================
# 4. Graceful Execution Engine
# ==========================================

async def main_loop():
    pygame.mixer.pre_init(44100, -16, 2, 2048) 
    pygame.mixer.init()
    available_ids = list(SONG_FILES.keys())
    next_talk_audio = "next_talk.mp3"
    
    if not available_ids:
        print("音楽ファイルが見つかりません。")
        return

    mode_text = "RANDOM" if RANDOM_MODE else "TIME-SYNC"
    print(f"\n† Midnight FM: Silas Requiem Online ({mode_text} / UTC+{UTC_OFFSET}) †\n")

    try:
        # オープニングもログ分割に対応させるため修正
        op_full_response = await generate_script_async("opening")
        op_parts = re.split(r'\[LOG\]', op_full_response, flags=re.IGNORECASE)
        op_speech = op_parts[0].strip()
        op_log = op_parts[1].strip() if len(op_parts) > 1 else ""
        
        if op_log: print(f"\n[System Log: Opening Translation]\n{op_log}\n")
        
        await edge_tts.Communicate(op_speech, VOICE_NAME, rate="-10%").save(next_talk_audio)
        
        voice = pygame.mixer.Sound(next_talk_audio)
        voice.set_volume(VOICE_LEVEL)
        voice.play()
        while pygame.mixer.get_busy(): await asyncio.sleep(0.1)

        current_id = select_next_song_weighted(SONG_DB, available_ids)

        while True:
            mark_as_played(current_id)
            current_info = get_song_info(current_id)
            sound_temp = pygame.mixer.Sound(SONG_FILES[current_id])
            duration = sound_temp.get_length()

            print(f"\n♪ Now Playing: {current_info['title']} [{int(duration)//60:02}:{int(duration)%60:02}]")
            pygame.mixer.music.load(SONG_FILES[current_id])
            pygame.mixer.music.set_volume(MUSIC_LEVEL)
            pygame.mixer.music.play()

            next_id = select_next_song_weighted(SONG_DB, available_ids)
            next_info = get_song_info(next_id)
            
            prep_task = asyncio.create_task(
                prepare_next_talk("talk", current_info, next_info, get_and_clear_comments(), next_talk_audio)
            )

            play_limit = min(duration, MAX_PLAY_TIME) if MAX_PLAY_TIME > 0 else duration
            await asyncio.sleep(play_limit - 2)

            pygame.mixer.music.fadeout(2000)
            await asyncio.sleep(2)
            await prep_task 

            print(f"   [Play] Silas Requiem: Speaking...")
            voice = pygame.mixer.Sound(next_talk_audio)
            voice.set_volume(VOICE_LEVEL)
            voice.play()
            while pygame.mixer.get_busy(): await asyncio.sleep(0.1)
            
            await asyncio.sleep(POST_TALK_WAIT)
            current_id = next_id

    except (asyncio.CancelledError, KeyboardInterrupt):
        print("\n   [System] Finalizing...")
        ed_full = await generate_script_async("closing")
        ed_parts = re.split(r'\[LOG\]', ed_full, flags=re.IGNORECASE)
        ed_speech = ed_parts[0].strip()
        
        await edge_tts.Communicate(ed_speech, VOICE_NAME, rate="-10%").save("final.mp3")
        final_voice = pygame.mixer.Sound("final.mp3")
        final_voice.set_volume(VOICE_LEVEL)
        pygame.mixer.music.set_volume(0.3)
        await asyncio.sleep(0.5)
        final_voice.play(fade_ms=300) 
        while pygame.mixer.get_busy(): await asyncio.sleep(0.1)
        pygame.mixer.music.fadeout(5000) 
        while pygame.mixer.music.get_busy(): await asyncio.sleep(0.1)
        print("\n--- Eternal peace be with you. ---")

    finally:
        pygame.mixer.quit()
        for f in ["next_talk.mp3", "final.mp3"]:
            if os.path.exists(f): 
                try: os.remove(f)
                except: pass

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        pass