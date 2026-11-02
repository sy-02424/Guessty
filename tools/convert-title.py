r"""Convert only the dedicated title backgrounds; never rebuild existing sprites.

Run from any directory with the project's Pillow environment:
    .venv\Scripts\python.exe tools\convert-title.py

The local originals stay under assets/raw (ignored by Git). Production PNGs
are opaque, at most 16 colors (approved 2.5 daytime/reverse atmospheres and
their surrounds: <=24).
Conversions use no automatic dithering. Web rendering uses integer
multiples of these exact dimensions. Palette slots reserve KHAKI colors and
approved glass colors; existing backgrounds sample remaining material colors
from their source. The reverse variant learns <=16 original RGB colors by
material, preserving the edited source's sky/road separation and saturation.
"""

from pathlib import Path
from collections import Counter, deque
from io import BytesIO
import argparse
import json
from statistics import median

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "assets" / "raw"
CREAM = (230, 225, 198)
BASE_PALETTE = (
    (47, 51, 38), (68, 82, 58), (102, 111, 84), CREAM,
    (217, 132, 78), (70, 160, 142),
    (126, 159, 174), (183, 205, 214), (83, 111, 122),
)
SPECS = (
    ("title-bg-source.png", "title-bg.png", (216, 384)),
    ("title-surround-source.png", "title-surround.png", (576, 384)),
)
KHAKI = (102, 111, 84)
# Material budgets prevent the large sky/road fields from consuming the palette.
REVERSE_MATERIALS = (("Khaki sky", 1), ("Neutral gray road", 1),
                     ("Outline / deep shadow", 2), ("Foliage", 3),
                     ("Cream / stone / cloud", 4), ("Orange accent", 2),
                     ("Blue glass", 2), ("Wood", 1))


def material_colors(source, count, predicate):
    pixels = [p for p in source.get_flattened_data() if predicate(*p)]
    if not pixels:
        raise ValueError("Missing title background material samples")
    strip = Image.new("RGB", (len(pixels), 1))
    strip.putdata(pixels)
    quantized = strip.quantize(colors=count, method=Image.Quantize.MEDIANCUT,
                               dither=Image.Dither.NONE)
    colors = sorted(quantized.convert("RGB").getcolors(len(pixels)), reverse=True)
    return [color for _, color in colors]


def build_palette(source):
    foliage = material_colors(source, 3, lambda r, g, b:
                              70 < r < 190 and g > r + 6 and r > b + 25)
    stone = material_colors(source, 2, lambda r, g, b:
                            130 < r < 210 and 12 < r - g < 40 and 15 < g - b < 60)
    wood = material_colors(source, 2, lambda r, g, b:
                           75 < r < 160 and r - g > 25 and g - b > 10)
    return tuple(dict.fromkeys(BASE_PALETTE + tuple(foliage + stone + wood)))


def convert(source, size, palette):
    small = source.resize(size, Image.Resampling.BOX)
    # A single flat sky avoids a seam with the CSS sky on tall viewports.
    small.putdata([CREAM if r > 210 and g > 200 and b > 155 and r - g < 25
                   else (r, g, b) for r, g, b in small.get_flattened_data()])
    palette_image = Image.new("P", (1, 1))
    padded = palette + (palette[0],) * (256 - len(palette))
    palette_image.putpalette([value for color in padded for value in color])
    output = small.quantize(palette=palette_image, dither=Image.Dither.NONE)
    if len(output.getcolors(256)) > 16 or "transparency" in output.info:
        raise ValueError("Title background must be opaque and <=16 colors")
    if any(output.convert("RGB").getpixel((x, 0)) != CREAM for x in range(size[0])):
        raise ValueError("Top sky edge must match the CSS cream")
    return output


def original_representatives(pixels, count):
    """MEDIANCUT per material, snapped to source RGBs, stable tie-breaking."""
    if not pixels:
        raise ValueError("Missing reverse-background material samples")
    strip = Image.new("RGB", (len(pixels), 1))
    strip.putdata(pixels)
    quantized = strip.quantize(colors=count, method=Image.Quantize.MEDIANCUT,
                               dither=Image.Dither.NONE)
    entries = quantized.getpalette()
    clusters = {}
    for rgb, index in zip(pixels, quantized.get_flattened_data()):
        clusters.setdefault(index, set()).add(rgb)
    result = []
    for index, candidates in sorted(clusters.items()):
        center = entries[index * 3:index * 3 + 3]
        result.append(min(candidates, key=lambda rgb: (
            sum((a - b) ** 2 for a, b in zip(rgb, center)), rgb)))
    return result


