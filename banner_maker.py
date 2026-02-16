from PIL import Image

# 元画像の読み込み
img = Image.open('silasrequiem_main.jpg')

# YouTubeの推奨規格
target_w, target_h = 2560, 1440

# 比率を維持して幅を2560pxに合わせる
w_percent = (target_w / float(img.size[0]))
h_size = int((float(img.size[1]) * float(w_percent)))
img_resized = img.resize((target_w, h_size), Image.Resampling.LANCZOS)

# 2560x1440の黒いキャンバスを作成
banner = Image.new('RGB', (target_w, target_h), (0, 0, 0))

# 中央に配置（これで高さ1152px不足のエラーを回避できる）
upper = (target_h - h_size) // 2
banner.paste(img_resized, (0, upper))

# 保存
banner.save('youtube_banner_fixed.png')