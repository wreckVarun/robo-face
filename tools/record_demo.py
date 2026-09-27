"""
Re-create the images in assets/: the demo GIF, the all-faces sheet and a screenshot.
Renders off-screen, so no window opens.

    pip install -r requirements-dev.txt
    python tools/record_demo.py
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame              # noqa: E402
from PIL import Image      # noqa: E402

import robot_face as rf    # noqa: E402

ASSETS = os.path.join(ROOT, "assets")
FPS = 15
HOLD = 0.9                 # seconds spent on each face in the GIF
DEMO = ["Neutral", "Happy", "Excited", "Love", "Surprised", "Curious", "Sad",
        "Crying", "Angry", "Dizzy", "Sleepy", "Wink", "Laughing"]


def to_pil(surface):
    return Image.frombytes("RGB", surface.get_size(), pygame.image.tostring(surface, "RGB"))


def settle(app, seconds):
    for _ in range(int(seconds * 60)):
        app.update(1 / 60)


def main():
    pygame.init()
    win = pygame.display.set_mode((rf.WIN_W, rf.WIN_H))
    app = rf.FaceApp(win)
    app.auto_blink = False
    names = [e["name"] for e in rf.EXPRESSIONS]
    os.makedirs(ASSETS, exist_ok=True)

    # 1) demo GIF: ears + screen + name label, cycling through a few faces
    crop = pygame.Rect(90, 0, rf.WIN_W - 180, rf.DISP.bottom + 75)
    frames = []
    for name in DEMO:
        app.set_expression(names.index(name))
        for k in range(int(HOLD * FPS)):
            if name == "Neutral" and k == 6:
                app.start_blink()
            for _ in range(60 // FPS):
                app.update(1 / 60)
            app.draw()
            img = to_pil(win.subsurface(crop))
            img = img.resize((img.width * 3 // 5, img.height * 3 // 5), Image.LANCZOS)
            frames.append(img.convert("P", palette=Image.ADAPTIVE, colors=128))
    frames[0].save(os.path.join(ASSETS, "demo.gif"), save_all=True, append_images=frames[1:],
                   duration=int(1000 / FPS), loop=0, optimize=True)

    # 2) all 25 faces in a 5x5 sheet
    app.next_twitch = 1e9
    tile_src = pygame.Rect(90, 0, rf.WIN_W - 180, rf.DISP.bottom + 30)
    tw, th = tile_src.w * 2 // 5, tile_src.h * 2 // 5
    sheet = pygame.Surface((tw * 5, th * 5))
    font = pygame.font.SysFont("avenirnext,helveticaneue,arial", 16, bold=True)
    for i, name in enumerate(names):
        app.set_expression(i)
        settle(app, 0.8)
        app.draw()
        tile = pygame.transform.smoothscale(win.subsurface(tile_src).copy(), (tw, th))
        tile.blit(font.render(name, True, (255, 235, 245)), (10, th - 24))
        sheet.blit(tile, ((i % 5) * tw, (i // 5) * th))
        if name == "Happy":
            pygame.image.save(win, os.path.join(ASSETS, "screenshot.png"))
    pygame.image.save(sheet, os.path.join(ASSETS, "all_faces.png"))

    for f in ("demo.gif", "all_faces.png", "screenshot.png"):
        print("%-15s %6.0f KB" % (f, os.path.getsize(os.path.join(ASSETS, f)) / 1024))


if __name__ == "__main__":
    main()
