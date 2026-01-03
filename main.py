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
from core.memory_manager import MemoryManager

# ================= 系統設定 =================
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
console = Console()

if not API_KEY:
    console.print("[red]❌ 錯誤: 請在 .env 設定 GEMINI_API_KEY[/]")
    sys.exit(1)

# 初始化核心
memory_mgr = MemoryManager()
lut_engine = LUTEngine()
rag = KnowledgeBase()

# 索引建立
try:
    all_luts = lut_engine.list_luts()
    if all_luts:
        rag.index_luts(all_luts)
except Exception as e:
    console.print(f"[yellow]⚠️ 索引建立警告: {e}[/]")

planner = SmartPlanner(API_KEY, rag)


# ================= 工具函式 =================
def execute_terminal_command(command: str):
    """執行 Windows 終端機指令"""
    try:
        console.print(f"[dim]💻 正在執行: {command}[/]")
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        if result.returncode == 0:
            return f"✅ 執行成功:\n{result.stdout}"
        else:
            return f"❌ 執行失敗:\n{result.stderr}"
    except Exception as e:
        return f"⚠️ 系統錯誤: {str(e)}"


def remember_user_preference(info: str):
    """記憶工具"""
    console.print(f"[yellow]🧠 正在寫入記憶: {info}[/]")
    return memory_mgr.add_preference(info)


def check_available_luts(keyword: str = ""):
    """查詢本地 LUT 工具"""
    console.print(f"[dim]🔍 AI 正在翻閱 LUT 資料庫 (關鍵字: {keyword})...[/]")
    all_files = lut_engine.list_luts()
    names = [os.path.basename(f) for f in all_files]

    if keyword:
        filtered = [n for n in names if keyword.lower() in n.lower()]
        if not filtered:
            return f"找不到包含 '{keyword}' 的濾鏡，但系統共有 {len(names)} 個濾鏡可選。"
        return f"找到 {len(filtered)} 個相關濾鏡，例如: {', '.join(filtered[:30])}..."

    import random
    sample = random.sample(names, min(len(names), 30))
    return f"系統目前擁有 {len(names)} 個濾鏡。包含: {', '.join(sample)}... 等。"


def create_chat_session():
    """建立 Session (整合所有工具)"""
    genai.configure(api_key=API_KEY)

    # 這裡賦予了查閱 LUT 的權限
    tools = [execute_terminal_command, remember_user_preference, check_available_luts]

    base_prompt = """
    你是一個強大的 AI 助理 (Gemini 3 Pro)。

    【你的能力與資源】
    1. 你擁有「視覺引擎」，可以存取使用者硬碟中的 LUT 濾鏡 (透過 check_available_luts 工具)。
    2. 千萬不要說「我無法存取檔案」，你完全可以透過工具查閱。
    3. 如果使用者覺得濾鏡重複，請主動查詢 check_available_luts 並推薦其他款。

    【核心行為準則】
    1. 圖片處理：引導使用圖片模式。
    2. 系統指令：使用 execute_terminal_command。
    3. 記憶能力：使用 remember_user_preference。
    4. 語言風格：繁體中文，自信、專業。
    """

    dynamic_context = memory_mgr.get_system_prompt_addition()
    final_system_prompt = base_prompt + dynamic_context

    model = genai.GenerativeModel(
        model_name='gemini-3-pro-preview',
        tools=tools,
        system_instruction=final_system_prompt
    )
    return model.start_chat(enable_automatic_function_calling=True)


# ================= 介面邏輯 =================
def get_input_safe(prompt_text):
    while True:
        try:
            user_in = console.input(prompt_text)
            if not user_in.strip(): continue
            return user_in.strip()
        except (KeyboardInterrupt, EOFError):
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


# ================= 主程式 =================
async def main():
    console.clear()
    console.print(Panel.fit("[bold cyan]🤖 Gemini Agent v9 (Integrated CLI)[/]", border_style="cyan"))
    console.print(f"[dim]✅ 系統就緒：已載入 {len(all_luts)} 個濾鏡 | 雙核大腦已連線[/]\n")

    while True:
        try:
            console.print("\n[dim]──────────────────────────────────────────────────[/]")
            user_input = get_input_safe("[yellow]請輸入 [bold white]圖片路徑[/] 或 [bold white]指令/聊天[/]: [/]")

            if user_input is None:
                if Confirm.ask("\n[bold yellow]要離開程式嗎？[/]"): break
                continue

            if user_input.lower() in ["exit", "quit"]: break

            raw_input = user_input.replace('"', '').replace("'", "")
            target_path = raw_input
            if not os.path.exists(target_path):
                check_input = os.path.join("input", target_path)
                if os.path.exists(check_input): target_path = check_input

            if os.path.exists(target_path):
                # 🖼️ 視覺模式
                console.print("[bold cyan]🖼️ 偵測到圖片，進入視覺模式[/]")
                target_files = []
                if os.path.isdir(target_path):
                    target_files = select_files_from_directory(target_path)
                    if not target_files: continue
                else:
                    target_files = [target_path]

                count = len(target_files)
                style_req = get_input_safe("[green]🎨 請描述風格: [/]")
                if not style_req: continue

                console.print(f"\n[bold cyan]🚀 Smart Planner 思考中...[/]")
                try:
                    iterator = track(target_files, description="修圖進度") if count > 1 else target_files
                    for img_path in iterator:
                        plan = await asyncio.to_thread(planner.generate_plan, img_path, style_req)

                        if plan and plan.get('selected_lut'):
                            if count == 1:
                                console.print(
                                    Panel(f"策略: {plan['reasoning']}\nLUT: {plan['selected_lut']}", title="AI 決策"))
                            final_img, msg = lut_engine.apply_lut(img_path, plan['selected_lut'],
                                                                  plan.get('intensity', 1.0))
                            if final_img:
                                if not os.path.exists("output"): os.makedirs("output")
                                save_path = f"output/v9_{os.path.basename(img_path)}"
                                final_img.save(save_path)
                                console.print(f"   [green]✅ 儲存: {save_path}[/]")
                except KeyboardInterrupt:
                    console.print("\n[bold yellow]🛑 視覺任務已暫停[/]")

            else:
                # 💬 對話模式
                temp_session = create_chat_session()
                try:
                    with console.status("[bold magenta]🧠 Gemini 思考中...[/]", spinner="dots"):
                        response = await asyncio.to_thread(temp_session.send_message, user_input)
                        console.print(Panel(
                            Markdown(response.text),
                            title="🤖 Gemini Assistant",
                            border_style="magenta"
                        ))
                except KeyboardInterrupt:
                    console.print("\n[bold yellow]🛑 對話已取消[/]")
                except Exception as e:
                    console.print(f"[red]❌ 對話發生錯誤: {e}[/]")

        except KeyboardInterrupt:
            console.print("\n[bold yellow]⚠️ (已攔截中斷訊號)[/]")
            continue
        except Exception as e:
            console.print(f"\n[bold red]💥 系統錯誤: {e}[/]")
            await asyncio.sleep(1)
            continue


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程式結束。")