"""วาดไอคอน MySoundpad (ลำโพง + คลื่นเสียง บนพื้นไล่สีม่วง) แล้วบันทึกเป็น icon.ico หลายขนาด"""
import os

from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

# พื้นหลังไล่สีม่วง -> ชมพู ในกรอบสี่เหลี่ยมมุมมน
grad = Image.new("RGBA", (S, S))
gd = ImageDraw.Draw(grad)
top, bottom = (108, 66, 245), (236, 72, 153)
for y in range(S):
    t = y / (S - 1)
    gd.line([(0, y), (S, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=220, fill=255)
img.paste(grad, (0, 0), mask)

d = ImageDraw.Draw(img)
white = (255, 255, 255, 255)
# ลำโพง
d.rectangle([230, 410, 360, 614], fill=white)
d.polygon([(360, 410), (520, 270), (520, 754), (360, 614)], fill=white)
# คลื่นเสียง 3 วง
for i, r in enumerate((130, 230, 330)):
    c = (520, 512)
    d.arc([c[0] - r + 40, c[1] - r, c[0] + r + 40, c[1] + r], start=-48, end=48, fill=white, width=58 - i * 6)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.resize((256, 256), Image.LANCZOS).save(out.replace(".ico", ".png"))  # ใช้ใน README
print("saved", out)
