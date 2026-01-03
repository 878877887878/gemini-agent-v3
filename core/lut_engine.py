import os
import math
import numpy as np
import PIL.Image
import PIL.ImageOps
import PIL.ImageEnhance
import PIL.ImageFilter
from pillow_lut import load_cube_file
from functools import lru_cache
from collections import defaultdict
import difflib
from core.logger import Logger


class LUTEngine:
    def __init__(self, lut_dir="luts"):
        self.lut_dir = lut_dir
        self.lut_index = defaultdict(list)
        self._build_index()

    def _build_index(self):
        self.lut_index.clear()
        if not os.path.exists(self.lut_dir): return
        Logger.info("正在建立 LUT 索引...")
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

    def _apply_curve(self, img, curve_type):
        """
        v13 電影級曲線應用
        不使用粗暴的 Contrast，而是使用查找表 (Lookup Table) 進行曲線映射
        """
        if curve_type == "Linear" or not curve_type:
            return img

        Logger.debug(f"套用色調曲線: {curve_type}")

        # 建立 0-255 的映射表
        x = np.arange(256)

        if curve_type == "S-Curve":
            # 經典 S 型: 壓暗部、提亮部 (增加對比但保留中間調)
            # 使用 Sigmoid 函數模擬
            factor = 5  # 曲線強度
            y = 255 / (1 + np.exp(-factor * (x / 255 - 0.5)))
            # 正規化回 0-255
            y = (y - y.min()) * 255 / (y.max() - y.min())

        elif curve_type == "Soft-High":
            # 富士風格: 柔化高光 (高光壓縮)
            # x > 128 的部分斜率變緩
            y = np.where(x < 128, x, 128 + (x - 128) * 0.8)

        elif curve_type == "Lift-Shadow":
            # 膠片風格: 提亮暗部 (暗部不在此死黑)
            # x < 64 的部分被提亮
            y = np.where(x > 64, x, x + (64 - x) * 0.3)

        else:
            return img

        # 應用映射表 (針對 RGB 三通道)
        table = y.astype(np.uint8).tolist() * 3
        return img.point(table)

    def _adjust_white_balance(self, img, temp_val, tint_val):
        if temp_val == 0 and tint_val == 0: return img
        # (保留 v12 的白平衡算法，這部分沒問題)
        r, g, b = img.split()
        r_factor = 1.0 + (temp_val * 0.25)
        b_factor = 1.0 - (temp_val * 0.25)
        g_factor = 1.0 - (tint_val * 0.25)
        r = r.point(lambda i: int(min(255, max(0, i * r_factor))))
        g = g.point(lambda i: int(min(255, max(0, i * g_factor))))
        b = b.point(lambda i: int(min(255, max(0, i * b_factor))))
        return PIL.Image.merge("RGB", (r, g, b))

    def apply_lut(self, image_path, lut_name_or_path, intensity=1.0,
                  brightness=1.0, saturation=1.0, temperature=0.0, tint=0.0,
                  contrast=1.0, curve="Linear", sharpness=1.0):
        """
        v13: 加入 Curve 與 Sharpness 參數
        """
        try:
            with PIL.Image.open(image_path) as im:
                img = PIL.ImageOps.exif_transpose(im).convert("RGB")

            # 1. 基礎校正 (Pre-processing)
            if brightness != 1.0:
                img = PIL.ImageEnhance.Brightness(img).enhance(brightness)
            if temperature != 0 or tint != 0:
                img = self._adjust_white_balance(img, temperature, tint)

            # v13 改進: 對比度改在曲線前做，或者直接用曲線取代
            if contrast != 1.0:
                img = PIL.ImageEnhance.Contrast(img).enhance(contrast)

            if saturation != 1.0:
                img = PIL.ImageEnhance.Color(img).enhance(saturation)

            # 2. 曲線應用 (v13 New Feature)
            # 這是創造「富士感」或「電影感」的關鍵，比單純 Contrast 細膩
            img = self._apply_curve(img, curve)

            # 3. LUT 搜尋與套用
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
                    if matches: target_path = self.lut_index[matches[0]][0]

            if not target_path:
                Logger.error(f"找不到 LUT: {lut_name_or_path}")
                # 找不到 LUT 至少回傳修整過基礎參數的圖
                return img, "找不到 LUT，僅執行基礎修圖"

            # 強度 clamp
            intensity = max(0.0, min(1.0, float(intensity)))

            # Log LUT 自動偵測防護 (如果 AI 沒擋住，這裡做最後一道防線)
            if "log" in os.path.basename(target_path).lower() and intensity > 0.4:
                Logger.warn("引擎偵測到 Log LUT，自動降低強度以避免畫質破壞。")
                intensity = 0.35

            try:
                lut = self._get_lut_object(target_path)
                filtered_img = img.filter(lut)
            except Exception as e:
                return None, f"LUT 檔案損壞: {e}"

            # 混合
            if intensity < 1.0:
                final_img = PIL.Image.blend(img, filtered_img, intensity)
            else:
                final_img = filtered_img

            # 4. 銳利度調整 (Post-processing)
            # 數位照片通常太銳利，降低銳利度可以增加膠片感
            if sharpness != 1.0:
                final_img = PIL.ImageEnhance.Sharpness(final_img).enhance(sharpness)

            return final_img, "成功"

        except Exception as e:
            Logger.error(f"Engine Error: {e}")
            return None, str(e)