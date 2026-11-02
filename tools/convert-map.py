r"""Convert docs/mockups/map.png.png into a clean daytime pixel map without ruining original colors.

Run with: .venv\Scripts\python.exe tools\convert-map.py
- Preserves 100% of map.png.png's original brick, stone, roof, tree, and grass colors (no destructive 32-color quantization!).
- Replaces ONLY the 4 main buildings with the already-approved daytime sprites from assets/buildings/
  and recolors ONLY the pure bright-yellow window panes of small houses to muted sky-blue glass.
"""

from collections import deque
import io
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "assets" / "raw"
MOCKUPS = ROOT / "docs" / "mockups"
BUILDINGS = ROOT / "assets" / "buildings"

GLASS_SHADOW = (0x53, 0x6F, 0x7A)
GLASS_BASE = (0x7E, 0x9F, 0xAE)
GLASS_LIGHT = (0xB7, 0xCD, 0xD6)
SIGN_ORANGE = (0xD9, 0x84, 0x4E)
CREAM = (0xE6, 0xE1, 0xC6)


def convert_windows_only(img: Image.Image) -> Image.Image:
    """Keep all original map colors intact, changing ONLY bright yellow lit window panes
    to muted sky-blue glass (#7E9FAE / #B7CDD6 / #536F7A)."""
    out = img.copy()
    px = out.load()
    w, h = out.size

    # Protect the 4 main orange signs, red/orange awnings, flags, and delivery truck/ markings
    protected_boxes = (
        (138, 20, 176, 42),   # 촤지피티 laptop sign
        (78, 94, 110, 115),   # 대충통운 box sign
        (116, 171, 151, 193), # 쟤당치킨 chicken sign
        (24, 265, 49, 282),   # 취업센터 i sign
        (120, 38, 128, 56),   # 촤지피티 left flag
        (189, 38, 198, 56),   # 촤지피티 right flag
        (86, 180, 116, 208),  # 쟤당치킨 striped awnings & parasols
        (168, 180, 178, 202), # 쟤당치킨 right flag
        (45, 253, 56, 265),   # 취업센터 roof red flag
        (36, 114, 72, 146),   # delivery truck & yellow dock stripes
        (190, 190, 214, 226), # bus lane yellow road marking
        (18, 20, 34, 36),     # wooden crates in top-left yard
        # Front stone nameplate steps in front of the 4 buildings
        (138, 60, 176, 74),
        (78, 134, 110, 148),
        (116, 213, 150, 228),
        (22, 295, 52, 310),
    )

    # Exact window pane rectangles on the 4 main buildings + small houses + bus stop
    window_pane_boxes = (
        # 4 main buildings' glass window areas
        (126, 22, 190, 60),
        (70, 74, 118, 134),
        (98, 170, 166, 212),
        (18, 268, 56, 295),
        # Small houses' window panes only (not roofs or walls!)
        (92, 1, 103, 7),
        (206, 7, 215, 14),
        (26, 61, 39, 67),
        (12, 87, 28, 94),
        (201, 83, 214, 90),
        (172, 89, 190, 96),
        (171, 114, 185, 121),
        (0, 110, 10, 117),
        (1, 140, 21, 148),
        (28, 160, 41, 167),
        (2, 185, 17, 192),
        (34, 192, 45, 198),
        (20, 210, 37, 219),
        (200, 162, 214, 170),
        (164, 234, 182, 245), # bus stop interior glass
        (106, 285, 125, 293),
        (168, 278, 185, 295),
        # Lamp glass heads
        (95, 27, 100, 32),
        (29, 109, 34, 114),
        (123, 111, 128, 116),
        (51, 155, 56, 160),
        (9, 279, 14, 284),
        (93, 279, 98, 284),
    )

    def in_boxes(x, y, boxes):
        return any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in boxes)

    for y in range(h):
        for x in range(w):
            if in_boxes(x, y, protected_boxes):
                continue
            r, g, b = px[x, y]

            if in_boxes(x, y, window_pane_boxes):
                # Convert all glowing yellow/amber/pale-yellow window panes to daytime sky-blue glass
                if r >= 150 and g >= 100 and (r - b) >= 24 and r >= g - 4:
                    lum = (r + g + b) / 3
                    if lum > 205:
                        px[x, y] = GLASS_LIGHT
                    elif lum > 160:
                        px[x, y] = GLASS_BASE
                    else:
                        px[x, y] = GLASS_SHADOW
                continue

            # Outside window boxes: remove only pinpoint bright yellow-orange road bollard lights
            if r >= 210 and g >= 135 and (r - b) >= 75:
                px[x, y] = (0x9E, 0x63, 0x47)

    return out


