"""วาดไอคอน MySoundpad (ลำโพง + คลื่นเสียง บนพื้นไล่สีม่วง-ชมพู) แยกทุกขนาด แล้วบันทึกเป็น icon.ico + icon.png

วาดแต่ละขนาดใหม่ (ไม่ย่อจากรูปใหญ่รูปเดียว) ที่ 4 เท่าแล้วย่อลง โดยจัดพิกัดให้ตรงตาราง pixel ของขนาดจริง
ขนาดเล็กใช้เส้นหนาขึ้นและคลื่นเสียงน้อยลง ไอคอนบน taskbar / แถบชื่อหน้าต่างจึงคม ไม่เบลอ
"""
import os

from PIL import Image, ImageDraw

SS = 4  # วาดใหญ่กว่าจริง 4 เท่าแล้วย่อ (ขอบเรียบแต่ยังคม)
TOP, BOTTOM = (108, 66, 245), (236, 72, 153)
WHITE = (255, 255, 255, 255)
# ครบทุกสเกลจอ: 100% (16/24/32/48), 125% (20/30/40/60), 150% (24/36/48/72), 200% (32/48/64/96) + ใหญ่
SIZES = [16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 128, 256]


def render(s):
    S = s * SS
    snap = lambda v: round(v * s) * SS  # สัดส่วน -> pixel เต็มของขนาดจริง -> พิกัดบนผ้าใบ 4 เท่า
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # พื้นไล่สี ในสี่เหลี่ยมมุมมน (ขนาดเล็กเว้นขอบน้อย ให้ไอคอนดูใหญ่เต็มช่อง)
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        gd.line([(0, y), (S, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)) + (255,))
    m = 0 if s <= 24 else max(SS, snap(0.03))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([m, m, S - 1 - m, S - 1 - m], radius=int(S * 0.22), fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    # ลำโพง: ตัวกล่อง + กรวย (ขนาดเล็กขยับไปทางซ้ายและใหญ่ขึ้นเล็กน้อย)
    x0, x1, x2 = (0.16, 0.34, 0.52) if s <= 24 else (0.20, 0.36, 0.53)
    d.rectangle([snap(x0), snap(0.38), snap(x1) - 1, snap(0.62) - 1], fill=WHITE)
    d.polygon([(snap(x1) - 1, snap(0.38)), (snap(x2), snap(0.20)), (snap(x2), snap(0.80)),
               (snap(x1) - 1, snap(0.62))], fill=WHITE)

    # คลื่นเสียง: ความหนาอย่างน้อย 2 pixel จริง (16/20 px มีวงเดียว แต่หนา)
    cx, cy = snap(x2) - snap(0.04), S // 2
    rings = [(0.22, 0.10)] if s <= 20 else [(0.17, 0.075), (0.31, 0.075)] if s <= 48 else \
        [(0.15, 0.06), (0.26, 0.06), (0.37, 0.06)]
    for r, w in rings:
        rr = snap(r)
        width = max(2 * SS, snap(w))
        d.arc([cx - rr, cy - rr, cx + rr, cy + rr], start=-50, end=50, fill=WHITE, width=width)
    return img.resize((s, s), Image.LANCZOS)


here = os.path.dirname(os.path.abspath(__file__))
frames = {s: render(s) for s in SIZES}
out = os.path.join(here, "icon.ico")
big = frames[256]
big.save(out, format="ICO", sizes=[(s, s) for s in SIZES],
         append_images=[frames[s] for s in SIZES if s != 256])  # ใช้รูปที่วาดเองทุกขนาด ไม่ให้ Pillow ย่อเอง
big.save(os.path.join(here, "icon.png"))  # โลโก้บนหัวแอป / README
print("saved", out, "sizes:", SIZES)
