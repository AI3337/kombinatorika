"""Страница скана Сакаева в картинку для сверки глазами: python3 pdfpage.py 218 [ширина]"""
import sys, io, os, pymupdf
from PIL import Image
d = pymupdf.open(os.path.expanduser("~/Desktop/Шахматы/Сакаев : Том 1.pdf"))
p = int(sys.argv[1]); w = int(sys.argv[2]) if len(sys.argv) > 2 else 700
x = d[p].get_images()[0][0]
im = Image.open(io.BytesIO(d.extract_image(x)["image"])).convert("L")
im = im.resize((w, round(im.size[1] * w / im.size[0])))
out = os.environ.get("OUT", ".") + f"/p{p:03d}.png"; im.save(out); print(out)
