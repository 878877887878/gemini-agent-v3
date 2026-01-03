import json
import os  # 補上 os 模組以修復之前的路徑檢查錯誤
import google.generativeai as genai


class SmartPlanner:
    def __init__(self, api_key, rag_engine):
        genai.configure(api_key=api_key)
        self.rag = rag_engine
        # [修改] 切換為 gemini-3-pro-preview
        self.model = genai.GenerativeModel('gemini-3-pro-preview')

    def generate_plan(self, image_path, user_request):
        """
        視覺推理流程：
        1. RAG 檢索可用武器
        2. Gemini Vision 觀察圖片 + 思考策略
        3. 輸出 JSON 施工圖
        """

        # 1. RAG: 先去腦袋找找有哪些相關濾鏡
        available_luts = self.rag.search(user_request)

        # 2. Construct Prompt (Visual Chain-of-Thought)
        prompt = f"""
        你是一位專業的影像調色師。請分析這張圖片並制定修圖計畫。

        【使用者需求】
        "{user_request}"

        【建議參考濾鏡 (來自知識庫，請從中選擇或使用你認為更合適的)】
        {available_luts}

        【任務步驟】
        1. **觀察 (Observe)**: 分析圖片的光影、色溫、曝光與當前氛圍。
        2. **診斷 (Diagnose)**: 判斷使用者需求與現況的差距。
        3. **決策 (Decide)**: 
           - 選擇一個最合適的 LUT。
           - **決定強度 (Intensity)**: 0.0~1.0。如果原圖已經很接近風格，強度調低；如果需要大改，強度調高。
        4. **文案 (Caption)**: 根據修圖後的預期成果，寫一段 IG 文案。

        請直接回傳 **純 JSON 格式** (不要 Markdown，不要 ```json):
        {{
            "analysis": "圖片偏暗，色溫偏暖...",
            "reasoning": "使用者想要日系冷白，需要校正白平衡並拉高亮度...",
            "selected_lut": "完整濾鏡檔名.cube",
            "intensity": 0.8,
            "caption": "生成的文案..."
        }}
        """

        # 3. Call Vision API
        try:
            # [安全檢查] 確認檔案存在
            if not os.path.isfile(image_path):
                return {
                    "analysis": "錯誤",
                    "reasoning": f"這不是檔案: {image_path}",
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
                "analysis": "API 呼叫失敗",
                "reasoning": f"錯誤: {e}",
                "selected_lut": None
            }