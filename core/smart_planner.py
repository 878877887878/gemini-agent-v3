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
        """
        使用 Regex 強制提取 JSON 物件 (忽略 Markdown 符號或廢話)
        """
        try:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception as e:
            Logger.warn(f"JSON 提取失敗: {e}")
        return None

    def generate_plan(self, image_path, user_request):
        Logger.info(f"開始策劃修圖: {user_request}")

        # 1. RAG 檢索：給 AI 足夠多的選擇 (60個)
        available_luts = self.rag.search(user_request, n_results=60)

        # 2. Prompt (v15: 上下文感知 + 權重修正)
        prompt = f"""
        你是一位好萊塢等級的 DI (Digital Intermediate) 專業調色師。
        請分析圖片並制定修圖計畫。

        【使用者當前需求】
        "{user_request}"

        【 📚 可用 LUT 資源庫 】
        {available_luts}

        【 ⚠️ 決策邏輯 (Priority Rules) 】
        1. **指令優先權 (Context First)**: 
           - 你的系統 Prompt 可能包含使用者的「長期偏好」(如: 喜歡日系冷白)。
           - **但是**，如果「當前需求」明確指定了相反風格 (如: "聖誕風格", "暖色", "復古")，請**務必忽略長期偏好**，以當前需求為準。
           - 只有當使用者說 "隨便"、"老樣子" 時，才使用長期偏好。

        2. **風格參數指引**:
           - **聖誕/溫馨/暖色**: 
             - 選擇暖色調 LUT。
             - 設定 `temperature`: 0.1 ~ 0.3 (偏暖)。
             - 設定 `saturation`: 1.0 ~ 1.2 (色彩飽滿)。
             - 設定 `contrast`: 1.0 ~ 1.1 (增加氛圍)。
           - **日系/冷白/科技**: 
             - 選擇冷色調 LUT。
             - 設定 `temperature`: -0.1 ~ -0.3 (偏冷)。
             - 設定 `saturation`: 0.7 ~ 0.9 (低飽和)。
             - 設定 `contrast`: 0.9 (柔和)。

        3. **Log LUT 防呆 (Log Detection)**:
           - 如果 selected_lut 檔名包含 "Log", "Raw", "Flat" 且原圖是 JPG (標準對比)。
           - 必須設定 `simulate_log: true` (開啟 Log 模擬器)。
           - 若開啟模擬，`intensity` 設為 1.0；若未開啟模擬但選了 Log LUT，`intensity` 強制降至 0.3。

        【 🛠️ 輸出參數定義 】
        - `curve`: "S-Curve"(電影感), "Soft-High"(柔化高光/富士感), "Linear"(無)
        - `sharpness`: 0.0~2.0 (數位照片建議 0.8~0.9 去除銳利感)
        - `temperature`/`tint`: 白平衡修正 (-1.0 ~ 1.0)
        - `brightness`/`contrast`/`saturation`: 基礎修正 (1.0 為基準)

        請回傳 **純 JSON 格式**：
        {{
            "technical_analysis": "原圖分析...",
            "style_strategy": "因使用者要求聖誕風格，故忽略長期記憶中的冷白偏好，改用暖色調策略...",
            "selected_lut": "完整檔名.cube",
            "simulate_log": false,
            "intensity": 0.8,
            "brightness": 1.0,
            "contrast": 1.0,
            "saturation": 1.0,
            "temperature": 0.0,
            "tint": 0.0,
            "curve": "Linear",
            "sharpness": 1.0,
            "caption": "IG文案..."
        }}
        """

        try:
            if not os.path.isfile(image_path):
                return {"selected_lut": None, "reasoning": "找不到圖片"}

            # 製作縮圖以加速 API 上傳 (1024px 足夠 AI 判斷光影與構圖)
            temp_thumb = "temp_analysis_thumb.jpg"
            with Image.open(image_path) as img:
                img.thumbnail((1024, 1024))
                img.save(temp_thumb, quality=85)

            img_file = genai.upload_file(temp_thumb)
            Logger.debug("圖片已上傳至 Gemini，等待分析...")

            response = self.model.generate_content([prompt, img_file])

            # 提取 JSON
            plan = self._extract_json(response.text)

            # --- v15 安全檢查與防呆機制 ---
            if plan and plan.get('selected_lut'):
                lut_name = plan['selected_lut'].lower()
                is_log_lut = any(x in lut_name for x in ['log', 'raw', 'flat'])

                # 防呆 1: 如果是 Log LUT 但 AI 忘了開模擬，強制幫它開
                if is_log_lut and not plan.get('simulate_log'):
                    Logger.warn(f"偵測到 Log LUT ({lut_name}) 但 AI 未啟用模擬，強制啟用 Log Simulation。")
                    plan['simulate_log'] = True
                    plan['intensity'] = 1.0  # 模擬模式下強度需全開才準

                # 防呆 2: 確保數值型別正確 (防止 AI 回傳字串導致報錯)
                for key in ['intensity', 'brightness', 'contrast', 'saturation', 'temperature', 'tint', 'sharpness']:
                    if key in plan:
                        try:
                            plan[key] = float(plan[key])
                        except:
                            plan[key] = 1.0 if key not in ['temperature', 'tint'] else 0.0

            else:
                # 保底策略 (Fallback)
                Logger.warn("AI 回傳格式錯誤或未選擇 LUT，啟動 Fallback 策略")
                return {
                    "technical_analysis": "解析失敗",
                    "style_strategy": "Fallback (使用預設值)",
                    "selected_lut": available_luts[0] if available_luts else None,
                    "simulate_log": False,
                    "intensity": 0.7,
                    "brightness": 1.0,
                    "contrast": 1.0,
                    "saturation": 1.0,
                    "temperature": 0.0,
                    "tint": 0.0,
                    "curve": "Linear",
                    "sharpness": 1.0,
                    "caption": "AI 自動修圖"
                }

            return plan

        except Exception as e:
            Logger.error(f"SmartPlanner 發生錯誤: {e}")
            return {"selected_lut": None, "reasoning": str(e)}