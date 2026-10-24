"""MySoundpad: soundboard เล่นเสียงเข้าไมค์ (ผ่าน VB-CABLE) พร้อมปุ่มลัดแบบ global"""
import os

# numpy (OpenBLAS) จองหน่วยความจำล่วงหน้าให้ทุก CPU thread (~500 MB บนเครื่อง 16 thread)
# ทั้งที่แอปไม่ได้คำนวณเมทริกซ์เลย -> จำกัดเหลือ 1 thread (ต้องตั้งก่อน import numpy ในโมดูลย่อย)
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
