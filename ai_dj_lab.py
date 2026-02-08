import os
import time
import random
import glob
import re
import csv
import pygame
import requests
import google.generativeai as genai

# ==========================================
# 1. 基本設定エリア
# ==========================================
api_key = os.environ.get("GEMINI_API_KEY")

MUSIC_FOLDER = r"D:/Music"  
CSV_PATH = "音楽ファイル管理用.csv" 
VOICEVOX_URL = "http://127.0.0.1:50021"
SPEAKER_ID = 13  
MODEL_NAME = 'gemini-2.5-flash'

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL_NAME)
else:
    print("【Error】APIキーが設定されていません。")
    exit()

# --- オーディオ・バランス設定（数値を完全死守） ---
VOICE_LEVEL = 1.0     
MUSIC_LEVEL = 0.7     
VOICE_BOOST = 1.2     
MAX_PLAY_TIME = 240
POST_TALK_WAIT = 5.0  
CHUNK_GAP = 0.5       

# ==========================================
# 2. 外部ファイル読み込み・お便り管理
# ==========================================

def load_persona():
    if os.path.exists("persona.txt"):
        with open("persona.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    return "あなたはラジオDJ、レクイエム青山です。"

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
            print(f"   [System] お便り回収エラー: {e}")
    return content

# ==========================================
# 3. 音楽データベース＆ファイル管理
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
                        'title_reading': row.get('title_reading', ''),
                        'composer': row.get('composer', ''),
                        'composer_reading': row.get('composer_reading', ''),
                    }
                except ValueError: continue
    except Exception as e: print(f"   [Error] CSV読み込み失敗: {e}")
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
        return {'title': fn, 'title_reading': fn, 'composer': '', 'composer_reading': ''}
    return None

# ==========================================
# 4. AI台本生成・読み変換
# ==========================================

def generate_dj_script(prompt_type, current_info=None, next_info=None, comments=None):
    print(f"   [AI] レクイエム青山が執筆中... ({prompt_type})")
    persona_setting = load_persona()
    comment_part = ""

    if prompt_type == "opening":
        instruction = "番組のオープニング。今日を弔い、リスナーを静寂へ誘う挨拶を200文字程度で。"
    elif prompt_type == "closing":
        instruction = "番組のエンディング。今日という日を無事に葬り去ったことを告げ、安らかな眠りを祈る言葉を200文字程度で。"
    else:
        def fmt(info): return f"『{info['title']}』" + (f"（作曲：{info['composer']}）" if info['composer'] else "")
        c_text, n_text = fmt(current_info), fmt(next_info)
        
        if comments:
            comment_part = (
                f"\n【重要：届いているお便り（未浄化の魂）】\n{comments}\n\n"
                "上記から最も興味深いものを1つ選び、以下の形式で必ず返答してください：\n"
                "1. まず『ペンネーム（名前）さん。「〜〜」とのことですが……』と内容を要約して紹介する。\n"
                "2. それに対し、レクイエム青山らしく慈悲深く供養する。"
            )

        if comments:
            instruction = (
                f"曲 {c_text} への短い感想と、次曲 {n_text} の荘厳な解説。"
                f"届いているお便りを今回のトークの主役とし、音楽の解説よりも熱を入れて供養してください。お便りへの返答を疎かにすることは許されません。全体で400文字程度。"
            )
        else:
            instruction = (
                f"曲 {c_text} への短い感想と、次曲 {n_text} についての専門的かつ荘厳な解説。"
                f"次曲の歴史的背景、作曲家、演奏者、あるいは楽曲を掘り下げてリスナーに語りかけてください。全体で400文字程度。"
            )

    prompt = f"{persona_setting}\n\n{comment_part}\n\n【依頼】\n{instruction}\n\n※漢字混じりで出力。固有名詞は「」。"

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e: return f"システムエラー: {e}"

