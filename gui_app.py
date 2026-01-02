import gradio as gr
import os
import sys
import json
import asyncio
import shutil
from datetime import datetime
from PIL import Image
from pillow_lut import load_cube_file
import google.generativeai as genai
from dotenv import load_dotenv

# ================= 復用原本的核心邏輯 =================

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
LUT_DIR = "luts"
BACKUP_DIR = "backups"

# 忽略 Google SDK 的過期警告 (暫時性修正，以免干擾視窗)
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

if API_KEY:
    try:
        genai.configure(api_key=API_KEY)
    except Exception as e:
        print(f"⚠️ Gemini API 設定失敗: {e}")


class LUTManager:
    def list_luts(self):
        if not os.path.exists(LUT_DIR): return []
        return [f for f in os.listdir(LUT_DIR) if f.endswith('.cube')]

    def load_lut(self, name):
        try:
            return load_cube_file(os.path.join(LUT_DIR, name))
        except:
            return None


class LogicCore:
    """將原本的 Console 邏輯封裝給 GUI 使用"""

    def __init__(self):
        self.lut_manager = LUTManager()

    async def process_image(self, image, lut_name, enable_ai_caption):
        """處理單張圖片 (供 GUI 預覽與處理用)"""
        # 1. 套用 LUT
        if lut_name:
            lut = self.lut_manager.load_lut(lut_name)
            if lut:
                image = image.filter(lut)

        caption = "AI 分析未啟用 (請檢查 API Key 或勾選啟用)"

        # 2. AI 分析 (如果有勾選)
        if enable_ai_caption and API_KEY:
            try:
                # 使用舊版 SDK 的呼叫方式 (維持與 agent.py 相容)
                model = genai.GenerativeModel('gemini-3-pro-preview')
                prompt = "請用繁體中文分析這張照片的構圖、光影與氛圍，並寫一段適合 IG 的文案。"

                # 在執行緒中執行以避免卡住 GUI
                response = await asyncio.to_thread(model.generate_content, [prompt, image])
                caption = response.text
            except Exception as e:
                caption = f"分析失敗: {e}\n(可能是 API Key 問題或是 Google SDK 版本過舊)"

        return image, caption

    def create_backup(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not os.path.exists(BACKUP_DIR): os.makedirs(BACKUP_DIR)
        shutil.copy2(__file__, os.path.join(BACKUP_DIR, f"gui_backup_{timestamp}.py"))
        return f"✅ 備份完成: {timestamp}"


# ================= GUI 介面設計 =================

logic = LogicCore()


# --- 分頁 1: AI 聊天室 ---
async def chat_response(message, history):
    """處理聊天訊息"""
    if not API_KEY:
        return "❌ 錯誤：未設定 GEMINI_API_KEY"

    system_prompt = f"""
    你是一個 AI 助理，透過 Gradio GUI 運作。
    目前的可用濾鏡: {logic.lut_manager.list_luts()}
    如果使用者想處理照片，請引導他們去「圖片處理實驗室」分頁。
    如果使用者想備份，請回傳 JSON: {{"action": "backup"}}
    """

    try:
        model = genai.GenerativeModel(
            model_name='gemini-3-pro-preview',
            system_instruction=system_prompt
        )
        chat = model.start_chat(history=[])
        response = await asyncio.to_thread(chat.send_message, message)
        text = response.text

        if '{"action": "backup"}' in text:
            msg = logic.create_backup()
            return f"{text}\n\n(系統訊息: {msg})"

        return text
    except Exception as e:
        return f"❌ AI 回應發生錯誤: {e}"


# --- 分頁 2: 圖片處理實驗室 ---
async def process_pipeline(image, lut_dropdown, ai_check):
    if image is None:
        return None, "請先上傳圖片"

    try:
        pil_image = Image.fromarray(image).convert('RGB')
        processed_img, caption = await logic.process_image(pil_image, lut_dropdown, ai_check)
        return processed_img, caption
    except Exception as e:
        return None, f"處理過程發生錯誤: {e}"


# --- 建構 Gradio App ---
def create_ui():
    custom_css = """
    footer {visibility: hidden}
    .gradio-container {background-color: #f0f2f6}
    """

    # 移除 theme 和 css 參數，改在 launch 中設定 (或是直接省略以避免版本衝突)
    with gr.Blocks(title="Gemini Agent GUI") as app:
        gr.Markdown("# 🤖 Gemini AI Agent 控制台")

        with gr.Tabs():
            # Tab 1: 聊天
            with gr.TabItem("💬 AI 助手"):
                gr.ChatInterface(
                    fn=chat_response,
                    examples=["幫我備份程式碼", "最近有什麼推薦的濾鏡？", "你會做什麼？"],
                    title="Agent Chat"
                )

            # Tab 2: 修圖
            with gr.TabItem("🎨 圖片處理實驗室"):
                with gr.Row():
                    with gr.Column(scale=1):
                        input_img = gr.Image(label="上傳圖片", sources=["upload", "clipboard"])

                        luts = logic.lut_manager.list_luts()
                        lut_dropdown = gr.Dropdown(choices=luts, label="選擇濾鏡 (LUT)",
                                                   value=luts[0] if luts else None)

                        ai_check = gr.Checkbox(label="啟用 AI 視覺分析", value=True)
                        btn_run = gr.Button("✨ 開始處理", variant="primary")

                    with gr.Column(scale=1):
                        output_img = gr.Image(label="處理結果", type="pil")
                        # 修正: 移除了 show_copy_button 參數以相容舊版 Gradio
                        output_text = gr.Textbox(label="AI 產生的文案", lines=5)

                btn_run.click(
                    fn=process_pipeline,
                    inputs=[input_img, lut_dropdown, ai_check],
                    outputs=[output_img, output_text]
                )

            # Tab 3: 系統資訊
            with gr.TabItem("⚙️ 系統狀態"):
                gr.Markdown(f"""
                ### 系統資訊
                - **API Key Status**: {'✅ 已設定' if API_KEY else '❌ 未設定'}
                - **LUT 數量**: {len(logic.lut_manager.list_luts())}
                - **備份目錄**: {BACKUP_DIR}
                """)
                btn_refresh = gr.Button("重新掃描 LUT")

                def refresh_luts():
                    new_luts = logic.lut_manager.list_luts()
                    return gr.Dropdown(choices=new_luts)

                btn_refresh.click(refresh_luts, outputs=lut_dropdown)

    return app


if __name__ == "__main__":
    ui = create_ui()
    # 將 theme 和 css 移到這裡 (如果您的 Gradio 版本支援的話)，或直接不設定以求最穩定
    # 這裡使用最基本的設定以確保能執行
    ui.queue().launch(inbrowser=True, server_name="127.0.0.1", server_port=7860)