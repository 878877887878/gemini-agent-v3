import gradio as gr
import os
import sys
import asyncio
import warnings
import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.lut_engine import LUTEngine
from core.rag_core import KnowledgeBase
from core.smart_planner import SmartPlanner
from core.memory_manager import MemoryManager
from core.security import execute_safe_command
from core.logger import Logger

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    print("❌ 錯誤: 請在 .env 設定 GEMINI_API_KEY")
    sys.exit(1)

Logger.info("正在啟動 GUI 核心系統 (v13 Cinematic)...")
memory_mgr = MemoryManager()
lut_engine = LUTEngine()
rag = KnowledgeBase()

all_luts = lut_engine.list_luts()
if all_luts:
    rag.index_luts(all_luts)

planner = SmartPlanner(API_KEY, rag)


# 工具函式
def remember_user_preference(info: str):
    Logger.info(f"GUI 觸發記憶寫入: {info}")
    return memory_mgr.add_preference(info)


def check_available_luts(keyword: str = ""):
    all_names = list(lut_engine.lut_index.keys())
    if keyword:
        filtered = [n for n in all_names if keyword.lower() in n]
        if not filtered:
            return f"找不到包含 '{keyword}' 的濾鏡。"
        return f"找到 {len(filtered)} 個相關濾鏡..."
    return f"系統目前擁有 {len(all_names)} 個濾鏡。"


# 對話邏輯
def create_chat_session():
    genai.configure(api_key=API_KEY)
    tools = [execute_safe_command, remember_user_preference, check_available_luts]
    base_prompt = """
    你是一個強大的 AI 助理 (Gemini 3 Pro)。
    【行為準則】引導使用圖片模式、執行白名單指令、記憶偏好。
    """
    dynamic_context = memory_mgr.get_system_prompt_addition()
    model = genai.GenerativeModel(
        model_name='gemini-3-pro-preview',
        tools=tools,
        system_instruction=base_prompt + dynamic_context
    )
    return model.start_chat(enable_automatic_function_calling=True)


def chat_response(message, history, session_state):
    if session_state is None:
        session_state = create_chat_session()
    try:
        Logger.debug(f"GUI 對話請求: {message}")
        response = session_state.send_message(message)
        return response.text, session_state
    except Exception as e:
        Logger.error(f"GUI 對話錯誤: {e}")
        return f"❌ 發生錯誤: {str(e)}", session_state


# ================= 視覺邏輯 (v13 Update) =================
def process_image_smartly(image, user_req):
    Logger.info(f"GUI 觸發修圖，需求: {user_req}")
    if image is None: return None, "❌ 請先上傳圖片"
    if not user_req: user_req = "自動調整"

    temp_path = "temp_gui_input.jpg"
    image.save(temp_path)

    plan = planner.generate_plan(temp_path, user_req)

    if not plan or not plan.get('selected_lut'):
        return None, f"⚠️ AI 思考失敗: {plan.get('reasoning', '未知錯誤')}"

    # v13 傳遞所有新參數 (含 Curve/Sharpness)
    final_img, msg = lut_engine.apply_lut(
        temp_path,
        plan['selected_lut'],
        intensity=plan.get('intensity', 1.0),
        brightness=plan.get('brightness', 1.0),
        saturation=plan.get('saturation', 1.0),
        temperature=plan.get('temperature', 0.0),
        tint=plan.get('tint', 0.0),
        contrast=plan.get('contrast', 1.0),
        curve=plan.get('curve', 'Linear'),  # 新增
        sharpness=plan.get('sharpness', 1.0)  # 新增
    )

    # v13 專業報告
    report = f"""### 🎨 AI 調色師報告 (v13)
**技術分析**: {plan.get('technical_analysis', '無')}
**調色策略**: {plan.get('style_strategy', '無')}

| 參數類別 | 設定值 |
| :--- | :--- |
| **LUT** | `{plan.get('selected_lut')}` (強度 {plan.get('intensity')}) |
| **色彩平衡** | Temp: `{plan.get('temperature')}` / Tint: `{plan.get('tint')}` |
| **曝光質感** | Curve: `{plan.get('curve')}` / Bright: `{plan.get('brightness')}` |
| **細節** | Sharpness: `{plan.get('sharpness')}` / Contrast: `{plan.get('contrast')}` |

> {plan.get('caption')}
"""
    return final_img, report


def get_current_memory():
    mem = memory_mgr._load_memory()
    prefs = mem.get("user_preferences", [])
    if not prefs: return "目前沒有記憶資料。"
    return "\n".join([f"- {p}" for p in prefs])


# GUI 建構
with gr.Blocks(title="Gemini Agent v13 (Cinematic)") as app:
    gr.Markdown("# 🤖 Gemini Agent v13 (Cinematic Grade)")
    gr.Markdown("引擎特色：`Log LUT 防呆` + `S-Curve 電影曲線` + `Tint 膚色校正`")

    chat_state = gr.State(None)

    with gr.Tabs():
        with gr.TabItem("👁️ 智能視覺修圖"):
            with gr.Row():
                with gr.Column(scale=1):
                    input_img = gr.Image(type="pil", label="上傳圖片")
                    style_input = gr.Textbox(label="風格需求", placeholder="日系冷白、電影感...", lines=2)
                    btn_process = gr.Button("🚀 開始 v13 修圖", variant="primary")
                with gr.Column(scale=1):
                    output_img = gr.Image(label="處理結果", type="pil")
                    output_info = gr.Markdown(label="AI 思考報告")
            btn_process.click(
                process_image_smartly,
                inputs=[input_img, style_input],
                outputs=[output_img, output_info]
            )

        with gr.TabItem("💬 核心大腦"):
            chatbot = gr.Chatbot(height=500)
            msg_input = gr.Textbox(label="User", placeholder="聊天或指令...")


            def user_msg(user_message, history):
                return "", history + [[user_message, None]]


            def bot_msg(history, state):
                user_message = history[-1][0]
                bot_response, new_state = chat_response(user_message, history, state)
                history[-1][1] = bot_response
                return history, new_state


            msg_input.submit(user_msg, [msg_input, chatbot], [msg_input, chatbot], queue=False).then(
                bot_msg, [chatbot, chat_state], [chatbot, chat_state]
            )

        with gr.TabItem("🧠 記憶庫"):
            memory_display = gr.Textbox(label="User Memory", value=get_current_memory(), lines=10, interactive=False)
            btn_refresh = gr.Button("🔄 重新讀取")
            btn_refresh.click(get_current_memory, outputs=memory_display)

if __name__ == "__main__":
    app.queue().launch(inbrowser=True, server_name="127.0.0.1")