import os
import time
import random
import glob
import re
import csv
import pygame
import asyncio
import edge_tts
import google.generativeai as genai

# ==========================================
# 1. Basic Settings
# ==========================================
api_key = os.environ.get("GEMINI_API_KEY")

MUSIC_FOLDER = r"D:/Music"  
CSV_PATH = "musicdata.csv" 
MODEL_NAME = 'gemini-2.5-flash' # Adjusted to latest stable
VOICE_NAME = "en-US-ChristopherNeural"

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL_NAME)
else:
    print("【Error】API Key not set.")
    exit()

# --- Audio Balance Settings ---
VOICE_LEVEL = 1.0     
MUSIC_LEVEL = 0.7     
MAX_PLAY_TIME = 200
POST_TALK_WAIT = 5.0  

# ==========================================
# 2. External File Loading
# ==========================================

def load_persona():
    if os.path.exists("persona.txt"):
        with open("persona.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    return "You are Silas Requiem, a sophisticated AI radio DJ for a nocturnal classical program."

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

# ==========================================
# 3. Music Database & File Management
# ==========================================

def load_song_database():
    song_db = {}
    if not os.path.exists(CSV_PATH): return song_db
    try:
        with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    key_id = int(row['id'])
                    song_db[key_id] = {
                        'title': row.get('title', ''),
                        'composer': row.get('composer', ''),
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
        return {'title': fn, 'composer': 'Unknown'}
    return None

# ==========================================
# 4. AI Script Generation
# ==========================================

def generate_dj_script(prompt_type, current_info=None, next_info=None, comments=None):
    print(f"   [AI] Silas Requiem is composing... ({prompt_type})")
    persona_setting = load_persona()
    comment_part = ""

    if prompt_type == "opening":
        instruction = "Write a program opening. Greet the listeners in the silence of the night and invite them into stillness. Approx 100 words."
    elif prompt_type == "closing":
        instruction = "Write a program closing. Announce that another day has been laid to rest. Wish them a peaceful slumber. Approx 100 words."
    else:
        c_text = f"'{current_info['title']}' by {current_info['composer']}"
        n_text = f"'{next_info['title']}' by {next_info['composer']}"
        
        if comments:
            comment_part = f"\n【Recent messages (Unpurified Souls)】\n{comments}\n\nPick one interesting message, address the sender, and offer a calm, philosophical response."
            instruction = f"Briefly comment on {c_text}, then provide an insightful and solemn introduction for {n_text}. Prioritize responding to the listener's message with mercy. Approx 200 words."
        else:
            instruction = f"Briefly reflect on {c_text}, then provide a sophisticated, professional, and solemn introduction for {n_text}, discussing its historical or emotional depth. Approx 200 words."

    prompt = f"{persona_setting}\n\n{comment_part}\n\n[Request]\n{instruction}\n\n*Write in elegant English only."

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e: return f"System Error: {e}"

# ==========================================
# 5. Audio Synthesis & Playback
# ==========================================

async def synthesize_audio(text, output_file):
    communicate = edge_tts.Communicate(text, VOICE_NAME)
    await communicate.save(output_file)

def play_audio(text):
    print(f"   [Play] Silas Requiem speaking...")
    temp_file = "speech.mp3"
    asyncio.run(synthesize_audio(text, temp_file))
    
    try:
        voice_sound = pygame.mixer.Sound(temp_file)
        voice_sound.set_volume(VOICE_LEVEL)
        channel = voice_sound.play()
        while channel.get_busy(): time.sleep(0.01)
    except Exception as e:
        print(f"Playback Error: {e}")

# ==========================================
# 6. Main Loop
# ==========================================

def main():
    pygame.mixer.init()
    available_ids = list(SONG_FILES.keys())
    
    print("\n† Midnight FM: Silas Requiem Online †\n")

    op_script = generate_dj_script("opening")
    print(f"\n>>> {op_script}\n")
    play_audio(op_script)

    current_id = random.choice(available_ids)

    try:
        while True:
            current_info = get_song_info(current_id)
            
            sound_temp = pygame.mixer.Sound(SONG_FILES[current_id])
            total_sec = int(sound_temp.get_length())
            time_str = f"[{total_sec // 60:02}:{total_sec % 60:02}]"
            print(f"\n♪ Now Playing: {current_info['title']} {time_str}")

            pygame.mixer.music.load(SONG_FILES[current_id])
            pygame.mixer.music.set_volume(MUSIC_LEVEL)
            pygame.mixer.music.play()

            next_id = random.choice(available_ids)
            while next_id == current_id: next_id = random.choice(available_ids)
            next_info = get_song_info(next_id)

            new_comments = get_and_clear_comments() 
            talk_script = generate_dj_script("talk", current_info, next_info, new_comments)
            
            print("\n" + "—" * 50)
            print(talk_script)
            print("—" * 50 + "\n")

            st = time.time()
            fade_duration = 2000 
            while pygame.mixer.music.get_busy():
                if MAX_PLAY_TIME > 0 and (time.time() - st > MAX_PLAY_TIME):
                    pygame.mixer.music.fadeout(fade_duration)
                    time.sleep(fade_duration / 1000) 
                    break
                time.sleep(1)

            play_audio(talk_script)
            time.sleep(POST_TALK_WAIT)
            current_id = next_id

    except KeyboardInterrupt:
        ed_script = generate_dj_script("closing")
        print(f"\n>>> {ed_script}\n")
        play_audio(ed_script)
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.fadeout(4000)
            time.sleep(4)
        print("\n--- Eternal peace be with you. ---")

if __name__ == "__main__":
    main()