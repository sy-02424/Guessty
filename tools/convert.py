"""Rebuild GUESSTY sprites from the local originals (Python 3.11+).

From the repository root:
    python -m pip install -r tools/requirements.txt
    python tools/convert.py

Paths are relative to this file, so invocation from another directory also works.
Logo: fixed DESIGN.md six colors. Characters: <=16 original colors per sheet.
Buildings: original 16 colors plus five approved, locally masked corrections
(<=21 shared colors). All palette conversions use no dithering.
Originals and previews stay under the existing assets/raw/ gitignore rule.
All coordinates below are SOURCE pixels, with right/bottom crop edges exclusive.
"""

from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import sys

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    raise SystemExit("Install Pillow: python -m pip install -r tools/requirements.txt")


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "assets" / "raw"
PREVIEW = RAW / "preview"
# DESIGN.md sections 2 and 4: the fixed six-color palette is LOGO ONLY.
PALETTE = (
    (0x2F, 0x33, 0x26),  # dark
    (0x44, 0x52, 0x3A),  # olive
    (0x66, 0x6F, 0x54),  # khaki
    (0xE6, 0xE1, 0xC6),  # cream
    (0xD9, 0x84, 0x4E),  # orange
    (0x46, 0xA0, 0x8E),  # mint
)
SOURCE_SIZES = {
    "logo-source.png": (808, 376),
    "city-tiles.png": (1536, 1024),
    "characters-base.png": (1086, 1448),
}
WHITE_MIN = 220
WHITE_MAX_SPREAD = 28
LOGO_OUTLINE_MAX = 52
LOGO_OUTLINE_SPREAD = 18
ALPHA_CUTOFF = 128
MAX_SOURCE_COLORS = 16  # transparent pixels do not consume a visible color
MAX_BUILDING_COLORS = 21
PREVIEW_SCALE = 4
PADDING = 1  # transparent pixels on every side; feet align at height - 2
# Reserve representative original colors for small but important materials.
# Each patch is quantized with MEDIANCUT too; no hand-picked replacement RGBs.
SOURCE_COLOR_REGIONS = {
    "city-tiles.png": ((160, 270, 183, 288), (163, 299, 185, 312),
                       (280, 62, 325, 80), (1435, 110, 1465, 123)),
    "characters-base.png": ((315, 815, 350, 835), (320, 710, 370, 745),
                            (345, 900, 360, 940), (270, 891, 285, 941),
                            (690, 940, 740, 955)),
}


@dataclass(frozen=True)
class Sprite:
    name: str
    source: str
    crop: tuple[int, int, int, int]
    size: tuple[int, int]
    output: str
    # A polygon follows the complete blank plate, including its dark outline.
    plate: tuple[tuple[int, int], ...] = ()
    # White sky enclosed by props needs an explicit seed, not a global white key.
    background_seeds: tuple[tuple[int, int], ...] = ()


SPRITES = (
    Sprite("logo", "logo-source.png", (28, 56, 800, 330), (192, 72), "assets/logo.png"),
    Sprite(
        "company-chicken", "city-tiles.png", (24, 16, 420, 374), (128, 128),
        "assets/buildings/company-chicken.png",
        ((207, 325), (307, 325), (319, 337), (319, 354),
         (308, 366), (203, 366), (191, 354), (191, 337)),
        background_seeds=((100, 220),),
    ),
    Sprite(
        "company-box", "city-tiles.png", (424, 8, 842, 374), (128, 128),
        "assets/buildings/company-box.png",
        ((670, 323), (768, 323), (784, 336), (784, 354),
         (773, 363), (666, 363), (655, 354), (655, 336)),
    ),
    Sprite(
        "company-laptop", "city-tiles.png", (850, 8, 1212, 374), (128, 128),
        "assets/buildings/company-laptop.png",
        ((968, 323), (1078, 323), (1095, 337), (1095, 354),
         (1083, 363), (965, 363), (952, 354), (952, 337)),
    ),
    Sprite(
        "career-center", "city-tiles.png", (1226, 78, 1512, 350), (96, 96),
        "assets/buildings/career-center.png",
        ((1307, 296), (1418, 296), (1434, 309), (1434, 331),
         (1424, 340), (1300, 340), (1291, 331), (1291, 309)),
    ),
    Sprite(
        "hero-front", "characters-base.png", (240, 668, 468, 1084), (32, 64),
        "assets/hero-front.png",
    ),
    Sprite(
        "hero-back", "characters-base.png", (612, 668, 848, 1084), (32, 64),
        "assets/hero-back.png",
    ),
)

# Exclude only the button; cropping this whole row would cut the G and Y tails.
LOGO_BUTTON = (245, 283, 580, 334)
# Each letter face and the sparkle must remain enclosed by its dark outline.
# Flood fill visits the olive field AND clouds, rather than globally keying cream.
LOGO_ANCHORS = ((100, 170), (220, 150), (340, 130), (440, 140),
                (530, 160), (620, 160), (710, 190), (756, 98))

