import os
import sys
import asyncio
import time
import subprocess
import google.generativeai as genai
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.markdown import Markdown
from rich.progress import track

# 匯入 v5 核心模組
from core.lut_engine import LUTEngine
from core.rag_core import KnowledgeBase
from core.smart_planner import SmartPlanner

# 設定
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
console = Console()

if not API_KEY:
    console.print("[red]❌ 錯誤: 請在 .env 設定 GEMINI_API_KEY[/]")
    sys.exit(1)


# ==========================================
# 🔧 工具函式：執行系統指令
# ==========================================
def execute_terminal_command(command: str):
    """執行 Windows 終端機指令 (例如 git commit, dir...)"""
    try:
        console.print(f"[dim]💻 正在執行: {command}[/]")
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8'  # 防止中文亂碼
        )
        if result.returncode == 0:
            return f"✅ 執行成功:\n{result.stdout}"
        else:
            return f"❌ 執行失敗:\n{result.stderr}"
    except Exception as e:
        return f"⚠️ 系統錯誤: {str(e)}"


# ==========================================
# 🧠 建立通用對話大腦 (處理非圖片需求)
# ==========================================
def create_chat_session():
    genai.configure(api_key=API_KEY)

    tools = [execute_terminal_command]

    # [修改] 切換為 gemini-3-pro-preview
    model = genai.GenerativeModel(
        model_name='gemini-3-pro-preview',
        tools=tools,
        system_instruction="""
        你是一個強大的 AI 助理 (Gemini 3 Pro)。
        1. 如果使用者輸入路徑或要求修圖，請引導他們使用圖片模式。
        2. 如果使用者輸入系統指令（如 git, dir, mkdir），請使用 execute_terminal_command 工具執行。
        3. 回答請簡潔有力，使用繁體中文。
        """
    )
    return model.start_chat(enable_automatic_function_calling=True)


# ==========================================
# 🎮 介面邏輯 (保留 v5 的優雅輸入)
# ==========================================
def get_input_safe(prompt_text):
    while True:
        try:
            user_in = console.input(prompt_text)
            if not user_in.strip(): continue
            return user_in.strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]↩️  取消...[/]")
            return None


def select_files_from_directory(dir_path):
    valid_exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff')
    try:
        files = [f for f in os.listdir(dir_path) if f.lower().endswith(valid_exts)]
    except Exception:
        return None

    if not files: return None

    table = Table(title=f"📂 資料夾: {dir_path}")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("檔名", style="green")
    table.add_row("0", "🚀 [bold yellow]批次處理全部[/]")

    for idx, f in enumerate(files):
        table.add_row(str(idx + 1), f)

    console.print(table)

    while True:
        selection = get_input_safe(f"[yellow]請選擇 ID (0-{len(files)}): [/]")
        if selection is None or selection.lower() in ['q', 'exit']: return None
        try:
            idx = int(selection)
            if idx == 0: return [os.path.join(dir_path, f) for f in files]
            if 0 < idx <= len(files): return [os.path.join(dir_path, files[idx - 1])]
        except ValueError:
            pass


# ==========================================
# 🚀 主程式 (Hybrid Loop)
# ==========================================
async def main():
    console.clear()
    console.print(Panel.fit("[bold cyan]🤖 Gemini Agent v6 (Hybrid: Visual + Chat)[/]", border_style="cyan"))

    # 1. 初始化所有模組
    with console.status("[bold green]正在啟動雙核大腦 (Gemini 3 Pro)...[/]"):
        try:
            # 視覺模組
            engine = LUTEngine()
            rag = KnowledgeBase()
            planner = SmartPlanner(API_KEY, rag)
            all_luts = engine.list_luts()
            if all_luts: rag.index_luts(all_luts)

            # 對話模組
            chat_session = create_chat_session()

        except KeyboardInterrupt:
            return

    console.print(f"[dim]✅ 系統就緒：已載入 {len(all_luts)} 個濾鏡 | Git 指令模組已連線[/]\n")

    while True:
        console.print("\n[dim]──────────────────────────────────────────────────[/]")
        user_input = get_input_safe("[yellow]請輸入 [bold white]圖片路徑[/] 或 [bold white]指令/聊天[/]: [/]")

        if user_input is None:  # Ctrl+C at main menu
            if Confirm.ask("\n[bold yellow]要離開程式嗎？[/]"): break
            continue

        if user_input.lower() in ["exit", "quit"]: break

        # 去除引號
        raw_input = user_input.replace('"', '').replace("'", "")

        # 🔍 判斷意圖：是路徑還是指令？
        is_path_target = False
        target_path = raw_input

        if not os.path.exists(target_path):
            check_input = os.path.join("input", target_path)
            if os.path.exists(check_input):
                target_path = check_input

        if os.path.exists(target_path):
            is_path_target = True

        # 🔀 分流處理
        if is_path_target:
            # ========================
            # 🖼️ 進入視覺處理模式
            # ========================
            console.print("[bold cyan]🖼️ 偵測到圖片/資料夾，進入視覺處理模式[/]")

            target_files = []
            if os.path.isdir(target_path):
                target_files = select_files_from_directory(target_path)
                if not target_files: continue
            else:
                target_files = [target_path]

            count = len(target_files)
            style_req = get_input_safe("[green]🎨 請描述想要的風格 (例如: 日系冷白): [/]")
            if not style_req: continue

            console.print(f"\n[bold cyan]🚀 Smart Planner (Gemini 3) 思考中...[/]")
            try:
                iterator = track(target_files, description="修圖進度") if count > 1 else target_files
                for img_path in iterator:
                    plan = await asyncio.to_thread(planner.generate_plan, img_path, style_req)

                    if plan and plan.get('selected_lut'):
                        if count == 1:
                            console.print(
                                Panel(f"策略: {plan['reasoning']}\nLUT: {plan['selected_lut']}", title="AI 決策"))

                        final_img, msg = engine.apply_lut(img_path, plan['selected_lut'], plan.get('intensity', 1.0))
                        if final_img:
                            if not os.path.exists("output"): os.makedirs("output")
                            save_path = f"output/v6_{os.path.basename(img_path)}"
                            final_img.save(save_path)
                            console.print(f"   [green]✅ 儲存: {save_path}[/]")
            except KeyboardInterrupt:
                console.print("[red]🛑 任務中斷[/]")

        else:
            # ========================
            # 💬 進入通用對話模式
            # ========================
            with console.status("[bold magenta]🧠 Gemini 3 Pro 正在思考/執行指令...[/]", spinner="dots"):
                try:
                    response = await asyncio.to_thread(chat_session.send_message, user_input)
                    console.print(Panel(
                        Markdown(response.text),
                        title="🤖 Gemini Assistant",
                        border_style="magenta"
                    ))
                except Exception as e:
                    console.print(f"[red]❌ 發生錯誤: {e}[/]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程式結束。")