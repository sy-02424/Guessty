r"""Convert the edited cream title artwork without touching earlier assets.

Run with: .venv\Scripts\python.exe tools\convert-title-v2.py
Inputs are local-only edits under assets/raw. Outputs are versioned v2 PNGs.
The logo's user-approved material palette has <=16 colors and binary alpha;
the one-piece panorama uses <=32 original material colors without dithering.
"""

from collections import deque
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "assets" / "raw"
CREAM = (230, 225, 198)
KHAKI = (102, 111, 84)
DARK = (47, 51, 38)
ORANGE = (217, 132, 78)


def source_palette(pixels, count):
    """Median cut, with every centroid snapped to an actual source RGB."""
    if not pixels:
        raise ValueError("Empty palette input")
    strip = Image.new("RGB", (len(pixels), 1))
    strip.putdata(pixels)
    quantized = strip.quantize(colors=count, method=Image.Quantize.MEDIANCUT,
                              dither=Image.Dither.NONE)
    entries = quantized.getpalette()
    clusters = {}
    for color, index in zip(pixels, quantized.get_flattened_data()):
        clusters.setdefault(index, set()).add(color)
    result = []
    for index, colors in sorted(clusters.items()):
        center = entries[index * 3:index * 3 + 3]
        result.append(min(colors, key=lambda rgb: (
            sum((a - b) ** 2 for a, b in zip(rgb, center)), rgb)))
    return tuple(dict.fromkeys(result))


def palette_image(colors):
    image = Image.new("P", (1, 1))
    padded = colors + (colors[0],) * (256 - len(colors))
    image.putpalette([value for color in padded for value in color])
    return image


def convert_logo():
    source = Image.open(RAW / "title-logo-v2-source.png").convert("RGBA")
    if source.getchannel("A").getextrema()[0] != 0:
        raise ValueError("Logo edit must have a real transparent background")
    source = source.crop(source.getchannel("A").getbbox())
    visible = [p[:3] for p in source.get_flattened_data() if p[3] >= 128]
    colors = source_palette(visible, 16)
    swatch = palette_image(colors)
    for filename, size in (("title-logo-v2.png", (192, 80)),
                           ("title-logo-small-v2.png", (144, 60))):
        scale = min((size[0] - 4) / source.width,
                    (size[1] - 4) / source.height)
        small = source.resize((round(source.width * scale),
                               round(source.height * scale)), Image.Resampling.BOX)
        rgb = small.convert("RGB").quantize(palette=swatch,
                                            dither=Image.Dither.NONE).convert("RGB")
        rgb.putalpha(small.getchannel("A").point(lambda a: 255 if a >= 128 else 0))
        output = Image.new("RGBA", size)
        output.paste(rgb, ((size[0] - rgb.width) // 2, (size[1] - rgb.height) // 2))
        actual = {p[:3] for p in output.get_flattened_data() if p[3]}
        if len(actual) > 16 or not actual.issubset(colors):
            raise ValueError("Logo palette drift")
        if set(output.getchannel("A").get_flattened_data()) != {0, 255}:
            raise ValueError("Logo alpha must stay binary")
        output.save(ROOT / "assets" / filename, optimize=True)
        print(f"assets/{filename}: {size[0]}x{size[1]}, {len(actual)} colors, binary alpha")


def flatten_sky(image):
    """Only the connected sky becomes cream, keeping enclosed wall details."""
    pixels = image.load()
    width, height = image.size
    seen = set()
    queue = deque((x, 0) for x in range(width))
    while queue:
        x, y = queue.popleft()
        if (x, y) in seen or not (0 <= x < width and 0 <= y < height):
            continue
        seen.add((x, y))
        r, g, b = pixels[x, y]
        if not (r > 180 and g > 170 and b > 115 and -8 < r - g < 45):
            continue
        pixels[x, y] = CREAM
        queue.extend(((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))
    if any(pixels[x, 0] != CREAM for x in range(width)):
        raise ValueError("Panorama's top edge must match the CSS sky")


def convert_scene():
    source = Image.open(RAW / "title-panorama-v2-source.png").convert("RGB")
    if abs(source.width / source.height - 3) > 0.01:
        raise ValueError("Panorama must retain its 3:1 framing")
    small = source.resize((1152, 384), Image.Resampling.BOX)
    flatten_sky(small)
    reserved = (CREAM, KHAKI, DARK, ORANGE)
    samples = [p for p in small.get_flattened_data() if p != CREAM]
    colors = tuple(dict.fromkeys(reserved + source_palette(samples, 28)))
    output = small.quantize(palette=palette_image(colors), dither=Image.Dither.NONE)
    if len(output.getcolors(256)) > 32 or "transparency" in output.info:
        raise ValueError("Panorama must stay opaque and <=32 colors")
    output.save(ROOT / "assets" / "title-scene-v2.png", optimize=True)
    print(f"assets/title-scene-v2.png: 1152x384, {len(output.getcolors(256))} colors, opaque")


if __name__ == "__main__":
    convert_logo()
    convert_scene()