# Recolor masks are FINAL sprite pixels, at the fixed SPRITES canvas sizes.
# Keeping the original 16-color render intact guarantees identical pixels
# outside these masks and identical alpha everywhere. Glass masks omit lamps,
# vehicles, steps, foliage, wall trim, and mullions (which also keep their RGBs).
BUILDING_REGIONS = {
    "company-chicken": {
        "glass": (
            ((35, 45), (52, 50), (52, 55), (35, 51)),
            ((60, 63), (90, 63), (90, 69), (60, 69)),
            ((35, 68), (39, 69), (39, 77), (35, 75)),
            ((43, 69), (53, 71), (53, 87), (43, 85)),
            ((97, 46), (102, 45), (102, 88), (97, 90)),
            ((106, 43), (116, 36), (116, 85), (106, 89)),
            ((68, 85), (84, 85), (84, 97), (68, 97)),
        ),
        "sign": (((55, 38), (90, 38), (94, 41), (94, 56), (90, 59),
                  (55, 59), (53, 56), (53, 41)),),
        "icon": (((64, 51), (69, 50), (71, 48), (72, 44), (75, 40),
                  (78, 39), (82, 40), (85, 42), (87, 45), (87, 49),
                  (84, 51), (78, 52), (74, 52), (71, 55), (69, 57), (65, 55)),),
        "flesh": (((71, 48), (72, 44), (75, 40), (78, 39), (82, 40),
                   (85, 42), (87, 45), (87, 49), (84, 51), (78, 52), (74, 52)),),
    },
    "company-box": {
        "glass": (
            ((62, 63), (69, 63), (69, 69), (62, 69)),
            ((62, 75), (69, 75), (69, 80), (62, 80)),
            ((62, 86), (69, 86), (69, 91), (62, 91)),
            ((76, 73), (104, 73), (104, 80), (76, 80)),
            ((84, 92), (99, 92), (99, 102), (84, 102)),
            ((113, 64), (120, 59), (120, 91), (113, 97)),
            ((41, 38), (44, 35), (82, 35), (79, 38)),  # rooftop skylights
        ),
        "sign": (((73, 52), (76, 50), (106, 50), (109, 53), (109, 65),
                  (106, 68), (73, 68), (71, 65), (71, 55)),),
        "icon": (((80, 55), (89, 51), (98, 55), (98, 62), (89, 67), (80, 63)),),
        "lid": (((84, 55), (89, 53), (95, 55), (89, 57)),),
        "left_face": (((82, 57), (87, 59), (87, 64), (82, 62)),),
        "right_face": (((91, 60), (96, 57), (96, 61), (91, 64)),),
    },
    "company-laptop": {
        "glass": (
            ((12, 53), (32, 56), (32, 63), (12, 60)),
            ((18, 71), (33, 71), (33, 80), (18, 80)),
            ((18, 91), (33, 91), (33, 99), (18, 99)),
            ((42, 71), (80, 71), (80, 80), (42, 80)),
            ((88, 44), (113, 38), (113, 97), (88, 100)),
            ((50, 98), (69, 98), (69, 110), (50, 110)),
        ),
        "sign": (((36, 38), (82, 38), (86, 42), (86, 59), (82, 62),
                  (36, 62), (34, 59), (34, 41)),),
        "icon": (((52, 40), (70, 40), (70, 54), (67, 58),
                  (47, 58), (47, 55), (52, 51)),),
        "screen": (((54, 43), (68, 43), (68, 50), (54, 50)),),
    },
    "career-center": {
        "glass": (
            ((20, 56), (28, 56), (28, 63), (20, 63)),
            ((64, 56), (71, 56), (71, 63), (64, 63)),
            ((37, 60), (53, 60), (53, 74), (37, 74)),
        ),
        "sign": (((31, 36), (40, 28), (49, 28), (59, 37),
                  (60, 48), (31, 48)),),
        "icon": (
            ((44, 32), (48, 32), (48, 34), (44, 34)),
            ((44, 37), (48, 37), (48, 43), (49, 43), (49, 45),
             (43, 45), (43, 43), (44, 43)),
        ),
    },
}

# User-approved replacement for the initial mint proposal: muted sky blue.
GLASS_SHADOW = (0x53, 0x6F, 0x7A)
GLASS_BASE = (0x7E, 0x9F, 0xAE)
GLASS_LIGHT = (0xB7, 0xCD, 0xD6)
SIGN_ORANGE = (0xD9, 0x84, 0x4E)
ICON_DARK = (0x2F, 0x33, 0x26)
ICON_BROWN = (0x7A, 0x57, 0x41)  # reuse P11, not a sixth additional color
ICON_CREAM = (0xF8, 0xDE, 0x98)  # reuse P05
ICON_GRAY = (0x6C, 0x69, 0x67)  # reuse P03
GLASS_MAP = {
    (0xF8, 0xDE, 0x98): GLASS_LIGHT,
    (0xF3, 0xC8, 0x7A): GLASS_BASE,
    (0xED, 0xB9, 0x6C): GLASS_BASE,
    (0xCE, 0xA3, 0x62): GLASS_SHADOW,
}
# Reduction blended some yellow glass edges into these orange/red-brown
# source entries. Correct them ONLY inside glass masks, never on signs/props.
GLASS_EDGE_MAP = {
    (0xC1, 0x7E, 0x55): GLASS_SHADOW,
    (0xDE, 0x60, 0x45): GLASS_SHADOW,
}
GLASS_RECOLOR_MAP = GLASS_MAP | GLASS_EDGE_MAP
# Final-pixel rectangles (right/bottom exclusive): actual door handles/jamb.
# Dark brown mullions and frames are also preserved by excluding their colors
# from GLASS_RECOLOR_MAP, instead of recoloring every brown pixel globally.
GLASS_DETAILS = {
    "company-chicken": ((74, 91, 78, 92),),
    "company-box": ((99, 92, 100, 103),),
    "career-center": ((44, 66, 45, 68),),
}
BUILDING_EXTRA_COLORS = (GLASS_SHADOW, GLASS_BASE, GLASS_LIGHT, SIGN_ORANGE, ICON_DARK)

