import os
import PIL.Image
import PIL.ImageOps
from pillow_lut import load_cube_file
from functools import lru_cache
from collections import defaultdict
import difflib


class LUTEngine:
    def __init__(self, lut_dir="luts"):
        self.lut_dir = lut_dir
        self.lut_index = defaultdict(list)  # 檔名 -> [完整路徑清單]
        self._build_index()

    def _build_index(self):
        """建立 LUT 索引，避免每次都 os.walk"""
        self.lut_index.clear()
        if not os.path.exists(self.lut_dir):
            return

        print("⚡ 正在建立 LUT 快取索引...")
        for root, _, files in os.walk(self.lut_dir):
            for f in files:
                if f.lower().endswith('.cube'):
                    full_path = os.path.join(root, f)
                    # 使用檔名當作 Key (轉小寫以方便搜尋)
                    self.lut_index[f.lower()].append(full_path)

    def list_luts(self):
        """回傳所有已索引的完整路徑"""
        all_paths = []
        for paths in self.lut_index.values():
            all_paths.extend(paths)
        return all_paths

    @lru_cache(maxsize=32)
    def _get_lut_object(self, lut_path):
        """快取 LUT 物件，避免重複讀取 IO"""
        return load_cube_file(lut_path)

    def apply_lut(self, image_path, lut_name_or_path, intensity=1.0):
        """
        高效套用 LUT
        intensity: 0.0 ~ 1.0 (自動 Clamp)
        """
        try:
            # 1. 確保圖片正確載入與旋轉 (Exif)
            with PIL.Image.open(image_path) as im:
                img = PIL.ImageOps.exif_transpose(im).convert("RGB")

            # 2. 快速查找路徑
            target_path = None

            # Case A: 給的是完整路徑
            if os.path.exists(lut_name_or_path):
                target_path = lut_name_or_path
            # Case B: 給的是檔名，查索引
            else:
                lookup_name = os.path.basename(lut_name_or_path).lower()
                candidates = self.lut_index.get(lookup_name)

                if candidates:
                    target_path = candidates[0]  # 取第一個匹配的
                else:
                    # Case C: 模糊搜尋 (Fallback) - AI 有時候會拼錯字
                    all_keys = list(self.lut_index.keys())
                    matches = difflib.get_close_matches(lookup_name, all_keys, n=1, cutoff=0.6)
                    if matches:
                        target_path = self.lut_index[matches[0]][0]
                        print(f"⚠️ 自動修正 LUT 名稱: '{lut_name_or_path}' -> '{os.path.basename(target_path)}'")

            if not target_path:
                return None, f"找不到 LUT: {lut_name_or_path}"

            # 3. 強度防呆
            intensity = max(0.0, min(1.0, float(intensity)))
            if intensity == 0:
                return img, "強度為 0，回傳原圖"

            # 4. 套用濾鏡 (使用 Cache)
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