def extract_tile_sprite(source: Image.Image, crop_box: tuple[int, int, int, int], target_size: tuple[int, int]) -> Image.Image:
    crop = source.crop(crop_box).convert("RGBA")
    w, h = crop.size
    data = list(crop.get_flattened_data())
    removed = bytearray(w * h)
    queue = deque()

    def is_bg(rgb):
        return min(rgb) >= 205 and (max(rgb) - min(rgb)) <= 35

    def enqueue(idx):
        if not removed[idx] and is_bg(data[idx][:3]):
            removed[idx] = 1
            queue.append(idx)

    for x in range(w):
        enqueue(x)
        enqueue((h - 1) * w + x)
    for y in range(h):
        enqueue(y * w)
        enqueue(y * w + w - 1)

    while queue:
        idx = queue.popleft()
        x, y = idx % w, idx // w
        if x > 0:
            enqueue(idx - 1)
        if x + 1 < w:
            enqueue(idx + 1)
        if y > 0:
            enqueue(idx - w)
        if y + 1 < h:
            enqueue(idx + w)

    fg = bytearray(0 if removed[i] else 1 for i in range(w * h))
    best_comp = []
    seen = bytearray(w * h)
    for start in range(w * h):
        if not fg[start] or seen[start]:
            continue
        comp = []
        q = deque([start])
        seen[start] = 1
        while q:
            cur = q.popleft()
            comp.append(cur)
            cx, cy = cur % w, cur // w
            for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                if 0 <= nx < w and 0 <= ny < h:
                    nb = ny * w + nx
                    if fg[nb] and not seen[nb]:
                        seen[nb] = 1
                        q.append(nb)
        if len(comp) > len(best_comp):
            best_comp = comp

    keep = set(best_comp)
    crop.putdata([data[i] if i in keep else (0, 0, 0, 0) for i in range(w * h)])
    bbox = crop.getchannel("A").getbbox()
    if bbox:
        crop = crop.crop(bbox)
    small = crop.resize(target_size, Image.Resampling.BOX)
    small.putdata([(p[0], p[1], p[2], 255) if p[3] >= 140 else (0, 0, 0, 0)
                   for p in small.get_flattened_data()])
    return small


def recolor_tree_to_map_palette(sprite: Image.Image) -> Image.Image:
    """Recolor a clean alpha-masked tree sprite so its foliage, trunk, and outline
    100% match day_map's dark muted olive/forest-green pixel palette (zero brightness/hue mismatch)."""
    out = sprite.copy().convert("RGBA")
    px = out.load()
    w, h = out.size

    # Exact tree & trunk palette sampled from day_map's native trees:
    OUTLINE = (24, 29, 24, 255)
    LEAF_DARK = (47, 61, 43, 255)
    LEAF_MID = (67, 84, 55, 255)
    LEAF_LIGHT = (90, 108, 68, 255)
    TRUNK_DARK = (68, 49, 38, 255)
    TRUNK_LIGHT = (98, 70, 52, 255)

    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 128:
                px[x, y] = (0, 0, 0, 0)
                continue
            lum = (r + g + b) / 3
            if lum < 58:
                px[x, y] = OUTLINE
            elif r > g + 8:
                # Brown trunk
                px[x, y] = TRUNK_LIGHT if lum > 105 else TRUNK_DARK
            else:
                # Foliage
                if lum > 138:
                    px[x, y] = LEAF_LIGHT
                elif lum > 96:
                    px[x, y] = LEAF_MID
                else:
                    px[x, y] = LEAF_DARK
    return out


