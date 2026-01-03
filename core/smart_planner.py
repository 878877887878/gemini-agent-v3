import json
import os
import re
import google.generativeai as genai
from PIL import Image
from core.logger import Logger


class SmartPlanner:
    def __init__(self, api_key, rag_engine):
        genai.configure(api_key=api_key)
        self.rag = rag_engine
        self.model = genai.GenerativeModel('gemini-3-pro-preview')
        Logger.info("SmartPlanner (Gemini 3 Pro) 初始化完成")

    def _extract_json(self, text):
        try:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception as e:
            Logger.warn(f"JSON 提取失敗: {e}")
        return None

    def generate_plan(self, image_path, user_request):
        Logger.info(f"開始策劃修圖: {user_request}")

        available_luts = self.rag.search(user_request, n_results=60)

        # v13 Prompt: 加入 Log LUT 防呆與曲線控制
        prompt = f"""
        你是一位好萊塢等級的 DI 調色師。請分析這張圖片並制定修圖計畫。

        【使用者需求】
        "{user_request}"

        【 📚 可用 LUT 資源庫 】
        {available_luts}

        【 ⚠️ 關鍵守則：Log LUT 防呆 】
        1. **檢查檔名**：如果圖片看起來是標準對比 (JPG/PNG 直出)，**絕對禁止** 選擇檔名包含 "Log", "FLog", "SLog", "VLog", "Raw" 的技術還原 LUT。
        2. **後果**：在普通照片上套用 Log LUT 會導致膚色爆紅、暗部死黑（如使用者抱怨的「烤焦」效果）。
        3. **替代方案**：請優先選擇帶有 "Rec709", "Standard", "Film", "Creative" 或無特殊標記的風格化 LUT。

        【 🛠️ 參數決策 (細膩度優先) 】
        1. **富士/膠片感 (Fuji/Film Look)**: 
           - 重點是「通透感」與「柔和高光」。不要過度增加對比。
           - 若原圖已是數位直出，通常需要 `contrast: 0.9` (降低數位銳利感) 甚至 `0.85`。
           - 膚色保護：若原圖偏紅，請用 `tint: -0.1` (往綠偏移) 來校正。
        2. **參數定義**:
           - `curve`: "S-Curve" (電影感), "Linear" (無), "Soft-High" (柔化高光), "Lift-Shadow" (拉提暗部)
           - `sharpness`: 銳利度 (0.0~2.0, 富士感通常設 0.8 讓畫質軟一點)

        請回傳 **純 JSON 格式**：
        {{
            "technical_analysis": "原圖為標準 Rec709 直出，膚色受室內光影響偏暖...",
            "style_strategy": "避開 F-Log LUT，選擇標準膠片模擬 LUT。降低數位銳利度，使用 S 曲線營造層次...",
            "selected_lut": "非Log的風格檔名.cube",
            "intensity": 0.6,
            "brightness": 1.0,
            "contrast": 0.9,
            "saturation": 0.9,
            "temperature": -0.1,
            "tint": 0.0,
            "curve": "Soft-High", 
            "sharpness": 0.9,
            "caption": "..."
        }}
        """

        try:
            if not os.path.isfile(image_path):
                return {"selected_lut": None, "reasoning": "找不到圖片"}

            temp_thumb = "temp_analysis_thumb.jpg"
            with Image.open(image_path) as img:
                img.thumbnail((1024, 1024))
                img.save(temp_thumb, quality=85)

            img_file = genai.upload_file(temp_thumb)
            response = self.model.generate_content([prompt, img_file])
            Logger.debug(f"AI 思考: {response.text[:100]}...")

            plan = self._extract_json(response.text)

            # v13 強制防呆檢查 (Double Check)
            if plan and plan.get('selected_lut'):
                lut_name = plan['selected_lut'].lower()
                if any(x in lut_name for x in ['log', 'raw']) and plan.get('intensity', 1.0) > 0.4:
                    Logger.warn(f"AI 選到了 Log LUT ({lut_name}) 但原圖似乎是 JPG。強制降低強度。")
                    plan['intensity'] = 0.3  # 強制壓低強度以挽救畫質

            return plan

        except Exception as e:
            Logger.error(f"SmartPlanner 錯誤: {e}")
            return {"selected_lut": None, "reasoning": str(e)}