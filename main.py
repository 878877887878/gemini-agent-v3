import os
import sys
import asyncio
import time
import google.generativeai as genai
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.markdown import Markdown
from rich.progress import track

# 匯入 v13 核心模組
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
console = Console()

if not API_KEY:
    Logger.error("請在 .env 設定 GEMINI_API_KEY")
    sys.exit(1)

# 初始化核心
Logger.info("正在啟動 Gemini Agent v13 (Cinematic CLI)...")
memory_mgr = MemoryManager()
lut_engine = LUTEngine()
rag = KnowledgeBase()

try:
    all_luts = lut_engine.list_luts()
    if all_luts:
        rag.index_luts(all_luts)
except Exception as e:
    Logger.warn(f"索引建立警告: {e}")

planner = SmartPlanner(API_KEY, rag)


# 工具函式
def remember_user_preference(info: str):
    Logger.info(f"寫入記憶: {info}")
    return memory_mgr.add_preference(info)


def check_available_luts(keyword: str = ""):
    Logger.debug(f"查詢 LUT: {keyword}")
    all_names = list(lut_engine.lut_index.keys())
    if keyword:
        filtered = [n for n in all_names if keyword.lower() in n]
        return f"找到 {len(filtered)} 個：{', '.join(filtered[:20])}..."
    import random
    sample = random.sample(all_names, min(len(all_names), 20))
    return f"系統共有 {len(all_names)} 個濾鏡，例如：{', '.join(sample)}..."


def create_chat_session():
    genai.configure(api_key=API_KEY)
    tools = [execute_safe_command, remember_user_preference, check_available_luts]
    base_prompt = """
    你是一個強大的 AI 助理 (Gemini 3 Pro)。
    【安全守則】執行指令前請用 execute_safe_command。
    【能力】修圖、查詢濾鏡、記憶偏好。
    """
    dynamic_context = memory_mgr.get_system_prompt_addition()
    model = genai.GenerativeModel(
        model_name='gemini-3-pro-preview',
        tools=tools,
        system_instruction=base_prompt + dynamic_context
    )
    return model.start_chat(enable_automatic_function_calling=True)


# 介面邏輯
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


async def main():
    console.clear()
    console.print(Panel.fit("[bold cyan]🤖 Gemini Agent v13 (Film Simulation)[/]", border_style="cyan"))

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
                console.print("[bold cyan]🖼️ 進入視覺模式[/]")
                target_files = []
                if os.path.isdir(target_path):
                    target_files = select_files_from_directory(target_path)
                    if not target_files: continue
                else:
                    target_files = [target_path]

                count = len(target_files)
                style_req = get_input_safe("[green]🎨 請描述風格: [/]")
                if not style_req: continue

                try:
                    iterator = track(target_files, description="修圖進度") if count > 1 else target_files
                    for img_path in iterator:
                        plan = await asyncio.to_thread(planner.generate_plan, img_path, style_req)

                        if plan and plan.get('selected_lut'):
                            if count == 1:
                                # v13 顯示詳細參數 (含 Curve/Sharpness)
                                console.print(Panel(
                                    f"技術分析: {plan.get('technical_analysis', '無')}\n"
                                    f"調色策略: {plan.get('style_strategy', '無')}\n"
                                    f"LUT: {plan['selected_lut']} (強度 {plan.get('intensity', 1.0)})\n"
                                    f"色彩: 亮({plan.get('brightness')}) 溫({plan.get('temperature')}) 調({plan.get('tint')})\n"
                                    f"質感: 曲線({plan.get('curve', 'Linear')}) 銳利({plan.get('sharpness', 1.0)})",
                                    title="AI 決策面板"
                                ))

                            # v13 傳遞完整參數
                            final_img, msg = lut_engine.apply_lut(
                                img_path,
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

                            if final_img:
                                if not os.path.exists("output"): os.makedirs("output")
                                save_path = f"output/v13_{os.path.basename(img_path)}"
                                final_img.save(save_path)
                                Logger.success(f"已儲存: {save_path}")
                except KeyboardInterrupt:
                    Logger.warn("視覺任務已暫停")

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
                    Logger.warn("對話已取消")
                except Exception as e:
                    Logger.error(f"對話錯誤: {e}")

        except KeyboardInterrupt:
            console.print("\n[bold yellow]⚠️ (已攔截中斷訊號)[/]")
            continue
        except Exception as e:
            Logger.error(f"系統崩潰攔截: {e}")
            await asyncio.sleep(1)
            continue


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程式結束。")