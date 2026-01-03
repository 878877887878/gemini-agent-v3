import json
import os
import google.generativeai as genai


class SmartPlanner:
    def __init__(self, api_key, rag_engine):
        genai.configure(api_key=api_key)
        self.rag = rag_engine
        # 使用 Gemini 3 Pro (Context Window 夠大)
        self.model = genai.GenerativeModel('gemini-3-pro-preview')

    def generate_plan(self, image_path, user_request):
        """
        視覺推理核心
        """

        # [修改點] 大幅增加檢索數量 (60 個)
        available_luts = self.rag.search(user_request, n_results=60)

        # 2. 建構 Visual CoT Prompt
        prompt = f"""
        你是一位專業的影像調色師。請分析這張圖片並制定修圖計畫。

        【使用者需求】
        "{user_request}"

        【 📚 你的濾鏡軍火庫 (已篩選最相關的 60 款) 】
        {available_luts}

        【任務要求】
        1. **拒絕無聊**：請嘗試從上方清單中，挑選最適合但「不一定是最常見」的濾鏡。不要總是選第一個。
        2. **視覺分析**：觀察圖片的光線、色溫、曝光。
        3. **決策制定**：
           - 選擇一個 LUT (必須是清單中確切存在的檔名)。
           - 決定強度 (Intensity 0.0~1.0)。
        4. **文案構思**：寫一段符合氛圍的 IG 文案。

        請直接回傳 **純 JSON 格式** (不要 Markdown):
        {{
            "analysis": "圖片分析...",
            "reasoning": "為什麼選這個濾鏡...",
            "selected_lut": "完整檔名.cube",
            "intensity": 0.8,
            "caption": "文案..."
        }}
        """

        # 3. Call Vision API
        try:
            if not os.path.isfile(image_path):
                return {
                    "analysis": "錯誤",
                    "reasoning": f"找不到檔案: {image_path}",
                    "selected_lut": None
                }

            img_file = genai.upload_file(image_path)
            response = self.model.generate_content([prompt, img_file])

            # 清理 JSON 字串
            text = response.text.strip()
            if text.startswith("```json"):
                text = text.split("```json")[1]
            if text.endswith("```"):
                text = text.split("```")[0]

            return json.loads(text)
        except Exception as e:
            print(f"❌ 策劃失敗: {e}")
            return {
                "analysis": "API Error",
                "reasoning": str(e),
                "selected_lut": None
            }