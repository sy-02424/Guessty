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


def reframe_panorama(source):
    """Bring the central street facades closer to match the portrait mockup framing
    while seamlessly continuing into the outer wings."""
    src_w, src_h = source.size
    center_x = src_w / 2.0
    out_w, out_h = 1152, 384
    # Vertical shift (-24px in 724px source, ~13px in 384px output) raises the
    # street horizon slightly to match the portrait mockup's road proportions.
    y_shift = round(src_h * 0.033)
    padded = Image.new("RGB", (src_w, src_h + y_shift), source.getpixel((0, 0)))
    padded.paste(source, (0, 0))
    # Map output x in [-576, 576] to source x in [-1086, 1086]:
    # In the central street zone (|u| <= 0.19, i.e. central 430px at 2x),
    # sample 1.30x wider so the awnings, chicken banner, lamp posts, and
    # tree trunks sit comfortably inside the mobile viewport, then ease
    # smoothly to the outer edges without any seam.
    u_knot = 0.19
    s_knot = 0.247
    strips = []
    for ox in range(out_w):
        u = (ox + 0.5 - out_w / 2.0) / (out_w / 2.0)
        au = abs(u)
        if au <= u_knot:
            t = au / u_knot
            su = s_knot * t
        else:
            t = (au - u_knot) / (1.0 - u_knot)
            # Hermite blend from slope (s_knot / u_knot) to endpoints
            m0 = (s_knot / u_knot) * (1.0 - u_knot)
            m1 = 1.0 - s_knot
            h00 = 2 * t ** 3 - 3 * t ** 2 + 1
            h10 = t ** 3 - 2 * t ** 2 + t
            h01 = -2 * t ** 3 + 3 * t ** 2
            h11 = t ** 3 - t ** 2
            su = s_knot * h00 + m0 * h10 + 1.0 * h01 + m1 * h11
        if u < 0:
            su = -su
        sx = center_x + su * (src_w / 2.0)
        x0 = max(0, min(src_w - 2, int(sx - 1)))
        x1 = min(src_w, max(x0 + 1, int(sx + 1)))
        col = padded.crop((x0, y_shift, x1, src_h + y_shift)).resize(
            (1, out_h), Image.Resampling.BOX)
        strips.append(col)
    small = Image.new("RGB", (out_w, out_h))
    for ox, col in enumerate(strips):
        small.paste(col, (ox, 0))
    return small


def convert_scene():
    source = Image.open(RAW / "title-panorama-v2-source.png").convert("RGB")
    if abs(source.width / source.height - 3) > 0.01:
        raise ValueError("Panorama must retain its 3:1 framing")
    small = reframe_panorama(source)
    flatten_sky(small)
    reserved = (CREAM, KHAKI, DARK, ORANGE)
    samples = [p for p in small.get_flattened_data() if p != CREAM]
    colors = tuple(dict.fromkeys(reserved + source_palette(samples, 28)))
    output = small.quantize(palette=palette_image(colors), dither=Image.Dither.NONE)
    if len(output.getcolors(256)) > 32 or "transparency" in output.info:
        raise ValueError("Panorama must stay opaque and <=32 colors")
    output.save(ROOT / "assets" / "title-bg-surround.png", optimize=True)
    print(f"assets/title-bg-surround.png: 1152x384, {len(output.getcolors(256))} colors, opaque")


if __name__ == "__main__":
    convert_logo()
    convert_scene()