def convert_to_reading_script(original_text, special_readings=None):
    print("   [AI] ひらがな変換中...")
    custom_rule = ""
    if special_readings:
        custom_rule = "【最優先】\n" + "\n".join([f"・「{k}」→{v}" for k,v in special_readings.items() if k and v and k!=v])

    prompt = (
        f"以下の漢字を全て「ひらがな」に変換。アルファベット禁止。、。は「　」（全角スペース）に。"
        f"内容は絶対に変えない。文中に不要なスペースを入れないこと。\n{custom_rule}\n\n【本文】\n{original_text}"
    )
    try:
        response = model.generate_content(prompt)
        clean_text = response.text.replace("```", "").strip()
        return clean_text
    except: return original_text

# ==========================================
# 5. 音声合成・再生
# ==========================================

def prepare_audio_files(reading_text):
    audio_data_list = []
    lines = [l.strip() for l in reading_text.split('\n') if l.strip()]
    chunks = []
    for line in lines:
        if len(line) > 50: 
            chunks.extend([p.strip() for p in line.split('　') if p.strip()])
        else: chunks.append(line)

    print(f"     [System] 音声生成を開始しました...")
    for chunk in chunks:
        for retry in range(2):
            try:
                q = requests.post(f"{VOICEVOX_URL}/audio_query", params={"text": chunk, "speaker": SPEAKER_ID}, timeout=10).json()
                q['volumeScale'] = VOICE_BOOST
                s = requests.post(f"{VOICEVOX_URL}/synthesis", params={"speaker": SPEAKER_ID}, json=q, timeout=30)
                if len(s.content) > 1024:
                    audio_data_list.append(s.content)
                    break
            except: time.sleep(1)
    return audio_data_list

def play_audio_files(audio_data_list):
    print("   [Play] レクイエム青山、発声...")
    for data in audio_data_list:
        try:
            with open("temp_chunk.wav", "wb") as f: f.write(data)
            voice_sound = pygame.mixer.Sound("temp_chunk.wav")
            voice_sound.set_volume(VOICE_LEVEL)
            channel = voice_sound.play()
            while channel.get_busy(): time.sleep(0.01)
            time.sleep(CHUNK_GAP)
        except: pass

# ==========================================
# 6. メインループ
# ==========================================

def main():
    for f in glob.glob("*.wav"):
        try: os.remove(f)
        except: pass
    
    pygame.mixer.init()
    available_ids = list(SONG_FILES.keys())
    
    print("\n† Midnight FM: レクイエム青山 起動 †\n")

    op_script = generate_dj_script("opening")
    op_reading = convert_to_reading_script(op_script)
    play_audio_files(prepare_audio_files(op_reading))

    current_id = random.choice(available_ids)

    try:
        while True:
            current_info = get_song_info(current_id)
            
            # --- 【追加】再生前にコンソールのみへ長さを表示 ---
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
            
            rd = {}
            for info in [current_info, next_info]:
                rd[info['title']] = info['title_reading']
                rd[info['composer']] = info['composer_reading']
            
            talk_reading = convert_to_reading_script(talk_script, rd)

            print("\n" + "☠" * 45)
            print(talk_reading if talk_reading else talk_script)
            print("☠" * 45 + "\n")

            talk_audio = prepare_audio_files(talk_reading)

            st = time.time()
            fade_duration = 2000 
            while pygame.mixer.music.get_busy():
                if MAX_PLAY_TIME > 0 and (time.time() - st > MAX_PLAY_TIME):
                    pygame.mixer.music.fadeout(fade_duration)
                    time.sleep(fade_duration / 1000) 
                    break
                time.sleep(1)

            play_audio_files(talk_audio)
            time.sleep(POST_TALK_WAIT)
            current_id = next_id

    except KeyboardInterrupt:
        ed_script = generate_dj_script("closing")
        ed_reading = convert_to_reading_script(ed_script)
        play_audio_files(prepare_audio_files(ed_reading))
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.fadeout(4000)
            time.sleep(4)
        print("\n--- 永遠の安らぎを。 ---")

if __name__ == "__main__":
    main()