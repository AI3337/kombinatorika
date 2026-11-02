"""Склейка вырезок в одну картинку с подписями: python3 sheet.py out.png a.png:подпись b.png:подпись"""
import sys
from PIL import Image, ImageDraw
ims = [(Image.open(a.split(":")[0]), a.split(":", 1)[1] if ":" in a else "") for a in sys.argv[2:]]
W = max(i.size[0] for i, _ in ims); H = sum(i.size[1] + 22 for i, _ in ims)
s = Image.new("L", (W, H), 255); d = ImageDraw.Draw(s); y = 0
for i, t in ims:
    d.text((4, y + 4), t, fill=0); s.paste(i, (0, y + 18)); y += i.size[1] + 22
s.save(sys.argv[1]); print(s.size)
