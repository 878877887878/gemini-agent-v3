import os
import PIL.Image
from pillow_lut import load_cube_file

class LUTEngine:
    def __init__(self, lut_dir="luts"):
        self.lut_dir = lut_dir

    def list_luts(self):
        """遞迴列出所有 .cube 檔案"""
        luts = []
        if not os.path.exists(self.lut_dir):
            return []
            
        for root, _, files in os.walk(self.lut_dir):
            for f in files:
                if f.lower().endswith('.cube'):
                    # 回傳完整路徑，方便後續處理
                    luts.append(os.path.join(root, f))
        return luts

    def get_lut_name(self, path):
        """從路徑取得乾淨的檔名"""
        return os.path.basename(path)

    def apply_lut(self, image_path, lut_name_or_path, intensity=1.0):
        """
        智能套用 LUT
        intensity: 0.0 (原圖) ~ 1.0 (完全套用)
        """
        try:
            # 載入圖片
            img = PIL.Image.open(image_path).convert("RGB")
            
            # 判斷輸入是檔名還是路徑
            lut_path = None
            if os.path.exists(lut_name_or_path):
                lut_path = lut_name_or_path
            else:
                # 如果只給檔名，嘗試搜尋
                all_luts = self.list_luts()
                # 簡單模糊比對
                for path in all_luts:
                    if lut_name_or_path.lower() in os.path.basename(path).lower():
                        lut_path = path
                        break
            
            if not lut_path:
                return None, f"找不到 LUT: {lut_name_or_path}"

            if intensity <= 0:
                return img, "強度為 0，未修改"

            # 載入 LUT 並套用
            try:
                lut = load_cube_file(lut_path)
            except Exception as e:
                return None, f"LUT 格式錯誤: {e}"

            filtered_img = img.filter(lut)

            # 混合模式 (Blending) 實現強度控制
            if intensity < 1.0:
                final_img = PIL.Image.blend(img, filtered_img, intensity)
            else:
                final_img = filtered_img

            return final_img, "成功"
        except Exception as e:
            return None, str(e)