# Leaf silhouettes stop above planter rims; warm flecks inside the foliage
# are texture noise, while the pots, lamps and facade accents stay separate.
FOLIAGE_REGIONS = {
    "company-chicken": (
        ((40, 96), (43, 91), (50, 89), (56, 92), (58, 99), (54, 102), (40, 102)),
        ((93, 94), (98, 88), (108, 88), (113, 83), (120, 83), (124, 87),
         (124, 96), (115, 100), (103, 101), (93, 100)),
    ),
    "company-box": (
        ((54, 98), (57, 94), (66, 95), (70, 99), (69, 102), (55, 102)),
        ((108, 97), (112, 93), (120, 94), (124, 99), (124, 102), (110, 102)),
    ),
    "company-laptop": (
        ((6, 106), (10, 100), (20, 99), (27, 103), (29, 109), (24, 111), (9, 111)),
        ((95, 103), (101, 98), (112, 98), (119, 101), (120, 109), (114, 111), (99, 111)),
    ),
    "career-center": (
        ((6, 71), (10, 68), (19, 68), (25, 71), (27, 75), (24, 78), (9, 78), (5, 76)),
        ((63, 72), (68, 68), (77, 69), (83, 65), (89, 65), (92, 70),
         (91, 76), (85, 79), (67, 79)),
    ),
}

# Top/front planes of entry canopies and planter bases. Palette reduction
# previously turned the source's soft shading into unrelated-looking patches.
# Preserve their dark edges and replace only the continuous material faces.
SURFACE_PLANES = {
    "company-chicken": (
        ("cream", ((55, 71), (91, 71), (94, 73), (54, 73))),
        ("gray_mid", ((55, 74), (93, 74), (93, 76), (55, 76))),
        ("gray", ((10, 109), (32, 110), (32, 114), (16, 114))),
        ("gray", ((37, 108), (52, 108), (52, 114), (37, 114))),
        ("gray", ((94, 109), (110, 108), (110, 113), (94, 114))),
    ),
    "company-box": (
        ("cream", ((72, 82), (109, 82), (109, 83), (72, 83))),
        ("gray_mid", ((72, 84), (108, 84), (108, 86), (72, 86))),
        ("gray", ((55, 106), (69, 106), (69, 110), (55, 110))),
        ("gray", ((112, 106), (123, 105), (123, 109), (112, 110))),
    ),
    "company-laptop": (
        ("cream", ((34, 83), (85, 83), (85, 85), (33, 85))),
        ("gray_mid", ((34, 86), (85, 86), (85, 88), (34, 88))),
        ("gray", ((5, 114), (30, 114), (30, 119), (5, 119))),
        ("gray", ((91, 114), (115, 114), (115, 119), (91, 119))),
    ),
    "career-center": (
        ("gray", ((9, 82), (28, 83), (28, 88), (13, 88))),
        ("gray", ((62, 83), (80, 83), (80, 88), (62, 88))),
    ),
}


def clean_building_materials(image, spec):
    """Consolidate material tones and remove tiny color islands, without blur.

    Keep approved glass, signs and icons byte-identical. Structural dark strokes
    and transparent silhouettes never get filtered; color cleanup operates on
    discrete palette indices and only merges related material tones.
    """
    masks = building_masks(spec)
    protected = Image.new("L", spec.size)
    protected.putdata([max(values) for values in zip(
        masks["glass"].get_flattened_data(), masks["sign"].get_flattened_data(),
        masks["icon"].get_flattened_data(), masks["glass_details"].get_flattened_data())])
    cream, tan = ICON_CREAM, (0xCE, 0xA3, 0x62)
    gray, gray_mid, shadow = ICON_GRAY, (0x7A, 0x74, 0x64), (0x3C, 0x41, 0x40)
    leaf, leaf_shadow = (0x7B, 0x84, 0x46), (0x41, 0x51, 0x35)
    simplify = {
        (0xF3, 0xC8, 0x7A): cream,
        (0xED, 0xB9, 0x6C): tan,
        (0xC1, 0x7E, 0x55): ICON_BROWN,
        (0x52, 0x4D, 0x45): shadow,
        (0x23, 0x2A, 0x2C): ICON_DARK,
        (0x14, 0x19, 0x1C): ICON_DARK,
        (0x0B, 0x0F, 0x12): ICON_DARK,
    }
    result = image.copy()
    pixels = result.load()
    for y in range(result.height):
        for x in range(result.width):
            pixel = image.getpixel((x, y))
            if pixel[3] and not protected.getpixel((x, y)):
                pixels[x, y] = (*simplify.get(pixel[:3], pixel[:3]), pixel[3])

    foliage = Image.new("L", spec.size)
    draw = ImageDraw.Draw(foliage)
    for polygon in FOLIAGE_REGIONS[spec.name]:
        draw.polygon(polygon, fill=255)
    # Correct brown/yellow flecks only where neighboring pixels confirm leaves.
    snapshot = result.copy()
    for y in range(1, result.height - 1):
        for x in range(1, result.width - 1):
            color = snapshot.getpixel((x, y))
            if not foliage.getpixel((x, y)) or protected.getpixel((x, y)) or not color[3]:
                continue
            neighbors = [snapshot.getpixel((nx, ny))[:3]
                         for ny in range(y - 1, y + 2) for nx in range(x - 1, x + 2)]
            if color[:3] in (cream, tan, ICON_BROWN, gray_mid, gray) and sum(
                    value in (leaf, leaf_shadow) for value in neighbors) >= 2:
                replacement = leaf if sum(color[:3]) >= 300 else leaf_shadow
                pixels[x, y] = (*replacement, color[3])

    # Mode filtering palette INDICES avoids RGB blur and new intermediate colors.
    palette = tuple(sorted({p[:3] for p in result.get_flattened_data()}))
    indices = {color: index for index, color in enumerate(palette)}
    families = {color: group for group, colors in enumerate(
        ((cream, tan), (gray, gray_mid, shadow), (leaf, leaf_shadow))) for color in colors}
    for _ in range(2):
        snapshot = result.copy()
        indexed = Image.new("L", result.size)
        indexed.putdata([indices[p[:3]] for p in snapshot.get_flattened_data()])
        mode = indexed.filter(ImageFilter.ModeFilter(3))
        for y in range(1, result.height - 1):
            for x in range(1, result.width - 1):
                pixel = snapshot.getpixel((x, y))
                if not pixel[3] or protected.getpixel((x, y)):
                    continue
                current, replacement = pixel[:3], palette[mode.getpixel((x, y))]
                if current in families and families[current] == families.get(replacement):
                    pixels[x, y] = (*replacement, pixel[3])

    materials = {"cream": cream, "gray": gray, "gray_mid": gray_mid}
    face_colors = {cream, tan, gray, gray_mid, shadow, ICON_BROWN}
    for material, polygon in SURFACE_PLANES[spec.name]:
        plane = Image.new("L", spec.size)
        ImageDraw.Draw(plane).polygon(polygon, fill=255)
        for y in range(result.height):
            for x in range(result.width):
                pixel = result.getpixel((x, y))
                if (plane.getpixel((x, y)) and not protected.getpixel((x, y))
                        and pixel[3] and pixel[:3] in face_colors):
                    pixels[x, y] = (*materials[material], pixel[3])

    for y in range(image.height):
        for x in range(image.width):
            if protected.getpixel((x, y)) and image.getpixel((x, y)) != result.getpixel((x, y)):
                raise ValueError(f"Material cleanup changed protected detail: {spec.name}")
    if image.getchannel("A").tobytes() != result.getchannel("A").tobytes():
        raise ValueError(f"Material cleanup changed silhouette: {spec.name}")
    return result


