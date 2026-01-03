import gradio as gr
import os
import sys
import asyncio
import warnings
import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image

# 忽略警告
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.lut_engine import LUTEngine
from core.rag_core import KnowledgeBase
from core.smart_planner import SmartPlanner
from core.memory_manager import MemoryManager
from core.security import execute_safe_command  # [新增] 安全模組

# 系統初始化
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

print("🚀 正在啟動 GUI 核心系統...")
memory_mgr = MemoryManager()
lut_engine = LUTEngine()
rag = KnowledgeBase()

all_luts = lut_engine.list_luts()
if all_luts:
    rag.index_luts(all_luts)

planner = SmartPlanner(API_KEY, rag)


# ================= 工具函式 =================
def remember_user_preference(info: str):
    return memory_mgr.add_preference(info)


def check_available_luts(keyword: str = ""):
    """查詢本地 LUT 工具 (GUI 版)"""
    all_names = list(lut_engine.lut_index.keys())
    if keyword:
        filtered = [n for n in all_names if keyword.lower() in n]
        if not filtered:
            return f"找不到包含 '{keyword}' 的濾鏡，但系統共有 {len(all_names)} 個濾鏡。"
        return f"找到 {len(filtered)} 個相關濾鏡，例如: {', '.join(filtered[:30])}..."
    import random
    sample = random.sample(all_names, min(len(all_names), 30))
    return f"系統目前擁有 {len(all_names)} 個濾鏡。包含: {', '.join(sample)}... 等。"


# ================= 對話邏輯 =================
def create_chat_session():
    genai.configure(api_key=API_KEY)

    # [修改] 使用 execute_safe_command
    tools = [execute_safe_command, remember_user_preference, check_available_luts]

    base_prompt = """
    你是一個強大的 AI 助理 (Gemini 3 Pro)。
    這是一個 GUI 介面環境。

    【安全守則】
    1. 執行指令前，請使用 execute_safe_command，嚴禁執行刪除或破壞性指令。
    2. 遇到無法執行的指令 (被攔截)，請誠實告知使用者權限不足。

    【核心行為準則】
    1. 圖片處理：如果使用者上傳圖片或要求修圖，請引導他們切換到「👁️ 智能視覺修圖」分頁。
    2. 系統指令：可以使用 execute_safe_command 執行白名單指令。
    3. 記憶能力：如果使用者提到個人偏好，請務必使用 remember_user_preference 工具儲存。
    4. 語言風格：請使用繁體中文，回答親切且專業。
    """

    dynamic_context = memory_mgr.get_system_prompt_addition()
    final_prompt = base_prompt + dynamic_context

    model = genai.GenerativeModel(
        model_name='gemini-3-pro-preview',
        tools=tools,
        system_instruction=final_prompt
    )
    return model.start_chat(enable_automatic_function_calling=True)


def chat_response(message, history, session_state):
    if session_state is None:
        session_state = create_chat_session()

    try:
        response = session_state.send_message(message)
        return response.text, session_state
    except Exception as e:
        return f"❌ 發生錯誤: {str(e)}", session_state


# ================= 視覺邏輯 =================
def process_image_smartly(image, user_req):
    if image is None:
        return None, "❌ 請先上傳圖片"

    if not user_req:
        user_req = "自動調整，讓照片更好看"

    temp_path = "temp_gui_input.jpg"
    image.save(temp_path)

    plan = planner.generate_plan(temp_path, user_req)

    if not plan or not plan.get('selected_lut'):
        return None, f"⚠️ AI 思考失敗: {plan.get('reasoning', '未知錯誤')}"

    final_img, msg = lut_engine.apply_lut(
        temp_path,
        plan['selected_lut'],
        intensity=plan.get('intensity', 1.0)
    )

    report = f"""### ✅ AI 施工完成
**策略推理**: {plan.get('reasoning')}
**視覺分析**: {plan.get('analysis')}
**使用濾鏡**: `{plan.get('selected_lut')}` (強度: {plan.get('intensity')})
**推薦文案**:
> {plan.get('caption')}
"""
    return final_img, report


def get_current_memory():
    mem = memory_mgr._load_memory()
    prefs = mem.get("user_preferences", [])
    if not prefs:
        return "目前沒有記憶資料。"
    return "\n".join([f"- {p}" for p in prefs])


# ================= GUI 建構 =================
with gr.Blocks(title="Gemini Agent v10 (GUI)") as app:
    gr.Markdown("# 🤖 Gemini Agent v10 (Hybrid GUI)")
    gr.Markdown("雙核大腦：`Gemini 3 Pro` + `Visual Smart Planner` + `Secure Core`")

    chat_state = gr.State(None)

    with gr.Tabs():
        # Tab 1: 修圖
        with gr.TabItem("👁️ 智能視覺修圖"):
            with gr.Row():
                with gr.Column(scale=1):
                    input_img = gr.Image(type="pil", label="上傳圖片")
                    style_input = gr.Textbox(
                        label="風格需求",
                        placeholder="例如：日系冷白、王家衛風格、用我記憶中的招牌風格...",
                        lines=2
                    )
                    btn_process = gr.Button("🚀 開始 AI 修圖", variant="primary")
                with gr.Column(scale=1):
                    output_img = gr.Image(label="處理結果", type="pil")
                    output_info = gr.Markdown(label="AI 思考報告")
            btn_process.click(
                process_image_smartly,
                inputs=[input_img, style_input],
                outputs=[output_img, output_info]
            )

        # Tab 2: 對話
        with gr.TabItem("💬 核心大腦 (Chat & Memory)"):
            chatbot = gr.Chatbot(height=500)
            msg_input = gr.Textbox(placeholder="輸入文字... (例如：'我有什麼濾鏡?' 或 'git status')", label="User")


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

        # Tab 3: 記憶
        with gr.TabItem("🧠 大腦記憶庫"):
            gr.Markdown("以下是 AI 目前記住的關於您的偏好與規則：")
            memory_display = gr.Textbox(
                label="User Memory (user_memory.json)",
                value=get_current_memory(),
                lines=10,
                interactive=False
            )
            btn_refresh_mem = gr.Button("🔄 重新讀取記憶")
            btn_refresh_mem.click(get_current_memory, outputs=memory_display)

if __name__ == "__main__":
    app.queue().launch(inbrowser=True, server_name="127.0.0.1")