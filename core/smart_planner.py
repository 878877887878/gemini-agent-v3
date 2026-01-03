import json
import os
import re
import google.generativeai as genai
from PIL import Image


class SmartPlanner:
    def __init__(self, api_key, rag_engine):
        genai.configure(api_key=api_key)
        self.rag = rag_engine
        self.model = genai.GenerativeModel('gemini-3-pro-preview')

    def _extract_json(self, text):
        try:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except:
            pass
        return None

    def generate_plan(self, image_path, user_request):
        # 1. RAG 檢索
        available_luts = self.rag.search(user_request, n_results=60)

        # 2. Prompt (v11: 增加曝光/色彩控制指令)
        prompt = f"""
        你是一位專業調色師。請分析這張圖片，制定**全方位的修圖計畫**。

        【使用者需求】
        "{user_request}"

        【可用濾鏡資源】
        {available_luts}

        【修圖決策要求】
        1. **基礎修正**：如果原圖太暗/太亮或色偏嚴重，請先設定 Pre-processing 參數修正它。
           - `brightness`: 亮度乘數 (1.0=不變, 1.2=提亮20%, 0.8=變暗20%)
           - `saturation`: 飽和度乘數 (1.0=不變, 0.0=黑白, 1.3=鮮豔)
           - `temperature`: 色溫偏移 (-1.0=極冷/藍, 0.0=不變, 1.0=極暖/黃)
        2. **風格化**：選擇最合適的 LUT 與強度 (0.0~1.0)。
        3. **文案**：寫一段 IG 文案。

        請回傳 **純 JSON 格式**：
        {{
            "analysis": "原圖分析...",
            "reasoning": "修圖策略...",
            "selected_lut": "檔名.cube",
            "intensity": 0.8,
            "brightness": 1.0,
            "saturation": 1.0,
            "temperature": 0.0,
            "caption": "..."
        }}
        """

        try:
            if not os.path.isfile(image_path):
                return {"selected_lut": None, "reasoning": "找不到圖片"}

            # 縮圖加速
            temp_thumb = "temp_analysis_thumb.jpg"
            with Image.open(image_path) as img:
                img.thumbnail((1024, 1024))
                img.save(temp_thumb, quality=80)

            img_file = genai.upload_file(temp_thumb)
            response = self.model.generate_content([prompt, img_file])

            # 解析
            plan = self._extract_json(response.text)

            # 保底
            if not plan or not plan.get('selected_lut'):
                print("⚠️ JSON 解析失敗，使用保底值")
                return {
                    "analysis": "解析失敗",
                    "reasoning": "Fallback",
                    "selected_lut": available_luts[0] if available_luts else None,
                    "intensity": 0.7,
                    "brightness": 1.0,
                    "saturation": 1.0,
                    "temperature": 0.0,
                    "caption": "AI 修圖"
                }

            return plan

        except Exception as e:
            print(f"❌ Planner Error: {e}")
            return {"selected_lut": None, "reasoning": str(e)}