def building_masks(spec):
    masks = {}
    for role, polygons in BUILDING_REGIONS[spec.name].items():
        mask = Image.new("L", spec.size)
        draw = ImageDraw.Draw(mask)
        for polygon in polygons:
            draw.polygon(polygon, fill=255)
        masks[role] = mask
    details = Image.new("L", spec.size)
    draw = ImageDraw.Draw(details)
    for left, top, right, bottom in GLASS_DETAILS.get(spec.name, ()):
        draw.rectangle((left, top, right - 1, bottom - 1), fill=255)
    masks["glass_details"] = details
    return masks


def recolor_building(before, spec, palette):
    masks = building_masks(spec)
    result = before.copy()
    pixels = result.load()
    brown_detail = (0xC1, 0x7E, 0x55)
    for y in range(before.height):
        for x in range(before.width):
            r, g, b, alpha = before.getpixel((x, y))
            if not alpha:
                continue
            color = (r, g, b)
            replacement = color
            glass = masks["glass"].getpixel((x, y))
            protected = masks["glass_details"].getpixel((x, y))
            if glass and not protected and color in GLASS_RECOLOR_MAP:
                replacement = GLASS_RECOLOR_MAP[color]
            if masks["sign"].getpixel((x, y)) and not masks["icon"].getpixel((x, y)):
                if color in GLASS_MAP and color != ICON_CREAM:
                    replacement = SIGN_ORANGE
            if masks["icon"].getpixel((x, y)):
                if spec.name == "career-center" or max(color) < 155:
                    replacement = ICON_DARK
                elif spec.name == "company-chicken":
                    if masks["flesh"].getpixel((x, y)):
                        replacement = ICON_BROWN
                    elif color in GLASS_MAP:
                        replacement = ICON_CREAM
                elif spec.name == "company-box":
                    if color == brown_detail:
                        replacement = ICON_BROWN
                    elif color == (0xCE, 0xA3, 0x62):
                        replacement = ICON_BROWN
                    elif color in GLASS_MAP:
                        replacement = ICON_CREAM
                elif spec.name == "company-laptop":
                    if masks["screen"].getpixel((x, y)) and color in GLASS_MAP:
                        replacement = GLASS_MAP[color]
                    elif color in GLASS_MAP or color == brown_detail:
                        replacement = ICON_GRAY
                # Keep the original cube silhouette; distinguish its small
                # faces even where reduction blended them with dark outlines.
                if spec.name == "company-box":
                    if masks["lid"].getpixel((x, y)) or masks["left_face"].getpixel((x, y)):
                        replacement = ICON_CREAM
                    elif masks["right_face"].getpixel((x, y)):
                        replacement = ICON_BROWN
            pixels[x, y] = (*replacement, alpha)
            if replacement != color and not any(masks[role].getpixel((x, y))
                                                 for role in ("glass", "sign", "icon")):
                raise ValueError(f"Change outside approved masks: {spec.name} {(x, y)}")
    if before.getchannel("A").tobytes() != result.getchannel("A").tobytes():
        raise ValueError(f"Recolor changed alpha: {spec.name}")
    # Validate the actual result, not just that the four original yellows were
    # mapped. This catches unmapped orange fringes on future script changes.
    for y in range(result.height):
        for x in range(result.width):
            if masks["glass_details"].getpixel((x, y)):
                if result.getpixel((x, y)) != before.getpixel((x, y)):
                    raise ValueError(f"Glass detail changed: {spec.name} {(x, y)}")
            elif masks["glass"].getpixel((x, y)) and not masks["icon"].getpixel((x, y)):
                pixel = result.getpixel((x, y))
                red, green, blue = pixel[:3]
                # Independent of mapping keys: removing a mapping must not
                # also remove the ability to detect its remaining warm fringe.
                warm = red > green + 20 and green > blue + 10
                if pixel[3] and warm and pixel[:3] != ICON_BROWN:
                    raise ValueError(f"Warm glass fringe remains: {spec.name} {(x, y)}")
    validate(result, spec, palette)
    return result


