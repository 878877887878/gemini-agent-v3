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
        """使用 Regex 強制提取 JSON 物件 (忽略 Markdown 符號)"""
        try:
            # 尋找最外層的 {}
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                json_str = match.group(0)
                return json.loads(json_str)
        except:
            pass
        return None

    def generate_plan(self, image_path, user_request):
        # 1. RAG 檢索 (給 60 個，增加多樣性)
        available_luts = self.rag.search(user_request, n_results=60)

        # 2. Prompt
        prompt = f"""
        你是一位專業調色師。
        需求："{user_request}"

        可用濾鏡庫 (請嚴格從中選擇，不要自己編造檔名)：
        {available_luts}

        請分析圖片並回傳 JSON (不要 Markdown)：
        {{
            "analysis": "...",
            "reasoning": "...",
            "selected_lut": "精確檔名.cube",
            "intensity": 0.8,
            "caption": "..."
        }}
        """

        try:
            if not os.path.isfile(image_path):
                return {"selected_lut": None, "reasoning": "找不到圖片"}

            # [優化] 製作暫存縮圖 (加速上傳)
            # AI 不需要看 4K 原圖就能判斷風格，縮到 1024px 足夠了
            temp_thumb = "temp_analysis_thumb.jpg"
            with Image.open(image_path) as img:
                img.thumbnail((1024, 1024))
                img.save(temp_thumb, quality=80)

            img_file = genai.upload_file(temp_thumb)
            response = self.model.generate_content([prompt, img_file])

            # 3. 穩健解析
            plan = self._extract_json(response.text)

            # 4. 驗證與保底 (Fallback)
            if not plan or not plan.get('selected_lut'):
                print("⚠️ JSON 解析失敗或欄位缺失，啟動保底策略")
                return {
                    "analysis": "解析失敗，使用自動推薦",
                    "reasoning": "Fallback strategy",
                    "selected_lut": available_luts[0] if available_luts else None,
                    "intensity": 0.7,
                    "caption": "風格修圖"
                }

            return plan

        except Exception as e:
            print(f"❌ Planner Error: {e}")
            return {"selected_lut": None, "reasoning": str(e)}