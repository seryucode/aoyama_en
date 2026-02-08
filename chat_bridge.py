import pytchat
import time

# YouTubeの配信ID（URLの最後にある英数字）
VIDEO_ID = "ここにURLのIDを入れる"

# NGワードリスト（適宜追加してください）
NG_WORDS = ["しね", "ころす", "ばか"] 

def start_bridge():
    chat = pytchat.create(video_id=VIDEO_ID)
    print(f"[Bridge] 接続完了。コメントを待機中...")

    while chat.is_alive():
        for c in chat.get().sync_items():
            # 1. NGワードチェック
            if any(word in c.message for word in NG_WORDS):
                print(f"[Block] 不適切なコメントをブロックしました")
                continue

            # 2. 特定の呼びかけがある時だけ拾う（ネタ感アップ！）
            if "青山さん" in c.message:
                with open("comment.txt", "w", encoding="utf-8") as f:
                    # 書き込み（上書き保存で常に最新の1件だけを保持）
                    f.write(f"{c.author.name}: {c.message}")
                print(f"[Saved] {c.author.name}: {c.message}")

        time.sleep(1)

if __name__ == "__main__":
    start_bridge()