def edge_flood_clear(image: Image.Image, eligible, seeds=()) -> Image.Image:
    """Four-connected fill seeded on ALL image edges; interiors stay protected."""
    width, height = image.size
    pixels = image.get_flattened_data()
    # A second pass after plate removal can reach newly exposed white pockets.
    candidates = bytearray(pixel[3] == 0 or bool(eligible(pixel[:3])) for pixel in pixels)
    removed = bytearray(width * height)
    queue = deque()

    def enqueue(index):
        if candidates[index] and not removed[index]:
            removed[index] = 1
            queue.append(index)

    for x in range(width):
        enqueue(x)
        enqueue((height - 1) * width + x)
    for y in range(height):
        enqueue(y * width)
        enqueue(y * width + width - 1)
    for x, y in seeds:
        index = y * width + x
        if not candidates[index]:
            raise ValueError(f"Background seed is not background: {(x, y)}")
        enqueue(index)
    while queue:
        index = queue.popleft()
        x, y = index % width, index // width
        if x:
            enqueue(index - 1)
        if x + 1 < width:
            enqueue(index + 1)
        if y:
            enqueue(index - width)
        if y + 1 < height:
            enqueue(index + width)

    result = image.copy()
    result.putdata([(0, 0, 0, 0) if removed[i] else pixel
                    for i, pixel in enumerate(pixels)])
    return result


def erase_source_shape(image, spec, *, polygon=(), rectangle=None):
    """Apply a source-coordinate removal mask without changing the original."""
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    left, top = spec.crop[:2]
    if polygon:
        draw.polygon([(x - left, y - top) for x, y in polygon], fill=255)
    if rectangle:
        x0, y0, x1, y1 = rectangle
        draw.rectangle((x0 - left, y0 - top, x1 - left - 1, y1 - top - 1), fill=255)
    result = image.copy()
    result.paste((0, 0, 0, 0), (0, 0), mask)
    return result


def clear_plate_fragments(image, spec):
    """Remove detached flecks near the plate, preserving attached steps/plinths."""
    xs, ys = zip(*spec.plate)
    left = max(0, min(xs) - spec.crop[0] - 8)
    top = max(0, min(ys) - spec.crop[1] - 2)
    right = min(image.width, max(xs) - spec.crop[0] + 9)
    bottom = min(image.height, max(ys) - spec.crop[1] + 9)
    alpha = bytearray(image.getchannel("A").tobytes())
    seen = set()
    for y in range(top, bottom):
        for x in range(left, right):
            start = y * image.width + x
            if not alpha[start] or start in seen:
                continue
            component, queue = [], deque([start])
            seen.add(start)
            attached = False
            while queue:
                index = queue.popleft()
                component.append(index)
                cx, cy = index % image.width, index // image.width
                if cx in (left, right - 1) or cy in (top, bottom - 1):
                    attached = True
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if left <= nx < right and top <= ny < bottom:
                        neighbor = ny * image.width + nx
                        if alpha[neighbor] and neighbor not in seen:
                            seen.add(neighbor)
                            queue.append(neighbor)
            if not attached:
                for index in component:
                    alpha[index] = 0
    image.putalpha(Image.frombytes("L", image.size, bytes(alpha)))
    return image


def retain_logo_components(image, spec):
    """Drop isolated background flecks; keep every component containing a face.

    These source-coordinate anchors are protection masks, not generated pixels.
    They preserve the separated sparkle as well as all seven original letters.
    """
    width, height = image.size
    opaque = bytearray(bool(a) for a in image.getchannel("A").get_flattened_data())
    keep = bytearray(width * height)
    queue = deque()
    for sx, sy in LOGO_ANCHORS:
        x, y = sx - spec.crop[0], sy - spec.crop[1]
        index = y * width + x
        if not opaque[index]:
            raise ValueError(f"Logo foreground anchor lost: {(sx, sy)}")
        if not keep[index]:
            keep[index] = 1
            queue.append(index)
    while queue:
        index = queue.popleft()
        x, y = index % width, index // width
        neighbors = []
        if x:
            neighbors.append(index - 1)
        if x + 1 < width:
            neighbors.append(index + 1)
        if y:
            neighbors.append(index - width)
        if y + 1 < height:
            neighbors.append(index + width)
        for neighbor in neighbors:
            if opaque[neighbor] and not keep[neighbor]:
                keep[neighbor] = 1
                queue.append(neighbor)
    image.putalpha(Image.frombytes("L", image.size, bytes(255 * v for v in keep)))
    return image


