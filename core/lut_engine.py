import os
import PIL.Image
import PIL.ImageOps
import PIL.ImageEnhance
from pillow_lut import load_cube_file
from functools import lru_cache
from collections import defaultdict
import difflib


class LUTEngine:
    def __init__(self, lut_dir="luts"):
        self.lut_dir = lut_dir
        self.lut_index = defaultdict(list)
        self._build_index()

    def _build_index(self):
        """建立 LUT 索引"""
        self.lut_index.clear()
        if not os.path.exists(self.lut_dir):
            return

        print("⚡ 正在建立 LUT 快取索引...")
        for root, _, files in os.walk(self.lut_dir):
            for f in files:
                if f.lower().endswith('.cube'):
                    full_path = os.path.join(root, f)
                    self.lut_index[f.lower()].append(full_path)

    def list_luts(self):
        all_paths = []
        for paths in self.lut_index.values():
            all_paths.extend(paths)
        return all_paths

    @lru_cache(maxsize=32)
    def _get_lut_object(self, lut_path):
        return load_cube_file(lut_path)

    def _adjust_temperature(self, img, value):
        """
        簡易色溫調整
        value: -1.0 (極冷) ~ 1.0 (極暖), 0.0 為原圖
        """
        if value == 0: return img

        # 轉換為 RGB 分離通道
        r, g, b = img.split()

        # 暖色調：紅增藍減；冷色調：紅減藍增
        # 係數微調，避免顏色爆掉
        r_factor = 1.0 + (value * 0.2)
        b_factor = 1.0 - (value * 0.2)

        r = r.point(lambda i: int(min(255, i * r_factor)))
        b = b.point(lambda i: int(min(255, i * b_factor)))

        return PIL.Image.merge("RGB", (r, g, b))

    def apply_lut(self, image_path, lut_name_or_path, intensity=1.0, brightness=1.0, saturation=1.0, temperature=0.0):
        """
        v11 全能修圖：LUT + 亮度 + 飽和度 + 色溫
        - brightness: 1.0 原圖, <1 變暗, >1 變亮
        - saturation: 1.0 原圖, 0 黑白, >1 鮮豔
        - temperature: 0.0 原圖, >0 暖, <0 冷
        """
        try:
            # 1. 載入圖片
            with PIL.Image.open(image_path) as im:
                img = PIL.ImageOps.exif_transpose(im).convert("RGB")

            # 2. [新增] 基礎畫質調整 (Pre-processing)
            # 先調色溫
            if temperature != 0:
                img = self._adjust_temperature(img, temperature)

            # 再調亮度
            if brightness != 1.0:
                enhancer = PIL.ImageEnhance.Brightness(img)
                img = enhancer.enhance(brightness)

            # 再調飽和度
            if saturation != 1.0:
                enhancer = PIL.ImageEnhance.Color(img)
                img = enhancer.enhance(saturation)

            # 3. 尋找 LUT
            target_path = None
            if os.path.exists(lut_name_or_path):
                target_path = lut_name_or_path
            else:
                lookup_name = os.path.basename(lut_name_or_path).lower()
                candidates = self.lut_index.get(lookup_name)

                if candidates:
                    target_path = candidates[0]
                else:
                    all_keys = list(self.lut_index.keys())
                    matches = difflib.get_close_matches(lookup_name, all_keys, n=1, cutoff=0.6)
                    if matches:
                        target_path = self.lut_index[matches[0]][0]

            if not target_path:
                return None, f"找不到 LUT: {lut_name_or_path}"

            # 4. 強度防呆
            intensity = max(0.0, min(1.0, float(intensity)))

            # 5. 套用濾鏡
            try:
                lut = self._get_lut_object(target_path)
            except Exception as e:
                return None, f"LUT 檔案損壞: {e}"

            filtered_img = img.filter(lut)

            if intensity < 1.0:
                final_img = PIL.Image.blend(img, filtered_img, intensity)
            else:
                final_img = filtered_img

            return final_img, "成功"

        except Exception as e:
            return None, str(e)