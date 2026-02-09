import asyncio
import edge_tts

VOICES = {
    "Andrew": "en-US-AndrewNeural",
    "Christopher": "en-US-ChristopherNeural",
    "Steffan": "en-US-SteffanNeural"
}

TEXT = "I am Requiem Aoyama. Today ends here. Let the silence consume your fatigue."

async def generate_test_voices():
    for name, voice in VOICES.items():
        print(f"【System】{name} の喉を調律中...")
        communicate = edge_tts.Communicate(TEXT, voice)
        await communicate.save(f"test_{name}.mp3")
    print("\n【Success】三つの声が生成されたぞ。聞き比べて、魂に響くものを選べ。")

if __name__ == "__main__":
    asyncio.run(generate_test_voices())