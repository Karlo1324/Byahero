"""One-off helper: crop and optimise the ByaHero emblem for the web UI."""

import os
from PIL import Image

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(
    BASE, "templates", "Logo",
    "Monochrome Isometric BA Monogram Emblem.png",
)
OUT_DIR = os.path.join(BASE, "static", "img")

im = Image.open(SRC).convert("RGBA")

alpha = im.getchannel("A")
bbox = alpha.point(lambda p: 255 if p > 12 else 0).getbbox()
print("alpha bbox:", bbox)

if bbox:
    im = im.crop(bbox)

# Square it out so the emblem stays centred and never distorts.
side = max(im.size)
square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
square.paste(im, ((side - im.size[0]) // 2, (side - im.size[1]) // 2), im)
im = square

os.makedirs(OUT_DIR, exist_ok=True)

im.resize((512, 512), Image.LANCZOS).save(
    os.path.join(OUT_DIR, "logo.png"), optimize=True
)
im.resize((128, 128), Image.LANCZOS).save(
    os.path.join(OUT_DIR, "favicon.png"), optimize=True
)

for name in ("logo.png", "favicon.png"):
    p = os.path.join(OUT_DIR, name)
    print(name, os.path.getsize(p), "bytes")
