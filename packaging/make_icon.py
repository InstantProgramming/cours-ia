"""Dessine l'icône de l'appli (PNG 1024×1024) : carré arrondi bleu → violet, livre ouvert et étincelle."""

import math
import sys

from PIL import Image, ImageDraw, ImageFilter

S = 1024


def gradient(size, top, bottom):
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size)
            px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(top, bottom))
    return img


def star(cx, cy, r_out, r_in, branches=4, rot=-math.pi / 2):
    pts = []
    for i in range(branches * 2):
        r = r_out if i % 2 == 0 else r_in
        a = rot + i * math.pi / branches
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def main(out):
    margin = 100  # marge recommandée par Apple pour les icônes macOS
    body = S - 2 * margin
    bg = gradient(body, (47, 91, 211), (124, 70, 220))
    mask = Image.new("L", (body, body), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, body - 1, body - 1), radius=int(body * 0.225), fill=255)

    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((margin, margin + 18, S - margin, S - margin + 18),
                                             radius=int(body * 0.225), fill=(20, 20, 60, 110))
    icon.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(22)))
    icon.paste(bg, (margin, margin), mask)

    d = ImageDraw.Draw(icon)
    # livre ouvert
    cx, base = S / 2, 690
    w, h = 300, 170
    paper = (255, 253, 249, 255)
    d.polygon([(cx, base), (cx - w, base - 40), (cx - w, base - 40 - h), (cx, base - h)], fill=paper)
    d.polygon([(cx, base), (cx + w, base - 40), (cx + w, base - 40 - h), (cx, base - h)], fill=(236, 240, 255, 255))
    for i in range(3):
        y = base - h + 45 + i * 38
        d.line([(cx - w + 50, y - 22), (cx - 40, y)], fill=(160, 175, 230, 255), width=12)
        d.line([(cx + 40, y), (cx + w - 50, y - 22)], fill=(170, 160, 230, 255), width=12)
    # étincelle (le « ✦ » de l'appli)
    d.polygon(star(S / 2, 345, 185, 48), fill=(255, 214, 102, 255))
    d.polygon(star(S / 2 + 175, 255, 62, 16), fill=(255, 255, 255, 230))
    icon.save(out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "icon.png")