def extract(source, spec):
    crop = source.crop(spec.crop)
    if spec.name == "logo":
        def background(rgb):
            # Neutral near-black pixels form the original protection outlines;
            # olive background and light clouds are allowed to flood together.
            return not (max(rgb) <= LOGO_OUTLINE_MAX
                        and max(rgb) - min(rgb) <= LOGO_OUTLINE_SPREAD)

        image = edge_flood_clear(crop, background)
        image = erase_source_shape(image, spec, rectangle=LOGO_BUTTON)
        image = retain_logo_components(image, spec)
    else:
        image = edge_flood_clear(
            crop, lambda rgb: min(rgb) >= WHITE_MIN
            and max(rgb) - min(rgb) <= WHITE_MAX_SPREAD,
            seeds=tuple((x - spec.crop[0], y - spec.crop[1])
                        for x, y in spec.background_seeds),
        )
        if spec.plate:
            image = erase_source_shape(image, spec, polygon=spec.plate)
            image = edge_flood_clear(
                image, lambda rgb: min(rgb) >= WHITE_MIN
                and max(rgb) - min(rgb) <= WHITE_MAX_SPREAD,
            )
            image = clear_plate_fragments(image, spec)
    bounds = image.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError(f"Empty extraction: {spec.name}")
    return crop, image.crop(bounds)


@lru_cache(maxsize=65536)
def nearest_color(rgb, palette=PALETTE):
    # Stable palette-order tie break, squared RGB distance, no dithering.
    return min(palette, key=lambda color: sum((a - b) ** 2
                                            for a, b in zip(rgb, color)))


