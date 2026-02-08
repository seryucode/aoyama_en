import os
import google.generativeai as genai

# 環境変数からキーを読み込む
api_key = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=api_key)

print("--- 使用可能なモデルリストを取得中... ---")

try:
    # 使えるモデルのリストを取得
    for m in genai.list_models():
        # 「generateContent」という機能（テキスト生成）ができるモデルだけを表示
        if 'generateContent' in m.supported_generation_methods:
            print(f"モデル名: {m.name}")
            print(f"　表示名: {m.display_name}")
            print(f"　説明　: {m.description}")
            print("-" * 30)
            
    print("\n✅ リストの取得が完了しました。")
    print("この中にある『models/gemini-...』という名前を、コードの MODEL_NAME に使えます。")

except Exception as e:
    print(f"❌ エラーが発生しました: {e}")