def build_surround_from_center(day_map: Image.Image, city_tiles: Image.Image) -> Image.Image:
    """Build a calm, clean, seamless side extension matching day_map's exact colors."""
    pano_w, pano_h = 1152, 324
    c_left = (pano_w - 216) // 2  # 468
    c_right = c_left + 216        # 684

    # 1. Sample genuine grass base color from day_map (69, 82, 64)
    pano = Image.new("RGBA", (pano_w, pano_h), (69, 82, 64, 255))
    draw = ImageDraw.Draw(pano)

    # Subtle pixel-art grass tufts matching day_map's exact palette
    tuft_dark = (55, 67, 51, 255)
    tuft_light = (82, 96, 73, 255)
    for gy in range(4, pano_h - 4, 14):
        for gx in range(6, pano_w - 6, 18):
            if c_left - 4 <= gx <= c_right + 4:
                continue
            ox = ((gy * 13 + gx * 7) % 9) - 4
            oy = ((gx * 11 + gy * 5) % 7) - 3
            tx, ty = gx + ox, gy + oy
            draw.point((tx, ty), fill=tuft_dark)
            draw.point((tx + 1, ty), fill=tuft_dark)
            draw.point((tx, ty - 1), fill=tuft_light)

    dm_px = day_map.load()

    # Exact dark charcoal asphalt color from day_map's lower road intersection (x=72, y=242 -> ~50, 56, 58)
    asphalt_dark = dm_px[72, 242]
    asphalt_mid = dm_px[72, 231]
    curb_outline = (26, 31, 33, 255)
    curb_brick = (158, 99, 71, 255)
    curb_brick_hi = (176, 114, 82, 255)
    curb_joint = (122, 74, 52, 255)
    lane_dash = (206, 198, 174, 255)

    def draw_horizontal_road(x0: int, x1: int, y_top: int, y_bot: int, dash_y: int):
        """Draw a horizontal road with brick curbs and dashed center line matching day_map's dark road."""
        for y in range(y_top, y_bot + 1):
            for x in range(x0, x1):
                if y in (y_top, y_top + 5, y_bot - 5, y_bot):
                    pano.putpixel((x, y), curb_outline)
                elif y in (y_top + 1, y_bot - 4):
                    pano.putpixel((x, y), curb_joint if (x % 8 == 0) else curb_brick_hi)
                elif y in (y_top + 2, y_top + 3, y_top + 4, y_bot - 3, y_bot - 2, y_bot - 1):
                    pano.putpixel((x, y), curb_joint if (x % 8 == 0) else curb_brick)
                else:
                    if y in (dash_y, dash_y + 1) and ((x % 20) in range(6, 14)):
                        pano.putpixel((x, y), lane_dash)
                    elif y in (y_top + 6, y_bot - 6):
                        pano.putpixel((x, y), (*asphalt_mid, 255))
                    else:
                        pano.putpixel((x, y), (*asphalt_dark, 255))

    # Left-wing upper brick walkway continuation (y=46..54)
    for y in range(46, 55):
        for x in range(0, c_left):
            if y in (46, 54):
                pano.putpixel((x, y), curb_outline)
            elif y == 47:
                pano.putpixel((x, y), curb_joint if (x % 8 == 0) else curb_brick_hi)
            else:
                pano.putpixel((x, y), curb_joint if (x % 8 == 0) else curb_brick)

    # Left-wing lower main road continuation (y=223..251, center dash at y=237)
    draw_horizontal_road(0, c_left, 223, 251, 237)

    # Right-wing middle road continuation (y=96..128, center dash at y=111)
    draw_horizontal_road(c_right, pano_w, 96, 128, 111)

    # Right-wing lower road continuation (y=223..256, center dash at y=239)
    draw_horizontal_road(c_right, pano_w, 223, 256, 239)

    # 3. Paste center day_map at x=468..684
    pano.paste(day_map.convert("RGBA"), (c_left, 0))

    # 4. Extract clean alpha-masked trees and recolor them to day_map's exact muted tree palette
    tree_big = recolor_tree_to_map_palette(extract_tile_sprite(city_tiles, (12, 570, 176, 736), (26, 28)))
    tree_mid = recolor_tree_to_map_palette(extract_tile_sprite(city_tiles, (176, 580, 290, 736), (22, 25)))
    bush = recolor_tree_to_map_palette(extract_tile_sprite(city_tiles, (405, 636, 520, 736), (18, 12)))

    # Place trees calmly along roadsides and park areas
    left_trees = (
        (tree_big, 26, 10), (tree_mid, 102, 13), (tree_big, 184, 9), (tree_mid, 268, 13), (tree_big, 350, 10), (tree_mid, 424, 12),
        (tree_mid, 44, 64), (tree_big, 134, 60), (tree_mid, 228, 66), (tree_big, 318, 60), (bush, 408, 72),
        (tree_big, 22, 122), (tree_mid, 112, 126), (tree_big, 198, 118), (tree_mid, 288, 124), (tree_big, 376, 120),
        (bush, 62, 192), (tree_big, 148, 176), (tree_mid, 246, 180), (tree_big, 338, 176), (bush, 420, 192),
        (tree_big, 36, 268), (tree_mid, 124, 272), (tree_big, 212, 266), (tree_mid, 304, 272), (tree_big, 390, 268),
    )

    right_trees = (
        (tree_mid, 706, 12), (tree_big, 786, 10), (tree_mid, 874, 13), (tree_big, 960, 10), (tree_mid, 1050, 12),
        (bush, 716, 70), (tree_big, 776, 56), (tree_mid, 868, 60), (tree_big, 960, 56), (tree_mid, 1052, 60),
        (tree_big, 710, 142), (tree_mid, 800, 146), (tree_big, 892, 140), (tree_mid, 984, 146), (tree_big, 1072, 142),
        (bush, 712, 194), (tree_mid, 780, 182), (tree_big, 874, 178), (tree_mid, 970, 182), (bush, 1056, 194),
        (tree_mid, 714, 272), (tree_big, 806, 266), (tree_mid, 898, 272), (tree_big, 990, 266), (tree_mid, 1080, 272),
    )

    for sprite, x, y in left_trees + right_trees:
        pano.alpha_composite(sprite, (x, y))

    # 5. Soften the vertical boundary seams at x=c_left (468) and x=c_right (684)
    # where day_map's edge trees were cut in half by the 216px crop, by completing those trees across the border:
    seam_trees = (
        # Left seam (x around 454..468) completing half-clipped trees at y=0..24, y=32..56, y=126..152, y=282..312
        (tree_mid, c_left - 14, 0),
        (tree_big, c_left - 16, 22),
        (tree_mid, c_left - 14, 122),
        (bush, c_left - 12, 208),
        (tree_big, c_left - 16, 286),
        # Right seam (x around 674..686) completing half-clipped trees at y=0..24, y=132..160, y=260..316
        (tree_mid, c_right - 10, 0),
        (tree_big, c_right - 12, 134),
        (tree_mid, c_right - 10, 262),
        (tree_big, c_right - 12, 292),
    )
    for sprite, x, y in seam_trees:
        pano.alpha_composite(sprite, (x, y))

    return pano.convert("RGB")


def build_map_assets():
    mockup = Image.open(MOCKUPS / "map.png.png").convert("RGB")
    if mockup.size != (1024, 1536):
        raise ValueError(f"Unexpected map.png.png size: {mockup.size}")

    small = mockup.resize((216, 324), Image.Resampling.BOX)
    day_small = convert_windows_only(small)

    city_tiles = Image.open(RAW / "city-tiles.png").convert("RGBA")
    surround_raw = build_surround_from_center(day_small, city_tiles)

    def safe_save(im: Image.Image, target: Path):
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        if target.exists():
            target.unlink()
        target.write_bytes(buf.getvalue())

    safe_save(day_small, ROOT / "assets" / "map-bg.png")
    print(f"assets/map-bg.png: {day_small.size} saved")

    safe_save(surround_raw, ROOT / "assets" / "map-bg-surround.png")
    print(f"assets/map-bg-surround.png: {surround_raw.size} saved")


if __name__ == "__main__":
    build_map_assets()
