"""Generate IPTV Checker app icon (.ico) - dark blue circle with play button."""
from PIL import Image, ImageDraw, ImageFont
import math, os

def generate_icon():
    sizes = [256, 128, 64, 48, 32, 16]
    images = []

    for sz in sizes:
        img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cx, cy = sz / 2, sz / 2
        r = sz * 0.44  # circle radius

        # --- Background: radial-ish dark blue gradient ---
        for y in range(sz):
            for x in range(sz):
                dx, dy = x - cx, y - cy
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= r + 1:
                    # Gradient from center (#3b4874) to edge (#1e2640)
                    t = min(dist / r, 1.0)
                    rc = int(59 + (30 - 59) * t)
                    gc = int(72 + (38 - 72) * t)
                    bc = int(116 + (64 - 116) * t)
                    # Anti-alias the edge
                    alpha = 255
                    if dist > r - 1:
                        alpha = int(255 * max(0, r + 1 - dist))
                    img.putpixel((x, y), (rc, gc, bc, alpha))

        # --- Subtle ring / border ---
        for angle_deg in range(360):
            angle = math.radians(angle_deg)
            for dr in [-1, 0, 1]:
                rx = cx + (r + dr) * math.cos(angle)
                ry = cy + (r + dr) * math.sin(angle)
                ix, iy = int(rx), int(ry)
                if 0 <= ix < sz and 0 <= iy < sz:
                    existing = img.getpixel((ix, iy))
                    # Lighten slightly for border glow
                    nc = tuple(min(255, c + 20) for c in existing[:3]) + (existing[3],)
                    img.putpixel((ix, iy), nc)

        # --- Play triangle (white) ---
        # Triangle points: left-center, top-right, bottom-right
        tri_size = r * 0.52
        # Offset right a bit (play buttons are visually centered when shifted right)
        offset_x = tri_size * 0.12
        left_x = cx - tri_size * 0.4 + offset_x
        right_x = cx + tri_size * 0.55 + offset_x
        top_y = cy - tri_size * 0.55
        bot_y = cy + tri_size * 0.55

        triangle = [(left_x, top_y), (right_x, cy), (left_x, bot_y)]
        draw.polygon(triangle, fill=(255, 255, 255, 240))

        # --- Inner triangle outline (subtle depth) ---
        inner_scale = 0.78
        inner_tri = []
        for px, py in triangle:
            inner_tri.append((cx + (px - cx) * inner_scale, cy + (py - cy) * inner_scale))
        draw.polygon(inner_tri, fill=(220, 230, 255, 60))

        # --- Drop shadow below circle ---
        if sz >= 48:
            shadow_y = cy + r + sz * 0.06
            shadow_w = r * 0.6
            shadow_h = sz * 0.02
            for sy in range(max(0, int(shadow_y - shadow_h)), min(sz, int(shadow_y + shadow_h))):
                for sx in range(max(0, int(cx - shadow_w)), min(sz, int(cx + shadow_w))):
                    dx = (sx - cx) / shadow_w
                    dy = (sy - shadow_y) / max(shadow_h, 1)
                    d = math.sqrt(dx * dx + dy * dy)
                    if d < 1:
                        a = int(60 * (1 - d))
                        existing = img.getpixel((sx, sy))
                        if existing[3] == 0:
                            img.putpixel((sx, sy), (10, 10, 20, a))

        images.append(img)

    # Save as .ico with multiple sizes
    icon_path = os.path.join(os.path.dirname(__file__), "iptv_checker.ico")
    images[0].save(
        icon_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:]
    )
    print(f"Icon saved: {icon_path}")
    return icon_path

if __name__ == "__main__":
    generate_icon()
