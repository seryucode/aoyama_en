import os
import time
import random
import glob
import re
import csv
import pygame
import asyncio
import edge_tts
from google import genai

# ==========================================
# 1. 基本設定エリア
# ==========================================
api_key = os.environ.get("GEMINI_API_KEY")

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
MUSIC_LEVEL = 0.7     
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

    prompt = f"{persona_setting}\n\n{comment_part}\n\n[Request]\n{instruction}\n\n*Write in elegant English only."

    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        return response.text.strip()
    except Exception as e: return f"System Error: {e}"

async def prepare_next_talk(prompt_type, current_info, next_info, comments, output_file):
    script = await generate_script_async(prompt_type, current_info, next_info, comments)
    print(f"\n[Future Script Prepared]\n{script}\n")
    communicate = edge_tts.Communicate(script, VOICE_NAME, rate="-10%", pitch="-5Hz")
    await communicate.save(output_file)
    return script

# ==========================================
# 4. Graceful Execution Engine
# ==========================================

async def main_loop():
    pygame.mixer.pre_init(44100, -16, 2, 2048) # 周波数、ビット幅、チャンネル、バッファ
    pygame.mixer.init()
    available_ids = list(SONG_FILES.keys())
    next_talk_audio = "next_talk.mp3"
    
    if not available_ids:
        print("音楽ファイルが見つかりません。")
        return

    print("\n† Midnight FM: Silas Requiem Online (Gemini 2.5 Flash / Parallel) †\n")

    try:
        # --- Opening ---
        op_script = await generate_script_async("opening")
        await edge_tts.Communicate(op_script, VOICE_NAME, rate="-10%").save(next_talk_audio)
        
        voice = pygame.mixer.Sound(next_talk_audio)
        voice.set_volume(VOICE_LEVEL)
        voice.play()
        while pygame.mixer.get_busy(): await asyncio.sleep(0.1)

        current_id = random.choice(available_ids)

        while True:
            current_info = get_song_info(current_id)
            sound_temp = pygame.mixer.Sound(SONG_FILES[current_id])
            duration = sound_temp.get_length()

            print(f"\n♪ Now Playing: {current_info['title']} [{int(duration)//60:02}:{int(duration)%60:02}]")
            pygame.mixer.music.load(SONG_FILES[current_id])
            pygame.mixer.music.set_volume(MUSIC_LEVEL)
            pygame.mixer.music.play()

            next_id = random.choice(available_ids)
            while next_id == current_id and len(available_ids) > 1:
                next_id = random.choice(available_ids)
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
        print("\n   [System] Interrupt received...")
        
        ed_script = await generate_script_async("closing")
        output_path = "final.mp3"
        await edge_tts.Communicate(ed_script, VOICE_NAME, rate="-10%").save(output_path)
        
        # 1. 再生前にロードを完了させる（不連続性の回避）
        final_voice = pygame.mixer.Sound(output_path)
        final_voice.set_volume(VOICE_LEVEL)

        # 2. ダッキング：喋る前に音楽を少し下げる（0.7 -> 0.3）
        pygame.mixer.music.set_volume(0.3)
        await asyncio.sleep(0.5) # わずかな静寂
        
        # 3. 再生
        final_voice.play()
        
        while pygame.mixer.get_busy(): 
            await asyncio.sleep(0.1)
            
        print("   [System] Speech finished. Fading out music...")
        pygame.mixer.music.fadeout(5000) 
        
        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.1)
            
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