def source_palette(images, color_samples=(), max_colors=MAX_SOURCE_COLORS):
    """MEDIANCUT on foreground only; snap each centroid to an actual source RGB.

    Preserve frequency weighting and stable sprite/pixel order. Each cluster's
    representative is its closest original pixel (RGB-order tie break).
    Background, removed nameplates, and unrelated sheet sprites are excluded.
    """
    pixels = [pixel[:3] for image in images for pixel in image.get_flattened_data()
              if pixel[3] >= ALPHA_CUTOFF]
    if not pixels:
        raise ValueError("Cannot learn a palette from empty foregrounds")
    strip = Image.new("RGB", (len(pixels), 1))
    strip.putdata(pixels)
    # A few material samples protect skin/foliage/cloth/roof/flag colors from
    # being lost to the much larger dark-outline regions in a global histogram.
    reserved = tuple(dict.fromkeys(source_palette([sample], max_colors=1)[0]
                                   for sample in color_samples))
    quantized = strip.quantize(colors=max_colors - len(reserved),
                              method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    clusters = {}
    for rgb, index in zip(pixels, quantized.get_flattened_data()):
        clusters.setdefault(index, set()).add(rgb)
    entries = quantized.getpalette()
    palette = list(reserved)
    for index, colors in sorted(clusters.items()):
        centroid = tuple(entries[index * 3:index * 3 + 3])
        representative = min(colors, key=lambda rgb: (
            sum((a - b) ** 2 for a, b in zip(rgb, centroid)), rgb))
        if representative not in palette:
            palette.append(representative)
    return tuple(palette)


def render(image, spec, scale, palette):
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    # Pillow resamples RGBA in premultiplied alpha, avoiding dark edge fringes.
    small = image.resize(size, Image.Resampling.BOX)
    small.putdata([(*nearest_color(pixel[:3], palette), 255) if pixel[3] >= ALPHA_CUTOFF
                   else (0, 0, 0, 0) for pixel in small.get_flattened_data()])
    bounds = small.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError(f"Empty reduced sprite: {spec.name}")
    small = small.crop(bounds)
    canvas = Image.new("RGBA", spec.size, (0, 0, 0, 0))
    x = (canvas.width - small.width) // 2
    y = (canvas.height - PADDING - small.height if spec.name.startswith("hero-")
         else (canvas.height - small.height) // 2)
    canvas.paste(small, (x, y))
    validate(canvas, spec, palette)
    return canvas


def validate(image, spec, palette):
    if image.mode != "RGBA" or image.size != spec.size:
        raise ValueError(f"Incorrect PNG format/size: {spec.name}")
    colors = set(image.get_flattened_data())
    if not colors or not any(pixel[3] for pixel in colors):
        raise ValueError(f"No visible pixels: {spec.name}")
    if any(pixel[3] not in (0, 255) for pixel in colors):
        raise ValueError(f"Non-binary alpha: {spec.name}")
    visible = {pixel[:3] for pixel in colors if pixel[3]}
    limit = (len(PALETTE) if spec.name == "logo" else
             MAX_BUILDING_COLORS if spec.plate else MAX_SOURCE_COLORS)
    if len(visible) > limit or not visible.issubset(palette):
        raise ValueError(f"Color outside source palette / color limit: {spec.name}")
    bounds = image.getchannel("A").getbbox()
    if (bounds[0] < PADDING or bounds[1] < PADDING
            or bounds[2] > image.width - PADDING
            or bounds[3] > image.height - PADDING):
        raise ValueError(f"Missing transparent margin: {spec.name}")


def checkerboard(size):
    image = Image.new("RGBA", size, (238, 238, 238, 255))
    draw = ImageDraw.Draw(image)
    for y in range(0, image.height, 16):
        for x in range(0, image.width, 16):
            if (x // 16 + y // 16) % 2:
                draw.rectangle((x, y, x + 15, y + 15), fill=(200, 200, 200, 255))
    return image


def comparison(spec, crop, result, before=None, source_label="SOURCE CROP"):
    """Unmodified original crop at left, exact nearest-neighbor 4x sprite at right."""
    panel_size = (result.width * PREVIEW_SCALE, result.height * PREVIEW_SCALE)
    gap, header = 16, 80
    columns = 3 if before is not None else 2
    sheet = Image.new("RGB", (panel_size[0] * columns + gap * (columns + 1),
                              panel_size[1] + header + gap), "#25282c")
    draw = ImageDraw.Draw(sheet)
    title_font = ImageFont.load_default(size=16)
    label_font = ImageFont.load_default(size=13)
    draw.text((gap, 10), spec.name, font=title_font, fill="white")
    draw.text((gap, 38), source_label, font=label_font, fill="white")
    right_x = panel_size[0] + gap * 2
    draw.text((right_x, 38), "RESULT 4x", font=label_font, fill="white")
    count = len({p[:3] for p in result.get_flattened_data() if p[3]})
    draw.text((right_x, 57), f"{result.width}x{result.height} / {count} colors", fill="white")
    factor = min(panel_size[0] / crop.width, panel_size[1] / crop.height)
    original = crop.resize((max(1, round(crop.width * factor)),
                            max(1, round(crop.height * factor))), Image.Resampling.NEAREST)
    left_panel = checkerboard(panel_size)
    left_panel.alpha_composite(original, ((panel_size[0] - original.width) // 2,
                                          (panel_size[1] - original.height) // 2))
    right_panel = checkerboard(panel_size)
    right_panel.alpha_composite(result.resize(panel_size, Image.Resampling.NEAREST))
    sheet.paste(left_panel.convert("RGB"), (gap, header))
    if before is not None:
        draw.rectangle((right_x, 35, right_x + panel_size[0], 75), fill="#25282c")
        draw.text((right_x, 38), "BEFORE 4x / 16 colors", font=label_font, fill="white")
        before_panel = checkerboard(panel_size)
        before_panel.alpha_composite(before.resize(panel_size, Image.Resampling.NEAREST))
        sheet.paste(before_panel.convert("RGB"), (right_x, header))
        right_x += panel_size[0] + gap
        draw.text((right_x, 38), "AFTER 4x", font=label_font, fill="white")
        draw.text((right_x, 57), f"{result.width}x{result.height} / {count} colors", fill="white")
    sheet.paste(right_panel.convert("RGB"), (right_x, header))
    return sheet


def comparison_montage(cards, shrink=1, columns=2):
    # The standalone comparisons retain 4x; building overview uses 2x thumbnails.
    if shrink != 1:
        cards = [card.resize((card.width // shrink, card.height // shrink),
                             Image.Resampling.NEAREST) for card in cards]
    gap = 12
    cell_width = max(card.width for card in cards)
    cell_height = max(card.height for card in cards)
    rows = (len(cards) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width + (columns + 1) * gap,
                              rows * cell_height + (rows + 1) * gap), "#25282c")
    for index, card in enumerate(cards):
        x = gap + (index % columns) * (cell_width + gap)
        y = gap + (index // columns) * (cell_height + gap)
        sheet.paste(card, (x + (cell_width - card.width) // 2, y))
    return sheet


def palette_swatch(palette, title, roles):
    columns, cell_width, cell_height, gap = 4, 246, 106, 16
    rows = (len(palette) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width + gap, 48 + rows * cell_height), "#f4f4f1")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=14)
    small = ImageFont.load_default(size=12)
    draw.text((gap, 12), title, font=font, fill="#202020")
    for index, (color, role) in enumerate(zip(palette, roles), 1):
        x = gap + ((index - 1) % columns) * cell_width
        y = 48 + ((index - 1) // columns) * cell_height
        draw.rectangle((x, y, x + 224, y + 40), fill=color, outline="#666666")
        label = f"P{index:02}  #" + "".join(f"{value:02X}" for value in color)
        draw.text((x, y + 45), label, font=font, fill="#202020")
        draw.text((x, y + 66), role, font=small, fill="#404040")
    return sheet


def khaki_preview(rendered):
    sheet = Image.new("RGB", (824, 912), "#666F54")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=15)
    draw.text((16, 12), "MUTED SKY-BLUE GLASS ON KHAKI #666F54", font=font, fill="#E6E1C6")
    for index, name in enumerate(BUILDING_REGIONS):
        image = rendered[name]
        enlarged = image.resize((image.width * 3, image.height * 3), Image.Resampling.NEAREST)
        x = 16 + (index % 2) * 404 + (384 - enlarged.width) // 2
        y = 52 + (index // 2) * 424
        draw.text((16 + (index % 2) * 404, y), name, font=font, fill="#E6E1C6")
        sheet.paste(enlarged, (x, y + 30 + 384 - enlarged.height), enlarged)
    return sheet


def main():
    # Read and validate ALL inputs before creating or replacing any outputs.
    sources = {}
    for name, expected_size in SOURCE_SIZES.items():
        path = RAW / name
        if not path.is_file():
            raise ValueError(f"Missing original: {path.relative_to(ROOT)}")
        with Image.open(path) as source:
            if source.size != expected_size:
                raise ValueError(f"Unexpected source size: {name}: {source.size}; "
                                 f"expected {expected_size}. Review crop coordinates.")
            sources[name] = source.convert("RGBA")

    extracted = {spec.name: extract(sources[spec.source], spec) for spec in SPRITES}
    scales = {
        spec.name: min((spec.size[0] - 2 * PADDING) / extracted[spec.name][1].width,
                       (spec.size[1] - 2 * PADDING) / extracted[spec.name][1].height)
        for spec in SPRITES
    }
    hero_scale = min(scales["hero-front"], scales["hero-back"])
    scales["hero-front"] = scales["hero-back"] = hero_scale
    palettes = {"logo-source.png": PALETTE}
    for source_name in SOURCE_SIZES:
        if source_name not in palettes:
            palettes[source_name] = source_palette(
                [extracted[spec.name][1] for spec in SPRITES if spec.source == source_name],
                color_samples=tuple(sources[source_name].crop(box)
                                    for box in SOURCE_COLOR_REGIONS[source_name]))
    rendered = {spec.name: render(extracted[spec.name][1], spec, scales[spec.name],
                                  palettes[spec.source])
                for spec in SPRITES}
    before_buildings = {spec.name: rendered[spec.name].copy() for spec in SPRITES if spec.plate}
    base_building_palette = palettes["city-tiles.png"]
    if not set(GLASS_MAP).issubset(base_building_palette):
        raise ValueError("Original building palette changed; review the local recolor mappings")
    building_palette = tuple(dict.fromkeys(base_building_palette + BUILDING_EXTRA_COLORS))
    before_cleanup = {}
    for spec in SPRITES:
        if spec.plate:
            rendered[spec.name] = recolor_building(rendered[spec.name], spec, building_palette)
            before_cleanup[spec.name] = rendered[spec.name].copy()
            rendered[spec.name] = clean_building_materials(rendered[spec.name], spec)
            validate(rendered[spec.name], spec, building_palette)
    shared_colors = {p[:3] for spec in SPRITES if spec.plate
                     for p in rendered[spec.name].get_flattened_data() if p[3]}
    if len(shared_colors) > MAX_BUILDING_COLORS:
        raise ValueError("Shared building palette exceeds 21 colors")
    comparisons = {spec.name: comparison(spec, extracted[spec.name][0], rendered[spec.name],
                                          before=before_buildings.get(spec.name))
                   for spec in SPRITES}

    PREVIEW.mkdir(parents=True, exist_ok=True)
    for spec in SPRITES:
        output = ROOT / spec.output
        output.parent.mkdir(parents=True, exist_ok=True)
        image = rendered[spec.name]
        image.save(output)
        extracted[spec.name][0].save(PREVIEW / f"{spec.name}-source-crop.png")
        image.resize((image.width * PREVIEW_SCALE, image.height * PREVIEW_SCALE),
                     Image.Resampling.NEAREST).save(
                         PREVIEW / f"{spec.name}-result-preview-4x.png")
        comparisons[spec.name].save(PREVIEW / f"{spec.name}-comparison.png")
        if spec.plate:
            before_buildings[spec.name].resize(
                (image.width * PREVIEW_SCALE, image.height * PREVIEW_SCALE),
                Image.Resampling.NEAREST).save(PREVIEW / f"{spec.name}-before-preview-4x.png")
        count = len({p[:3] for p in image.get_flattened_data() if p[3]})
        print(f"{spec.output}: {image.width}x{image.height}, {count} visible colors")
    comparison_montage([comparisons["hero-front"], comparisons["hero-back"]]).save(
        PREVIEW / "characters-comparison.png")
    comparison_montage([comparisons[spec.name] for spec in SPRITES if spec.plate],
                       shrink=2, columns=1).save(
        PREVIEW / "buildings-comparison.png")
    roles = ("Foliage: light", "Foliage: shadow", "Roof / gray walls", "Flags / red banners",
             "Glass / bone / trim", "Glass / sign highlight", "Glass / sign base",
             "Glass / beige shadow", "Brown details / icons", "Roof / plinth / walls",
             "Brown icon / shadows", "Roof / wall shadow", "Road / dark surfaces",
             "Frames / outlines", "Deep outlines", "Deepest outlines")
    palette_swatch(base_building_palette, "BEFORE: 16 SHARED BUILDING COLORS", roles).save(
        PREVIEW / "buildings-palette-before.png")
    after_roles = list(roles)
    after_roles[4:8] = ["Bone / box / bright trim", "Trim / lamp highlights", "Trim / lamps / awnings",
                        "Beige walls / trim shadows"]
    building_roles = tuple(after_roles) + (
        "Glass: blue-gray shadow", "Glass: muted sky blue", "Glass: light reflection",
        "Main sign: orange", "Company icon: dark outline")
    active_palette = tuple(color for color in building_palette if color in shared_colors)
    active_roles = tuple(role for color, role in zip(building_palette, building_roles)
                         if color in shared_colors)
    palette_swatch(active_palette, f"AFTER: {len(active_palette)} SHARED BUILDING COLORS",
                   active_roles).save(
        PREVIEW / "buildings-palette-after.png")
    khaki_preview(rendered).save(PREVIEW / "buildings-on-khaki-preview.png")
    cleanup_cards = [comparison(spec, before_cleanup[spec.name], rendered[spec.name],
                                source_label="BEFORE CLEANUP 4x")
                     for spec in SPRITES if spec.plate]
    comparison_montage(cleanup_cards, shrink=2).save(
        PREVIEW / "buildings-material-cleanup-comparison.png")
    print(f"Shared building colors: {len(shared_colors)}; alpha, glass, signs and icons preserved during material cleanup.")
    print("Saved original/before/after comparisons, 4x previews and before/after palette swatches.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        print(f"Conversion failed: {error}", file=sys.stderr)
        sys.exit(1)
