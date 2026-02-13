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
RANDOM_MODE = False
UTC_OFFSET = 9
BOOST_2 = 10.0
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

VOICE_LEVEL = 0.95
MUSIC_LEVEL = 0.8
MAX_PLAY_TIME = 200
POST_TALK_WAIT = 3.0

# ==========================================
# 2. File & Metadata Management
# ==========================================

def load_persona():
    if os.path.exists("persona.txt"):
        with open("persona.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    return "You are Silas Requiem, a sophisticated AI DJ for a nocturnal classical program. Use elegant, philosophical English only."

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

def get_song_info(song_id):
    if song_id in SONG_DB:
        return SONG_DB[song_id]
    if song_id in SONG_FILES:
        fn = os.path.basename(SONG_FILES[song_id])
        return {'title': fn, 'composer': 'Unknown', 'performer': 'Unknown'}
    return None

# --- 選曲エンジン ---

def get_now_jst():
    return datetime.now(timezone(timedelta(hours=UTC_OFFSET)))

def get_target_scale():
    now = get_now_jst()
    # 1日の経過秒数を算出（0〜86400）
    seconds = now.hour * 3600 + now.minute * 60 + now.second
    # 正午（43200秒）との距離に基づき、1.0から9.0の間で変動させる
    return 9.0 - (abs(43200 - seconds) / 43200.0) * 8.0

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
            w = (p_logic / ((dist + 1.0) ** 10)) * time_diff
            if dist > 3.0:
                w *= 0.000001
        
        candidates.append(sid)
        weights.append(w)
        
    if not candidates: return random.choice(available_ids)
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
    
    # 既存のヘッダーを取得するために一度読み込む
    fieldnames = []
    with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames

    # まとめて書き出し
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

async def generate_script_async(prompt_type, current_info=None, next_info=None, comments=None):
    persona_setting = load_persona()
    comment_part = ""

    if prompt_type == "opening":
        instruction = "Write a program opening. Greet listeners. Approx 100 words. Do NOT describe sound effects (e.g. 'music starts'). Write ONLY the spoken English words."
    elif prompt_type == "closing":
        instruction = "Write a program closing. Bid farewell to the day. Approx 100 words. Do NOT describe sound effects. Write ONLY the spoken English words."
    else:
        c_text = f"'{current_info['title']}' by {current_info['composer']}, performed by {current_info['performer']}"
        n_text = f"'{next_info['title']}' by {next_info['composer']}, performed by {next_info['performer']}"
        if comments:
            comment_part = f"\n【Messages from Unpurified Souls】\n{comments}\n"
            instruction = (
                f"[SPEECH SECTION]\n"
                f"Write a 150-word script. Reflect on {c_text}. "
                f"Then, summarize the essence of one listener's message and offer a warm, thoughtful response that provides genuine comfort. "
                f"Finally, introduce {n_text}.\n"
                f"CRITICAL: Use ONLY English. NO other languages, and NO non-English characters are allowed in this section. Do NOT use numbering, bullet points, or separators.\n\n"
                f"[LOG SECTION]\n"
                f"Provide a brief Japanese translation of your response to the listener, prefixed with '[LOG]'.\n\n"
                f"Messages from Unpurified Souls:\n{comments if comments else 'None'}"
            )
        else:
            instruction = f"Briefly reflect on {c_text}. Then provide a sophisticated introduction for {n_text}. Approx 200 words. Do NOT include sound effects. Write ONLY the spoken words."

    prompt = f"{persona_setting}\n\n{comment_part}\n\n[Request]\n{instruction}\n\n*Write in elegant English only (except after [LOG] if requested). Strictly NO sound effects or stage directions."

    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        return response.text.strip()
    except Exception as e: return f"System Error: {e}"

async def prepare_next_talk(prompt_type, current_info, next_info, comments, output_file):
    full_response = await generate_script_async(prompt_type, current_info, next_info, comments)
    
    parts = re.split(r'\[LOG\]', full_response, flags=re.IGNORECASE)
    speech_text = parts[0].strip()
    speech_text = re.sub(r'\[.*?\]', '', speech_text).strip()
    
    if comments:
        print(f"\n[Future Script Prepared]\n{speech_text}")
        if len(parts) > 1:
            print(f"\n[Translation Log]\n{parts[1].strip()}\n")
    else:
        print(f"\n[Future Script Prepared]\n{speech_text}")

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

    # 一回流した曲を貯めるリスト
    played_in_session = []
    
    if not available_ids:
        print("音楽ファイルが見つかりません。")
        return

    mode_text = "RANDOM" if RANDOM_MODE else "TIME-SYNC"
    print(f"\n† Silas Requiem Online ({mode_text} / UTC+{UTC_OFFSET}) †\n")

    try:
        # --- オープニング ---
        op_script = await generate_script_async("opening")
        print(f"[Opening Script]\n{op_script}\n")
        await edge_tts.Communicate(op_script, VOICE_NAME, rate="-10%").save(next_talk_audio)
        
        voice = pygame.mixer.Sound(next_talk_audio)
        voice.set_volume(VOICE_LEVEL); voice.play()
        while pygame.mixer.get_busy(): await asyncio.sleep(0.1)

        current_id = select_next_song_weighted(SONG_DB, available_ids)

        while True:
            mark_as_played(current_id)
            played_in_session.append(current_id)
            current_info = get_song_info(current_id)
            sound_temp = pygame.mixer.Sound(SONG_FILES[current_id])
            duration = sound_temp.get_length()

            print(f"\n♪ Now Playing: {current_info['title']} [{int(duration)//60:02}:{int(duration)%60:02}]")
            pygame.mixer.music.load(SONG_FILES[current_id])
            pygame.mixer.music.set_volume(MUSIC_LEVEL); pygame.mixer.music.play()

            # 次の曲を選ぶ際、記憶にあるものを候補から除外する
            # 曲が尽きることはあるまいが、念のため安全策は講じておく
            remaining_ids = [i for i in available_ids if i not in played_in_session]
        
            if not remaining_ids:
                # 万が一、全ての曲を流し尽くしたなら記憶をリセットする
                played_in_session.clear()
                remaining_ids = available_ids

            # 次の曲の選定と台本の準備
            next_id = select_next_song_weighted(SONG_DB, remaining_ids)
            next_info = get_song_info(next_id)
            
            prep_task = asyncio.create_task(
                prepare_next_talk("talk", current_info, next_info, get_and_clear_comments(), next_talk_audio)
            )

            # 音楽が再生中である限り、ここで足を止める
            start_time = time.time()
            while pygame.mixer.music.get_busy():
                # MAX_PLAY_TIMEによる制限がある場合の処理
                if MAX_PLAY_TIME > 0 and (time.time() - start_time) > MAX_PLAY_TIME:
                    break
                await asyncio.sleep(0.1)

            # 曲が終了、あるいは中断されたので音楽を止める
            pygame.mixer.music.fadeout(2000)
            await asyncio.sleep(2)

            await prep_task  # 台本準備の完了を待つ

            # 静寂の中で語りを開始する
            print(f"   [Play] Silas Requiem: Speaking after the music...")
            voice = pygame.mixer.Sound(next_talk_audio)
            voice.set_volume(VOICE_LEVEL); voice.play()

            while pygame.mixer.get_busy(): 
                await asyncio.sleep(0.1)
            
            await asyncio.sleep(POST_TALK_WAIT)
            current_id = next_id

    except (asyncio.CancelledError, KeyboardInterrupt):
        print("\n   [System] Finalizing...")

        # 幕引きの言葉を準備する
        ed_script = await generate_script_async("closing")
        final_audio = "final.mp3"
        await edge_tts.Communicate(
            ed_script,
            VOICE_NAME,
            rate="-10%"
        ).save(final_audio)

        # 1. 曲を流したまま、BGMの音量を「少し小さく」する
        # ここで急激に下げればまた雑音の原因になる。
        pygame.mixer.music.set_volume(MUSIC_LEVEL * 0.4)
        
        # 2. 最後の音声を入れる
        if os.path.exists(final_audio):
            closing_voice = pygame.mixer.Sound(final_audio)
            closing_voice.set_volume(VOICE_LEVEL)
            # 再生中のチャネルを保持し、その終了を監視する
            voice_channel = closing_voice.play()

            # 3. しゃべり終わるまで、ここで時を止める
            # music.get_busy()ではなく、voice_channelの監視が必要
            while voice_channel.get_busy():
                await asyncio.sleep(0.1)

        # 4. しゃべり終わった。ここで初めて、曲をフェードアウトさせる
        print("   [System] Speech finished. Fading out music...")
        pygame.mixer.music.fadeout(10000)
        
        # 完全に音が消えるまでの余韻
        await asyncio.sleep(10.0)

    finally:
        # 記録を刻み、舞台を片付ける
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