def reverse_palette(source):
    # NEAREST sampling retains actual source RGBs, unlike averaged swatches.
    sample = ImageOps.fit(source, (432, 768), method=Image.Resampling.NEAREST)
    groups = [list(sample.crop((40, 4, 390, 40)).get_flattened_data()),
              list(sample.crop((202, 660, 230, 756)).get_flattened_data())]
    groups.extend([] for _ in range(6))
    sky = original_representatives(groups[0], 1)[0]
    sky_region = connected_material(sample, (0, 0), lambda x, y, rgb:
        y < 514 and max(rgb) - min(rgb) < 65
        and sum((a - b) ** 2 for a, b in zip(rgb, sky)) < 40 ** 2)
    road_region = connected_material(sample, (216, 767), lambda x, y, rgb:
        y >= 508 and 90 <= min(rgb) and max(rgb) <= 175
        and abs(rgb[0] - rgb[1]) < 15 and max(rgb) - min(rgb) < 35)
    excluded = sky_region | road_region
    for index, (r, g, b) in enumerate(sample.get_flattened_data()):
        if (index % 432, index // 432) in excluded:
            continue
        x, y = (index % 432) / 2, (index // 432) / 2
        if max(r, g, b) < 70:
            material = 2
        elif r > 150 and r - g > 45 and r - b > 65:
            material = 5
        elif b > r + 10 and g > r + 10:
            material = 6
        elif r < 165 and r - g > 18 and g - b > 12 and y > 180:
            material = 7
        elif r >= g and r - g < 45 and g - b > 10 and b >= 100:
            material = 4
        elif (g > r - 5 and g - b > 20 and 75 < g < 195
              and y > 115 and (x < 50 or x > 165)):
            material = 3
        else:
            continue
        groups[material].append((r, g, b))
    palette, roles = [], []
    for pixels, (role, budget) in zip(groups, REVERSE_MATERIALS):
        for color in original_representatives(pixels, budget):
            if color not in palette:
                palette.append(color)
                roles.append(role)
    return tuple(palette), tuple(roles)


def connected_material(image, seed, eligible):
    pixels = image.load()
    queue, visited, region = deque([seed]), set(), set()
    while queue:
        x, y = queue.popleft()
        if (x, y) in visited or not (0 <= x < image.width and 0 <= y < image.height):
            continue
        visited.add((x, y))
        if not eligible(x, y, pixels[x, y]):
            continue
        region.add((x, y))
        queue.extend(((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))
    return region


def convert_reverse(source, palette):
    # Fit rather than stretch: the saved edit is already approximately 9:16.
    small = ImageOps.fit(source, (216, 384), method=Image.Resampling.BOX)
    palette_image = Image.new("P", (1, 1))
    colors = palette + (palette[0],) * (256 - len(palette))
    palette_image.putpalette([v for color in colors for v in color])
    # Exact RGB distance avoids Pillow's reduced-resolution palette lookup,
    # which can choose a neighboring material even for an exact palette RGB.
    nearest, values = {}, bytearray()
    for rgb in small.get_flattened_data():
        if rgb not in nearest:
            nearest[rgb] = min(range(len(palette)), key=lambda index:
                sum((a - b) ** 2 for a, b in zip(rgb, palette[index])))
        values.append(nearest[rgb])
    # Restore each broad material to its OWN source representative. Source-space
    # masks prevent the sky/road from competing with foliage during quantizing.
    sky, road = palette[:2]
    sky_region = connected_material(small, (0, 0), lambda x, y, rgb:
        y < 257 and max(rgb) - min(rgb) < 65
        and sum((a - b) ** 2 for a, b in zip(rgb, sky)) < 40 ** 2)
    road_region = connected_material(small, (108, 383), lambda x, y, rgb:
        y >= 254 and 90 <= min(rgb) and max(rgb) <= 175
        and abs(rgb[0] - rgb[1]) < 15 and max(rgb) - min(rgb) < 35)
    for region, index in ((sky_region, 0), (road_region, 1)):
        for x, y in region:
            values[y * 216 + x] = index
    output = Image.frombytes("P", small.size, bytes(values))
    output.putpalette(palette_image.getpalette())
    if len(output.getcolors(256)) > 16 or "transparency" in output.info:
        raise ValueError("Reverse title must be opaque and <=16 colors")
    if any(output.convert("RGB").getpixel((x, 0)) != sky for x in range(output.width)):
        raise ValueError("Reverse title top sky must match the original sky material")
    if output.convert("RGB").getpixel((108, 383)) != road:
        raise ValueError("Reverse road must remain distinct from the sky")
    return output


def reverse_previews(source, output, palette, roles):
    preview = RAW / "preview"
    preview.mkdir(parents=True, exist_ok=True)
    source.save(preview / "title-bg-reverse-source-crop.png")
    output.resize((432, 768), Image.Resampling.NEAREST).save(
        preview / "title-bg-reverse-asset-preview-2x.png")
    output.resize((864, 1536), Image.Resampling.NEAREST).save(
        preview / "title-bg-reverse-result-preview-4x.png")
    font = ImageFont.load_default(size=16)
    sheet = Image.new("RGB", (3 * 432 + 4 * 16, 824), "#2F3326")
    draw = ImageDraw.Draw(sheet)
    images = (
        ("REVERSE MOCKUP / REFERENCE", Image.open(ROOT / "docs/mockups/title-reverse.ver.png")),
        ("CLEANED SOURCE", source),
        ("FINAL / 216x384 / <=16 COLORS", output),
    )
    for index, (label, image) in enumerate(images):
        x = 16 + index * 448
        draw.text((x, 14), label, font=font, fill=CREAM)
        # Letterbox the 2:3 mockup; do not distort it to match the 9:16 asset.
        panel = Image.new("RGB", (432, 768), palette[0])
        fit = ImageOps.contain(image.convert("RGB"), (432, 768),
                               method=Image.Resampling.NEAREST)
        panel.paste(fit, ((432 - fit.width) // 2, (768 - fit.height) // 2))
        sheet.paste(panel, (x, 40))
    sheet.save(preview / "title-bg-reverse-comparison.png")

    swatch = Image.new("RGB", (720, 320), CREAM)
    draw = ImageDraw.Draw(swatch)
    draw.text((12, 10), "REVERSE / ORIGINAL MATERIAL COLORS / <=16", font=font, fill=BASE_PALETTE[0])
    for index, (color, role) in enumerate(zip(palette, roles)):
        x, y = 12 + (index % 4) * 177, 40 + (index // 4) * 70
        draw.rectangle((x, y, x + 160, y + 22), fill=color)
        draw.text((x, y + 24), "#" + "".join(f"{c:02X}" for c in color), fill=BASE_PALETTE[0])
        draw.text((x, y + 40), role, fill=BASE_PALETTE[0])
    swatch.save(preview / "title-bg-reverse-palette.png")

    # Asset-only composition, no invented copy or web changes.
    scene = output.convert("RGBA")
    logo = Image.open(ROOT / "assets/logo.png").convert("RGBA")
    hero = Image.open(ROOT / "assets/hero-back.png").convert("RGBA")
    scene.alpha_composite(logo, ((scene.width - logo.width) // 2, 42))
    scene.alpha_composite(hero, ((scene.width - hero.width) // 2, 256))
    scene.resize((432, 768), Image.Resampling.NEAREST).save(preview / "title-reverse-composite.png")
    comparisons = (
        ("title-bg-reverse-before-brand.png", "BEFORE / PALE KHAKI", "AFTER / SOURCE COLORS",
         "title-bg-reverse-brand-comparison.png"),
        ("title-bg-reverse-before-separation.png", "BEFORE / DARK SKY + ROAD", "AFTER / SEPARATE MATERIALS",
         "title-bg-reverse-separation-comparison.png"),
    )
    for filename, before_label, after_label, destination in comparisons:
        before_path = preview / filename
        if not before_path.exists():
            continue
        comparison = Image.new("RGB", (912, 824), BASE_PALETTE[0])
        draw = ImageDraw.Draw(comparison)
        before = Image.open(before_path).convert("RGBA")
        before.alpha_composite(logo, ((before.width - logo.width) // 2, 42))
        before.alpha_composite(hero, ((before.width - hero.width) // 2, 256))
        for x, label, panel in ((16, before_label, before), (464, after_label, scene)):
            draw.text((x, 14), label, font=font, fill=CREAM)
            comparison.paste(panel.resize((432, 768), Image.Resampling.NEAREST), (x, 40))
        comparison.save(preview / destination)


def material_noise(x, y, scale):
    """Seeded, smoothly connected values; no checker/Bayer/repeating mesh."""
    ix, iy = x // scale, y // scale
    fx, fy = (x % scale) / scale, (y % scale) / scale
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)

    def value(a, b):
        n = ((a * 374761393 + b * 668265263 + 1759) ^ 0x5F3759DF) & 0xFFFFFFFF
        n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
        return ((n ^ (n >> 16)) & 65535) / 32767.5 - 1

    top = value(ix, iy) * (1 - fx) + value(ix + 1, iy) * fx
    bottom = value(ix, iy + 1) * (1 - fx) + value(ix + 1, iy + 1) * fx
    return top * (1 - fy) + bottom * fy


def atmosphere_tones(donor, sky, road, sky_color):
    """Six close sky shades and two warm road shades from the saved edit."""
    pixels = donor.load()
    tones = [sky_color]
    for row in (85, 110, 135, 160, 185, 208):
        samples = [pixels[x, y] for x, y in sorted(sky) if abs(y - row) < 5
                   and 40 < min(pixels[x, y]) and max(pixels[x, y]) < 155
                   and pixels[x, y][1] > pixels[x, y][2] + 12]
        if not samples:
            raise ValueError("Missing atmosphere sky samples")
        center = tuple(median([p[c] for p in samples]) for c in range(3))
        color = min(set(samples), key=lambda p: (sum((a - b) ** 2 for a, b in zip(p, center)), p))
        # The edit is an atmosphere reference, not a global grade. Compress its
        # range so close sky shades stay quiet behind the existing logo.
        tones.append(tuple(round(a + (b - a) * 0.30) for a, b in zip(sky_color, color)))
    tones.sort(key=lambda p: sum(p))
    if tones[0] != sky_color:
        raise ValueError("Atmosphere would darken the top sky; review source")
    samples = [pixels[x, y] for x, y in sorted(road)
               if 65 < min(pixels[x, y]) and max(pixels[x, y]) < 170
               and 0 <= pixels[x, y][0] - pixels[x, y][1] < 20
               and pixels[x, y][1] > pixels[x, y][2] + 10]
    center = tuple(median([p[c] for p in samples]) for c in range(3))
    # Keep the warm tint but compress local contrast: no camouflage-like blobs.
    road_tones = sorted((tuple(round(a + (b - a) * 0.22) for a, b in zip(center, color))
                         for color in original_representatives(samples, 2)), key=lambda p: sum(p))
    return tuple(tones), tuple(road_tones)


def atmosphere_sky_color(x, y, tones):
    if y <= 70:
        return tones[0]
    t = min(1, max(0, (y - 70) / 168))
    progress = t * t * (3 - 2 * t)
    # Broad, softly stepped edges rather than single-pixel speckle.
    noise = (material_noise(x, y, 32) * 0.18 + material_noise(x, y, 12) * 0.12
             + material_noise(x, y, 5) * 0.04)
    index = max(0, min(6, round(progress * 5.6 + noise * t ** 1.3)))
    return tones[index]


def cream_atmosphere_tones(donor, sky, road, sky_color):
    """Close, source-sampled cream sky and road tones for the daytime title.

    The normal title art already has a soft painted gradient in its source.
    We retain its actual RGB values but compress that range before applying it
    as sparse pixel clusters.  This keeps the upper title area quiet enough
    for the logo and avoids a synthetic checker or a global colour grade.
    """
    pixels = donor.load()
    sky_tones = [sky_color]
    for row in (92, 116, 140, 164, 188, 212):
        samples = [pixels[x, y] for x, y in sorted(sky) if abs(y - row) < 5
                   and min(pixels[x, y]) > 145 and pixels[x, y][0] > pixels[x, y][2] + 12
                   and pixels[x, y][0] - pixels[x, y][1] < 30]
        if not samples:
            raise ValueError("Missing cream atmosphere sky samples")
        center = tuple(median([p[c] for p in samples]) for c in range(3))
        sample = min(set(samples), key=lambda p: (
            sum((a - b) ** 2 for a, b in zip(p, center)), p))
        # The source is a reference for nearby tones, not a full-screen tint.
        sky_tones.append(tuple(round(a + (b - a) * 0.40)
                               for a, b in zip(sky_color, sample)))

    road_samples = [pixels[x, y] for x, y in sorted(road)
                    if min(pixels[x, y]) > 35 and max(pixels[x, y]) < 145
                    and pixels[x, y][1] >= pixels[x, y][2] + 10]
    if not road_samples:
        raise ValueError("Missing cream atmosphere road samples")
    representatives = original_representatives(road_samples, 2)
    center = tuple(median([p[c] for p in road_samples]) for c in range(3))
    # A very small source-faithful road variation: warm enough to separate it
    # from the lower sky, but not an orange glow.
    road_tones = tuple(sorted((tuple(round(a + (b - a) * 0.28)
                                      for a, b in zip(center, color))
                                for color in representatives), key=sum))
    return tuple(sky_tones), road_tones


def cream_atmosphere_sky_color(x, y, tones):
    """Plain cream at the top, then irregular small tonal clusters below."""
    if y <= 70:
        return tones[0]
    t = min(1, max(0, (y - 70) / 168))
    progress = t * t * (3 - 2 * t)
    noise = (material_noise(x, y, 32) * 0.18 + material_noise(x, y, 12) * 0.12
             + material_noise(x, y, 5) * 0.04)
    index = max(0, min(6, round(progress * 5.35 + noise * t ** 1.3)))
    return tones[index]


def write_cream_atmosphere():
    """Rebuild the original daytime pair with the approved organic falloff.

    The center retains its shops and clouds. The side scenery uses the exact
    tree/lamp/tile composition of reverse 2.5 with a daytime material palette.
    Both outputs share a maximum 24-colour palette.
    """
    sources = [Image.open(RAW / name).convert("RGB") for name, _, _ in SPECS]
    palette = build_palette(sources[0])
    flat_center, flat_surround = [convert(source, size, palette).convert("RGB")
                                  for source, (_, _, size) in zip(sources, SPECS)]
    sky_color = flat_center.getpixel((108, 0))
    road_color = flat_center.getpixel((108, 383))
    center_sky = connected_material(flat_center, (0, 0), lambda x, y, rgb:
                                    y < 259 and rgb == sky_color)
    center_road = connected_material(flat_center, (108, 383), lambda x, y, rgb:
                                     y >= 254 and rgb == road_color)
    if len(center_sky) < 20000 or len(center_road) < 15000:
        raise ValueError("Unexpected daytime title sky/road masks")
    donor = ImageOps.fit(sources[0], flat_center.size, method=Image.Resampling.BOX)
    sky_tones, road_tones = cream_atmosphere_tones(donor, center_sky, center_road, sky_color)

    def apply(image, sky, road, x_offset=0):
        output = image.copy()
        for x, y in sky:
            output.putpixel((x, y), cream_atmosphere_sky_color(x + x_offset, y, sky_tones))
        for x, y in road:
            t = min(1, max(0, (y - 259) / 124))
            noise = material_noise(x + x_offset, y, 24) * 0.16 + material_noise(x + x_offset, y, 9) * 0.08
            index = max(0, min(1, round(0.9 - t * 0.55 + noise * t)))
            output.putpixel((x, y), road_tones[index])
        return output

    center = apply(flat_center, center_sky, center_road)
    surround = compose_side_scenery(center, sky_tones, road_tones, cream_atmosphere_sky_color)
    for label, before, after in (("title-bg", flat_center, center),
                                 ("title-surround", flat_surround, surround)):
        allowed = set(before.get_flattened_data()) | set(sky_tones) | set(road_tones)
        if len(set(after.get_flattened_data())) > 24 or not set(after.get_flattened_data()) <= allowed:
            raise ValueError(f"{label} cream atmosphere palette escaped its 24-colour limit")

    for filename, output in (("title-bg.png", center), ("title-surround.png", surround)):
        encoded = BytesIO()
        output.save(encoded, format="PNG", optimize=True)
        (ROOT / "assets" / filename).write_bytes(encoded.getvalue())

    preview = RAW / "preview"
    preview.mkdir(parents=True, exist_ok=True)
    flat_center.resize((432, 768), Image.Resampling.NEAREST).save(
        preview / "title-bg-before-cream-atmosphere.png")
    center.resize((432, 768), Image.Resampling.NEAREST).save(
        preview / "title-bg-cream-atmosphere-preview-2x.png")
    center.resize((864, 1536), Image.Resampling.NEAREST).save(
        preview / "title-bg-cream-atmosphere-preview-4x.png")
    flat_surround.resize((1152, 768), Image.Resampling.NEAREST).save(
        preview / "title-surround-before-cream-atmosphere.png")
    surround.resize((1152, 768), Image.Resampling.NEAREST).save(
        preview / "title-surround-cream-atmosphere-preview-2x.png")

    comparison = Image.new("RGB", (912, 824), BASE_PALETTE[0])
    draw = ImageDraw.Draw(comparison)
    logo = Image.open(ROOT / "assets/logo.png").convert("RGBA")
    hero = Image.open(ROOT / "assets/hero-back.png").convert("RGBA")
    for x, label, image in ((16, "BEFORE / FLAT CREAM SKY", flat_center),
                             (464, "AFTER / ORGANIC PIXEL ATMOSPHERE", center)):
        scene = image.convert("RGBA")
        scene.alpha_composite(logo, (12, 42))
        scene.alpha_composite(hero, (92, 256))
        draw.text((x, 14), label, font=ImageFont.load_default(size=16), fill=CREAM)
        comparison.paste(scene.convert("RGB").resize((432, 768), Image.Resampling.NEAREST), (x, 40))
    comparison.save(preview / "title-bg-cream-atmosphere-comparison.png")
    desktop_preview(center, surround, preview / "title-desktop-cream-composite.png")
    calm_comparison(center, surround, "title-bg", "title-surround", "cream")
    (preview / "title-bg-cream-atmosphere-colors.json").write_text(
        json.dumps({"sky": sky_tones, "road": road_tones,
                    "plain_sky_through_y": 70, "max_colors": 24}, indent=2) + "\n")
    print(f"assets/title-bg.png: 216x384, daytime organic pixel atmosphere, "
          f"{len(set(center.get_flattened_data()))} colors")
    print(f"assets/title-surround.png: 576x384, matching atmosphere, "
          f"{len(set(surround.get_flattened_data()))} colors")


def write_reverse_25():
    """Approved <=24-color 2.5: plain upper sky, organic tonal falloff below.

    Only the two original connected material masks are changed. Six close sky
    shades and two warm road shades are sampled from the saved image edit.
    Existing building, cloud, foliage and pavement pixels remain exact.
    """
    before = Image.open(ROOT / "assets/title-bg-reverse-2.png").convert("RGB")
    if before.size != (216, 384):
        raise ValueError("Dark Sky version 2 must be 216x384")
    old_color = before.getpixel((108, 383))
    road = connected_material(before, (108, 383), lambda x, y, rgb:
                              y >= 254 and rgb == old_color)
    if len(road) < 15000 or KHAKI not in set(before.get_flattened_data()):
        raise ValueError("Version 2 road/palette changed; review the source")
    after = before.copy()
    for position in road:
        after.putpixel(position, KHAKI)
    for index, (old, new) in enumerate(zip(before.get_flattened_data(), after.get_flattened_data())):
        if old != new and (index % 216, index // 216) not in road:
            raise ValueError("Version 2.5 changed a pixel outside the road")
    untextured = after.copy()
    sky_color = before.getpixel((108, 0))
    sky = connected_material(before, (0, 0), lambda x, y, rgb:
                             y < 259 and rgb == sky_color)
    donor = ImageOps.fit(Image.open(RAW / "title-bg-reverse-2.5-atmosphere-source.png").convert("RGB"),
                         before.size, method=Image.Resampling.BOX)
    sky_tones, road_tones = atmosphere_tones(donor, sky, road, sky_color)
    for x, y in sky:
        # Natural clusters emerge downwards. Close shades meet along irregular
        # edges; the untextured upper 70px stays exactly the original solid sky.
        after.putpixel((x, y), atmosphere_sky_color(x, y, sky_tones))
    for x, y in road:
        t = min(1, max(0, (y - 259) / 124))
        noise = material_noise(x, y, 24) * 0.16 + material_noise(x, y, 9) * 0.08
        index = max(0, min(1, round(0.9 - t * 0.55 + noise * t)))
        after.putpixel((x, y), road_tones[index])
    material_mask = sky | road
    for index, (old, new) in enumerate(zip(before.get_flattened_data(), after.get_flattened_data())):
        if old != new and (index % 216, index // 216) not in material_mask:
            raise ValueError("Atmosphere changed a pixel outside sky/road")
    if len(set(after.get_flattened_data())) > 24:
        raise ValueError("Version 2.5 exceeds the approved 24 colors")
    encoded = BytesIO()
    after.save(encoded, format="PNG", optimize=True)
    (ROOT / "assets/title-bg-reverse-2.5.png").write_bytes(encoded.getvalue())
    preview = RAW / "preview"
    preview.mkdir(parents=True, exist_ok=True)
    after.resize((432, 768), Image.Resampling.NEAREST).save(
        preview / "title-bg-reverse-2.5-asset-preview-2x.png")
    after.resize((864, 1536), Image.Resampling.NEAREST).save(
        preview / "title-bg-reverse-2.5-result-preview-4x.png")
    logo = Image.open(ROOT / "assets/logo.png").convert("RGBA")
    hero = Image.open(ROOT / "assets/hero-back.png").convert("RGBA")
    comparison = Image.new("RGB", (912, 824), BASE_PALETTE[0])
    draw = ImageDraw.Draw(comparison)
    for x, label, image in ((16, "2 / ORIGINAL DARK SKY", before),
                             (464, "2.5 / PIXEL ATMOSPHERE", after)):
        scene = image.convert("RGBA")
        scene.alpha_composite(logo, (12, 42))
        scene.alpha_composite(hero, (92, 256))
        panel = scene.resize((432, 768), Image.Resampling.NEAREST)
        draw.text((x, 14), label, font=ImageFont.load_default(size=16), fill=CREAM)
        comparison.paste(panel, (x, 40))
        if image is after:
            panel.save(preview / "title-reverse-2.5-composite.png")
    comparison.save(preview / "title-bg-reverse-2-vs-2.5.png")
    texture_comparison = Image.new("RGB", (912, 824), BASE_PALETTE[0])
    draw = ImageDraw.Draw(texture_comparison)
    for x, label, image in ((16, "2.5 / BEFORE SKY TEXTURE", untextured),
                             (464, "2.5 / NATURAL PIXEL GRADATION", after)):
        scene = image.convert("RGBA")
        scene.alpha_composite(logo, (12, 42))
        scene.alpha_composite(hero, (92, 256))
        draw.text((x, 14), label, font=ImageFont.load_default(size=16), fill=CREAM)
        texture_comparison.paste(scene.resize((432, 768), Image.Resampling.NEAREST), (x, 40))
    texture_comparison.save(preview / "title-bg-reverse-2.5-texture-comparison.png")
    (preview / "title-bg-reverse-2.5-atmosphere-colors.json").write_text(
        json.dumps({"sky": sky_tones, "road": road_tones,
                                  "plain_sky_through_y": 70, "max_colors": 24}, indent=2) + "\n")
    print(f"assets/title-bg-reverse-2.5.png: 216x384, plain upper sky / organic lower sky / "
          f"warm road, {len(set(after.get_flattened_data()))} colors")


def compose_side_scenery(center, sky_tones, road_tones, sky_function):
    """Same scenery geometry for both themes, with the center's own palette."""
    palette = tuple(sorted(set(center.get_flattened_data())))
    layer = ImageOps.fit(Image.open(RAW / "title-surround-reverse-2.5-source.png").convert("RGBA"),
                         (576, 384), method=Image.Resampling.BOX)
    if layer.getchannel("A").getpixel((288, 0)) >= 128:
        raise ValueError("Surround scenery must have transparent sky")
    output = Image.new("RGB", (576, 384))
    output.putdata([sky_function(x - 180, y, sky_tones) if y < 259 else road_tones[0]
                    for y in range(384) for x in range(576)])
    # Keep sky-gradient colours out of opaque scenery material matching.
    materials = tuple(color for color in palette if color not in sky_tones[1:])
    foliage = tuple(color for color in materials
                    if color[1] > color[0] + 5 and color[1] > color[2] + 20)
    nearest = {}
    for index, rgba in enumerate(layer.get_flattened_data()):
        if rgba[3] < 128:
            continue
        rgb = rgba[:3]
        # Daytime leaf samples are brighter/greener than the reverse source.
        # Match their material explicitly so foliage cannot turn into beige stone.
        is_leaf = (sky_tones[0] == CREAM and foliage and index // 576 < 320
                   and rgb[1] > rgb[0] + 2 and rgb[1] > rgb[2] + 20 and rgb[0] > 60)
        key = (rgb, bool(is_leaf))
        if key not in nearest:
            candidates = foliage if is_leaf else materials
            nearest[key] = min(candidates, key=lambda color: sum((a - b) ** 2 for a, b in zip(rgb, color)))
        output.putpixel((index % 576, index // 576), nearest[key])
    if len(set(output.get_flattened_data()) | set(palette)) > 24:
        raise ValueError("Surround exceeds the shared 24-colour palette")
    return output


def desktop_preview(center, surround, target):
    desktop = surround.copy()
    ImageDraw.Draw(desktop).rectangle((178, 0, 397, 383), fill=BASE_PALETTE[0])
    scene = center.convert("RGBA")
    scene.alpha_composite(Image.open(ROOT / "assets/logo.png").convert("RGBA"), (12, 42))
    scene.alpha_composite(Image.open(ROOT / "assets/hero-back.png").convert("RGBA"), (92, 256))
    desktop.paste(scene.convert("RGB"), (180, 0))
    desktop.resize((1152, 768), Image.Resampling.NEAREST).save(target)


def calm_comparison(center, surround, center_name, surround_name, theme):
    """Compare actual saved pre-fix assets with the regenerated desktop scene."""
    preview = RAW / "preview"
    old_center = preview / f"{center_name}-before-calm.png"
    old_surround = preview / f"{surround_name}-before-calm.png"
    if not old_center.exists() or not old_surround.exists():
        return
    desktop_preview(Image.open(old_center).convert("RGB"), Image.open(old_surround).convert("RGB"),
                    preview / f"title-desktop-{theme}-before-calm.png")
    desktop_preview(center, surround, preview / f"title-desktop-{theme}-calm.png")
    sheet = Image.new("RGB", (1152, 1600), BASE_PALETTE[0])
    draw = ImageDraw.Draw(sheet)
    for y, label, name in ((0, "BEFORE", f"title-desktop-{theme}-before-calm.png"),
                            (800, "AFTER / QUIET SKY + MATCHED SIDE SCENERY", f"title-desktop-{theme}-calm.png")):
        draw.text((16, y + 8), label, font=ImageFont.load_default(size=16), fill=CREAM)
        sheet.paste(Image.open(preview / name), (0, y + 32))
    sheet.save(preview / f"title-desktop-{theme}-calm-comparison.png")


def write_surround_25():
    """Quiet desktop side wings; sky matches 2.5, no storefront continuation."""
    center = Image.open(ROOT / "assets/title-bg-reverse-2.5.png").convert("RGB")
    palette = tuple(sorted(set(center.get_flattened_data())))
    before = Image.open(ROOT / "assets/title-bg-reverse-2.png").convert("RGB")
    sky_color = before.getpixel((108, 0))
    sky = connected_material(before, (0, 0), lambda x, y, rgb: y < 259 and rgb == sky_color)
    road_color = before.getpixel((108, 383))
    road = connected_material(before, (108, 383), lambda x, y, rgb: y >= 254 and rgb == road_color)
    donor = ImageOps.fit(Image.open(RAW / "title-bg-reverse-2.5-atmosphere-source.png").convert("RGB"),
                         before.size, method=Image.Resampling.BOX)
    sky_tones, road_tones = atmosphere_tones(donor, sky, road, sky_color)
    output = compose_side_scenery(center, sky_tones, road_tones, atmosphere_sky_color)
    target = ROOT / "assets/title-surround-reverse-2.5.png"
    encoded = BytesIO()
    output.save(encoded, format="PNG", optimize=True)
    target.write_bytes(encoded.getvalue())
    preview = RAW / "preview"
    output.resize((1152, 768), Image.Resampling.NEAREST).save(
        preview / "title-surround-reverse-2.5-preview-2x.png")
    output.resize((2304, 1536), Image.Resampling.NEAREST).save(
        preview / "title-surround-reverse-2.5-preview-4x.png")
    # Deliberate mobile panel and side scenery, rather than pretending the
    # central cropped shops are parts of the side landscape.
    desktop_preview(center, output, preview / "title-desktop-2.5-composite.png")
    calm_comparison(center, output, "title-bg-reverse-2.5", "title-surround-reverse-2.5", "reverse")
    print(f"assets/title-surround-reverse-2.5.png: 576x384, shared <=24 colors, decorative trees/lamps/tiles")


def versioned_png_bytes(image):
    stream = BytesIO()
    image.save(stream, format="PNG", optimize=True)
    return stream.getvalue()


def save_numbered_files(files):
    """An identical rebuild is allowed; a changed design needs a new number.

    Preflight the complete batch so a conflicting file cannot leave a mixture
    of previous and new results. Existing unnumbered assets are never targets.
    """
    conflicts = [str(path.relative_to(ROOT)) for path, data in files.items()
                 if path.exists() and path.read_bytes() != data]
    if conflicts:
        raise ValueError("Preserving existing version; select the next --version number: "
                         + ", ".join(conflicts))
    for path, data in files.items():
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)


def simple_desktop_scene(center, surround):
    """Actual native-resolution asset composite, without an invented frame."""
    scene = center.convert("RGBA")
    scene.alpha_composite(Image.open(ROOT / "assets/logo.png").convert("RGBA"), (12, 42))
    scene.alpha_composite(Image.open(ROOT / "assets/hero-back.png").convert("RGBA"), (92, 256))
    output = surround.copy()
    output.paste(scene.convert("RGB"), (180, 0))
    return output.resize((1152, 768), Image.Resampling.NEAREST)


def simple_surround(source, center, reverse=False, include_buildings=True):
    """Flatten a saved plaza edit into quiet, solid pixel material fields.

    The edit's four clouds and four tiny buildings retain their silhouettes.
    Its horizon is at row 252; move it to the central street's row 255. Grout
    follows that same vanishing point, rather than sampling grainy AI texture.
    """
    def mix(a, b, t):
        return tuple(round(x * (1 - t) + y * t) for x, y in zip(a, b))

    sky_top = center.getpixel((108, 0))
    road = center.getpixel((108, 383))
    cloud = CREAM if reverse else KHAKI
    building = mix(KHAKI, sky_top, 0.45 if reverse else 0.40)
    roof = mix(building, sky_top, 0.12)
    window = mix(building, sky_top if reverse else KHAKI, 0.35)
    floor = mix(road, CREAM, 0.25) if reverse else mix(CREAM, KHAKI, 0.12)
    grout = mix(floor, KHAKI, 0.45 if reverse else 0.35)
    output = Image.new("RGB", (576, 384), sky_top)
    # Sample only atmospheric sky pixels, excluding the center's clouds and
    # trees. Each row is uniform: no noise, dither or isolated tonal flecks.
    sky_rows, previous = [], sky_top
    for y in range(255):
        candidates = []
        # The building-free variant continues the last unobstructed sky into
        # the horizon; distant center buildings must not become sky stripes.
        sample_y = y if include_buildings else min(y, 190)
        for x in range(92, 124):
            rgb = center.getpixel((x, sample_y))
            is_sky = (max(rgb) < 105 and rgb[1] > rgb[2] + 12) if reverse else (
                min(rgb) > 180 and rgb[0] > 210 and rgb[1] > 205)
            if is_sky:
                candidates.append(rgb)
        if y <= 70:
            previous = sky_top
        elif candidates:
            previous = Counter(candidates).most_common(1)[0][0]
        sky_rows.append(previous)
    draw = ImageDraw.Draw(output)
    for y, color in enumerate(sky_rows):
        draw.line((0, y, 575, y), fill=color)
    # Source-space masks exclude the sky's broad cream fields and the floor.
    for y in range(200):
        for x in range(576):
            r, g, b = source.getpixel((x, y))
            if r < 180 and g < 180 and b < 155:
                output.putpixel((x, y), cloud)
    if include_buildings:
        for y in range(200, 252):
            for x in range(576):
                r, g, b = source.getpixel((x, y))
                if r < 185 and g < 185 and b < 165:
                    color = window if b > r or (r < 125 and g < 145) else (roof if y < 234 else building)
                    output.putpixel((x, y + 3), color)
    draw.rectangle((0, 255, 575, 383), fill=floor)
    # Low-contrast one-point paving, not a raised platform. Horizontal rows
    # widen towards the viewer; all longitudinal seams meet at (288,255).
    for endpoint in (-576, -288, 0, 192, 384, 576, 864, 1152):
        draw.line((288, 255, endpoint, 383), fill=grout, width=1)
    for row in (268, 280, 296, 318, 348, 383):
        draw.line((0, row, 575, row), fill=grout, width=1)
    colors = set(output.get_flattened_data())
    if len(colors) > 24:
        raise ValueError("Simple surround exceeds its approved 24-colour limit")
    return output


def write_simple_surround(version, include_buildings=True, source_version=None):
    """Versioned-only entry point; never runs old asset conversion groups."""
    if version < 1:
        raise ValueError("--version must be a positive integer")
    source_version = version if source_version is None else source_version
    if source_version < 1:
        raise ValueError("--source-version must be a positive integer")
    source_path = RAW / f"title-surround-simple-source.{source_version}.png"
    source = ImageOps.fit(Image.open(source_path).convert("RGB"), (576, 384),
                         method=Image.Resampling.BOX)
    files = {}
    preview = RAW / "preview"
    for reverse, stem, center_name, old_name in (
            (False, "title-surround", "title-bg.png", "title-surround.png"),
            (True, "title-surround-reverse", "title-bg-reverse-2.5.png", "title-surround-reverse-2.5.png")):
        center = Image.open(ROOT / "assets" / center_name).convert("RGB")
        output = simple_surround(source, center, reverse, include_buildings)
        filename = f"{stem}.{version}.png"
        files[ROOT / "assets" / filename] = versioned_png_bytes(output)
        for scale in (2, 4):
            files[preview / f"{stem}-preview-{scale}x.{version}.png"] = versioned_png_bytes(
                output.resize((576 * scale, 384 * scale), Image.Resampling.NEAREST))
        scene = simple_desktop_scene(center, output)
        files[preview / f"{stem}-desktop.{version}.png"] = versioned_png_bytes(scene)
        old = Image.open(ROOT / "assets" / old_name).convert("RGB")
        sheet = Image.new("RGB", (1152, 1600), BASE_PALETTE[0])
        draw = ImageDraw.Draw(sheet)
        for y, label, panel in ((0, "EXISTING", simple_desktop_scene(center, old)),
                                 (800, f"VERSION .{version} / " + ("QUIET PLAZA" if include_buildings else "CLOUDS + TILES ONLY"), scene)):
            draw.text((16, y + 8), label, font=ImageFont.load_default(size=16), fill=CREAM)
            sheet.paste(panel, (0, y + 32))
        files[preview / f"{stem}-comparison.{version}.png"] = versioned_png_bytes(sheet)
        colors = sorted(set(output.get_flattened_data()), key=lambda p: (sum(p), p))
        swatches = Image.new("RGB", (640, 36 * len(colors) + 36), CREAM)
        swatch_draw = ImageDraw.Draw(swatches)
        swatch_draw.text((12, 8), filename, font=ImageFont.load_default(size=16), fill=BASE_PALETTE[0])
        for i, color in enumerate(colors):
            swatch_draw.rectangle((12, 36 + i * 36, 84, 64 + i * 36), fill=color, outline=BASE_PALETTE[0])
            swatch_draw.text((100, 41 + i * 36), "#%02X%02X%02X" % color,
                             font=ImageFont.load_default(size=16), fill=BASE_PALETTE[0])
        files[preview / f"{stem}-palette.{version}.png"] = versioned_png_bytes(swatches)
        metadata = {
            "file": filename, "source": source_path.name, "colors": colors,
            "size": [576, 384], "vanishing_point": [288, 255], "dither": False,
            "preview_center": center_name, "web_connected": False}
        if not include_buildings:
            metadata["include_buildings"] = False
            metadata["sky_sample_last_row"] = 190
        files[preview / f"{stem}-colors.{version}.json"] = (json.dumps(metadata, indent=2) + "\n").encode("utf-8")
        if version > 1 and (ROOT / "assets" / f"{stem}.{version - 1}.png").exists():
            earlier = Image.open(ROOT / "assets" / f"{stem}.{version - 1}.png").convert("RGB")
            pair = Image.new("RGB", (1152, 1600), BASE_PALETTE[0])
            pair_draw = ImageDraw.Draw(pair)
            for y, label, panel in ((0, f"VERSION .{version - 1}", simple_desktop_scene(center, earlier)),
                                     (800, f"VERSION .{version} / CLOUDS + TILES ONLY", scene)):
                pair_draw.text((16, y + 8), label, font=ImageFont.load_default(size=16), fill=CREAM)
                pair.paste(panel, (0, y + 32))
            files[preview / f"{stem}-previous-version-comparison.{version}.png"] = versioned_png_bytes(pair)
    save_numbered_files(files)
    for reverse, stem in ((False, "title-surround"), (True, "title-surround-reverse")):
        print(f"assets/{stem}.{version}.png: 576x384, opaque, no dither; previous versions preserved")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", choices=("all", "existing", "cream-2.5", "reverse", "reverse-2.5", "surround-2.5", "surround-simple"), default="all",
                        help="rebuild all title backgrounds, or just the selected variant")
    parser.add_argument("--version", type=int, default=1,
                        help="positive dot-number for surround-simple; changed existing versions are never overwritten")
    parser.add_argument("--source-version", type=int,
                        help="reuse a saved numbered source; defaults to --version")
    parser.add_argument("--no-buildings", action="store_true",
                        help="surround-simple: clouds and tile floor only, no distant buildings")
    args = parser.parse_args()
    if args.group == "surround-simple":
        write_simple_surround(args.version, not args.no_buildings, args.source_version)
        return
    if args.group in ("all", "existing", "cream-2.5"):
        write_cream_atmosphere()
    if args.group in ("all", "reverse"):
        source = Image.open(RAW / "title-bg-reverse-source.png").convert("RGB")
        palette, roles = reverse_palette(source)
        output = convert_reverse(source, palette)
        output.save(ROOT / "assets/title-bg-reverse.png", optimize=True)
        reverse_previews(source, output, palette, roles)
        print(f"assets/title-bg-reverse.png: 216x384, {len(output.getcolors(256))} colors")
    if args.group == "reverse-2.5" or (args.group == "all" and (ROOT / "assets/title-bg-reverse-2.png").exists()):
        write_reverse_25()
    if args.group == "surround-2.5" or (args.group == "all" and (RAW / "title-surround-reverse-2.5-source.png").exists()):
        write_surround_25()


if __name__ == "__main__":
    main()
