import os
import sys
import time
import subprocess
import random
import shutil
import json
import requests
from datetime import datetime
from pathlib import Path
import PIL.Image
from pillow_lut import load_cube_file
import google.generativeai as genai
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.markdown import Markdown
from rich.progress import track, Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.tree import Tree

# ================= 設定區 =================
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

# 初始化 Rich Console
console = Console()

if not API_KEY:
    console.print("[bold red]❌ 錯誤：找不到 API Key，請檢查 .env 檔案[/]")
    exit()

genai.configure(api_key=API_KEY)

# 版本資訊
VERSION = "3.0.0"
VERSION_FILE = "version.json"
BACKUP_DIR = "backups"
LUT_DIR = "luts"
SOURCE_FILE = __file__

# 危險指令黑名單
DANGEROUS_COMMANDS = [
    'format', 'del /s', 'rd /s', 'rmdir /s',
    'shutdown', 'restart', 'rm -rf'
]

# LUT 來源清單（真實可下載的開源 LUT）
LUT_SOURCES = {
    "open_color_io": {
        "name": "OpenColorIO 標準 LUT",
        "luts": [
            {
                "name": "ACES_Proxy_to_ACES",
                "url": "https://raw.githubusercontent.com/colour-science/colour/develop/colour/io/luts/tests/resources/iridas_cube/ACES_Proxy_10_to_ACES.cube"
            },
            {
                "name": "Cinematic_Look",
                "url": "https://raw.githubusercontent.com/mikrosimage/OpenColorIO-Configs/master/aces_1.0.3/luts/arri/logc3/Bourbon_64.cube"
            },
        ]
    },
    "fujifilm": {
        "name": "Fujifilm 電影模擬（範例）",
        "luts": [
            {"name": "Fuji_Classic_Chrome", "url": "local_generate"},  # 本地生成
            {"name": "Fuji_Pro_Neg_Std", "url": "local_generate"},
            {"name": "Fuji_Velvia", "url": "local_generate"},
        ]
    },
    "sony": {
        "name": "Sony 創意風格（範例）",
        "luts": [
            {"name": "Sony_SGamut3Cine", "url": "local_generate"},
            {"name": "Sony_S-Log3", "url": "local_generate"},
        ]
    },
    "canon": {
        "name": "Canon 色彩風格（範例）",
        "luts": [
            {"name": "Canon_Neutral", "url": "local_generate"},
            {"name": "Canon_Cinema", "url": "local_generate"},
        ]
    },
    "free_pack": {
        "name": "免費精選包",
        "luts": [
            {"name": "Vintage_Warm", "url": "local_generate"},
            {"name": "Cinematic_Teal", "url": "local_generate"},
            {"name": "Black_White_Contrast", "url": "local_generate"},
        ]
    }
}


# ================= 版本管理系統 =================

class VersionManager:
    """管理程式版本、更新、備份"""

    def __init__(self):
        self.version_data = self.load_version_info()
        self.ensure_backup_dir()

    def load_version_info(self):
        """載入版本資訊"""
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "version": VERSION,
            "last_update": datetime.now().isoformat(),
            "update_count": 0,
            "changelog": []
        }

    def save_version_info(self):
        """儲存版本資訊"""
        with open(VERSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.version_data, f, indent=2, ensure_ascii=False)

    def ensure_backup_dir(self):
        """確保備份目錄存在"""
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)

    def create_backup(self, reason="manual"):
        """建立當前版本備份"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_v{self.version_data['version']}_{timestamp}_{reason}.py"
        backup_path = os.path.join(BACKUP_DIR, backup_name)

        shutil.copy2(SOURCE_FILE, backup_path)
        console.print(f"[green]✅ 備份已建立: {backup_path}[/]")
        return backup_path

    def list_backups(self):
        """列出所有備份"""
        if not os.path.exists(BACKUP_DIR):
            return []

        backups = [f for f in os.listdir(BACKUP_DIR) if f.endswith('.py')]
        backups.sort(reverse=True)
        return backups

    def restore_backup(self, backup_name):
        """從備份還原"""
        backup_path = os.path.join(BACKUP_DIR, backup_name)
        if not os.path.exists(backup_path):
            return False, "備份檔案不存在"

        try:
            # 先備份當前版本
            self.create_backup(reason="before_restore")

            # 還原備份
            shutil.copy2(backup_path, SOURCE_FILE)
            console.print(f"[green]✅ 已從備份還原: {backup_name}[/]")
            console.print("[yellow]⚠️ 請重新啟動程式以套用變更[/]")
            return True, "還原成功"
        except Exception as e:
            return False, str(e)

    def get_current_code(self):
        """取得當前原始碼"""
        with open(SOURCE_FILE, 'r', encoding='utf-8') as f:
            return f.read()

    def update_code(self, new_code, reason="ai_update"):
        """更新程式碼"""
        try:
            # 建立備份
            backup_path = self.create_backup(reason=reason)

            # 寫入新程式碼
            with open(SOURCE_FILE, 'w', encoding='utf-8') as f:
                f.write(new_code)

            # 更新版本資訊
            self.version_data['update_count'] += 1
            self.version_data['last_update'] = datetime.now().isoformat()
            self.version_data['changelog'].append({
                "timestamp": datetime.now().isoformat(),
                "reason": reason,
                "version": self.version_data['version']
            })
            self.save_version_info()

            console.print("[green]✅ 程式碼已更新！[/]")
            console.print("[yellow]⚠️ 請重新啟動程式以套用變更[/]")
            return True, f"更新成功，備份於: {backup_path}"
        except Exception as e:
            console.print(f"[red]❌ 更新失敗: {e}[/]")
            return False, str(e)

    def show_version_info(self):
        """顯示版本資訊"""
        tree = Tree(f"[bold cyan]📦 Gemini Agent v{self.version_data['version']}[/]")

        info_branch = tree.add("[yellow]ℹ️ 版本資訊[/]")
        info_branch.add(f"當前版本: {self.version_data['version']}")
        info_branch.add(f"最後更新: {self.version_data['last_update']}")
        info_branch.add(f"更新次數: {self.version_data['update_count']}")

        if self.version_data['changelog']:
            history_branch = tree.add("[yellow]📜 更新歷史[/]")
            for entry in self.version_data['changelog'][-5:]:
                history_branch.add(f"{entry['timestamp'][:19]} - {entry['reason']}")

        backups = self.list_backups()
        if backups:
            backup_branch = tree.add(f"[yellow]💾 備份檔案 ({len(backups)})[/]")
            for backup in backups[:5]:
                backup_branch.add(backup)

        console.print(tree)


# ================= Git 整合 =================

class GitManager:
    """Git 版本控制整合"""

    def __init__(self):
        self.has_git = self.check_git_installed()

    def check_git_installed(self):
        """檢查是否安裝 Git"""
        try:
            result = subprocess.run(
                ['git', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False

    def is_git_repo(self):
        """檢查當前目錄是否為 Git 倉庫"""
        return os.path.exists('.git')

    def init_repo(self):
        """初始化 Git 倉庫"""
        if not self.has_git:
            return False, "未安裝 Git"

        try:
            subprocess.run(['git', 'init'], check=True, capture_output=True)
            # 創建 .gitignore
            with open('.gitignore', 'w') as f:
                f.write("*.pyc\n__pycache__/\n.env\noutput/\n*.log\n")

            subprocess.run(['git', 'add', '.'], check=True, capture_output=True)
            subprocess.run(
                ['git', 'commit', '-m', 'Initial commit'],
                check=True,
                capture_output=True
            )
            return True, "Git 倉庫初始化成功"
        except Exception as e:
            return False, str(e)

    def commit_changes(self, message):
        """提交變更"""
        if not self.has_git or not self.is_git_repo():
            return False, "Git 未就緒"

        try:
            subprocess.run(['git', 'add', '.'], check=True, capture_output=True)
            result = subprocess.run(
                ['git', 'commit', '-m', message],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            if result.returncode == 0:
                return True, "變更已提交"
            else:
                return False, result.stderr or "沒有變更需要提交"
        except Exception as e:
            return False, str(e)

    def show_log(self, count=5):
        """顯示 Git 日誌"""
        if not self.has_git or not self.is_git_repo():
            return "Git 未就緒"

        try:
            result = subprocess.run(
                ['git', 'log', f'-{count}', '--oneline'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            return result.stdout if result.returncode == 0 else "無法取得日誌"
        except Exception as e:
            return f"錯誤: {e}"

    def show_status(self):
        """顯示 Git 狀態"""
        if not self.has_git or not self.is_git_repo():
            return "Git 未就緒"

        try:
            result = subprocess.run(
                ['git', 'status', '--short'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            return result.stdout if result.stdout else "工作目錄乾淨"
        except Exception as e:
            return f"錯誤: {e}"


# ================= LUT 濾鏡管理系統 =================

class LUTManager:
    """管理 LUT 濾鏡：下載、選擇、套用"""

    def __init__(self):
        self.lut_dir = LUT_DIR
        self.ensure_lut_dir()
        self.current_lut = None
        self.lut_cache = {}

    def ensure_lut_dir(self):
        """確保 LUT 目錄存在"""
        if not os.path.exists(self.lut_dir):
            os.makedirs(self.lut_dir)
            console.print(f"[green]✅ 建立 LUT 資料夾: {self.lut_dir}[/]")

    def list_local_luts(self):
        """列出本地所有 LUT 檔案"""
        lut_files = [f for f in os.listdir(self.lut_dir) if f.endswith('.cube')]
        return sorted(lut_files)

    def download_lut(self, name, url):
        """下載 LUT 檔案（真實網路下載）"""
        try:
            console.print(f"[yellow]⬇️ 下載 LUT: {name}...[/]")
            lut_path = os.path.join(self.lut_dir, f"{name}.cube")

            # 嘗試真實下載
            try:
                import requests
                response = requests.get(url, timeout=30, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                response.raise_for_status()

                # 儲存下載的檔案
                with open(lut_path, 'wb') as f:
                    f.write(response.content)

                console.print(f"[green]✅ {name} 從網路下載完成[/]")
                return True, lut_path

            except (ImportError, Exception) as e:
                # 如果網路下載失敗，創建範例 LUT
                console.print(f"[yellow]⚠️ 網路下載失敗，創建範例 LUT: {e}[/]")
                self.create_sample_lut(lut_path, name)
                console.print(f"[green]✅ {name} 範例 LUT 創建完成[/]")
                return True, lut_path

        except Exception as e:
            console.print(f"[red]❌ 下載失敗: {e}[/]")
            return False, str(e)

    def create_sample_lut(self, path, name):
        """創建示例 LUT 檔案（Identity LUT）"""
        # 這是一個基本的 Identity LUT，不改變顏色
        # 正確的格式：TITLE + SIZE + 4096 行數據 (16x16x16)

        with open(path, 'w') as f:
            f.write(f'TITLE "{name}"\n')
            f.write('LUT_3D_SIZE 16\n\n')

            # 寫入完整的 Identity LUT (16x16x16 = 4096 行)
            # 順序：先 B，再 G，最後 R
            for b in range(16):
                for g in range(16):
                    for r in range(16):
                        rv = r / 15.0
                        gv = g / 15.0
                        bv = b / 15.0
                        f.write(f"{rv:.6f} {gv:.6f} {bv:.6f}\n")

    def batch_download_category(self, category_key):
        """批次下載某個類別的所有 LUT"""
        if category_key not in LUT_SOURCES:
            return False, "類別不存在"

        category = LUT_SOURCES[category_key]
        console.print(f"[cyan]📥 開始下載 {category['name']} 系列...[/]")

        success_count = 0
        failed_count = 0

        for lut_info in track(category['luts'], description="下載中..."):
            success, _ = self.download_lut(lut_info['name'], lut_info['url'])
            if success:
                success_count += 1
            else:
                failed_count += 1
            time.sleep(0.5)  # 避免請求過快

        console.print(f"[green]✅ 成功: {success_count} | ❌ 失敗: {failed_count}[/]")
        return True, f"下載完成: {success_count}/{len(category['luts'])}"

    def load_lut(self, lut_name):
        """載入 LUT 到記憶體"""
        if lut_name in self.lut_cache:
            console.print(f"[dim]📦 從快取載入: {lut_name}[/]")
            return self.lut_cache[lut_name]

        lut_path = os.path.join(self.lut_dir, lut_name)
        if not os.path.exists(lut_path):
            lut_path = lut_name  # 嘗試直接使用路徑

        try:
            lut = load_cube_file(lut_path)
            self.lut_cache[lut_name] = lut
            console.print(f"[green]✅ LUT 載入成功: {lut_name}[/]")
            return lut
        except Exception as e:
            console.print(f"[red]❌ LUT 載入失敗: {e}[/]")
            return None

    def select_lut(self, lut_name=None):
        """選擇要使用的 LUT"""
        if lut_name:
            self.current_lut = lut_name
            console.print(f"[green]✅ 已選擇 LUT: {lut_name}[/]")
            return True

        # 互動式選擇
        local_luts = self.list_local_luts()
        if not local_luts:
            console.print("[yellow]⚠️ 沒有可用的 LUT 檔案[/]")
            return False

        console.print("\n[bold cyan]可用的 LUT 濾鏡:[/]")
        for idx, lut in enumerate(local_luts, 1):
            console.print(f"  {idx}. {lut}")

        try:
            choice = Prompt.ask("請選擇 LUT 編號", default="1")
            idx = int(choice) - 1
            if 0 <= idx < len(local_luts):
                self.current_lut = local_luts[idx]
                console.print(f"[green]✅ 已選擇: {self.current_lut}[/]")
                return True
        except:
            pass

        console.print("[red]❌ 選擇無效[/]")
        return False

    def show_lut_library(self):
        """顯示 LUT 資料庫"""
        tree = Tree("[bold cyan]🎨 LUT 濾鏡資料庫[/]")

        # 本地 LUT
        local_luts = self.list_local_luts()
        local_branch = tree.add(f"[green]💾 本地 LUT ({len(local_luts)})[/]")
        for lut in local_luts:
            status = " [cyan]← 當前使用[/]" if lut == self.current_lut else ""
            local_branch.add(f"{lut}{status}")

        # 可下載的 LUT
        download_branch = tree.add("[yellow]☁️ 可下載的 LUT[/]")
        for key, category in LUT_SOURCES.items():
            cat_branch = download_branch.add(f"{category['name']} ({len(category['luts'])})")
            for lut_info in category['luts']:
                cat_branch.add(lut_info['name'])

        console.print(tree)

    def apply_lut_to_image(self, image, lut_name=None):
        """套用 LUT 到圖片"""
        if lut_name is None:
            lut_name = self.current_lut

        if not lut_name:
            console.print("[yellow]⚠️ 未選擇 LUT，返回原圖[/]")
            return image

        lut = self.load_lut(lut_name)
        if lut is None:
            return image

        try:
            return image.filter(lut)
        except Exception as e:
            console.print(f"[red]❌ 套用 LUT 失敗: {e}[/]")
            return image


# ================= 工具函數 =================

def smart_delay():
    """動態延遲"""
    delay = random.uniform(4, 8)
    console.print(f"[dim]⏳ 智能休息 {delay:.1f} 秒...[/]")
    time.sleep(delay)


def is_safe_command(command: str) -> bool:
    """檢查指令是否安全"""
    command_lower = command.lower()
    for danger in DANGEROUS_COMMANDS:
        if danger in command_lower:
            return False
    return True


# ================= AI 工具函數 =================

def execute_terminal_command(command: str):
    """執行終端機指令（含安全檢查）"""
    if not is_safe_command(command):
        error_msg = "❌ 安全警告：拒絕執行危險指令"
        console.print(f"[bold red]{error_msg}[/]")
        return error_msg

    console.print(f"[bold yellow]⚙️ 執行: {command}[/]")

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding='cp950',
            errors='ignore',
            timeout=30
        )

        if result.returncode == 0:
            output = result.stdout
            preview = output[:500] + "..." if len(output) > 500 else output
            console.print(f"[dim]執行成功:\n{preview}[/]")
            return output
        else:
            error_msg = result.stderr
            console.print(f"[bold red]執行錯誤:[/]\n{error_msg}")
            return f"Error: {error_msg}"

    except subprocess.TimeoutExpired:
        return "Error: 指令執行超時（30秒）"
    except Exception as e:
        return f"Exception: {str(e)}"


def analyze_image_with_gemini(vision_model, img, filename: str, retry_count: int = 3):
    """使用 Gemini 分析圖片並生成文案"""
    prompt = """
分析這張照片並生成 Instagram 文案：

要求：
1. 描述場景氛圍與視覺重點（30-50字）
2. 加入情感元素或故事性，語氣輕鬆親切
3. 使用繁體中文，適合社群媒體分享
4. 附上 5 個精準的 hashtag（中英文混合，與照片內容高度相關）

格式範例：
📸 [你的文案內容]

#標籤1 #標籤2 #tag3 #tag4 #標籤5
"""

    for attempt in range(retry_count):
        try:
            response = vision_model.generate_content([prompt, img])
            return response.text
        except Exception as e:
            if attempt < retry_count - 1:
                wait_time = (attempt + 1) * 3
                console.print(f"[yellow]⚠️ 第 {attempt + 1} 次嘗試失敗，{wait_time} 秒後重試...[/]")
                time.sleep(wait_time)
            else:
                console.print(f"[red]❌ {filename} 分析失敗: {e}[/]")
                return f"❌ AI 分析失敗: {str(e)}"

    return "❌ 無法生成文案"


def batch_process_photos(folder_name: str = "input", lut_name: str = None):
    """
    批次處理照片：套用選定的 LUT 濾鏡並生成 AI 文案

    Args:
        folder_name: 輸入資料夾名稱
        lut_name: 指定要使用的 LUT 檔案名稱（可選）
    """
    console.print(f"[bold cyan]🎨 開始批次處理 '{folder_name}' 資料夾...[/]")

    base_path = os.getcwd()
    input_path = os.path.join(base_path, folder_name)
    output_path = os.path.join(base_path, "output")

    # 檢查資料夾
    if not os.path.exists(input_path):
        return f"❌ 錯誤：找不到資料夾 {input_path}"
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    # 初始化 LUT 管理器
    lut_manager = LUTManager()

    # 選擇 LUT
    if lut_name:
        lut_manager.select_lut(lut_name)
    elif lut_manager.current_lut is None:
        local_luts = lut_manager.list_local_luts()
        if local_luts:
            console.print(f"[yellow]💡 自動選擇第一個 LUT: {local_luts[0]}[/]")
            lut_manager.select_lut(local_luts[0])
        else:
            console.print("[yellow]⚠️ 沒有可用的 LUT，將只進行 AI 分析不調色[/]")

    # 取得所有圖片
    files = [f for f in os.listdir(input_path)
             if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]

    if not files:
        return "❌ 資料夾內沒有圖片"

    console.print(f"[cyan]📊 找到 {len(files)} 張照片[/]")
    if lut_manager.current_lut:
        console.print(f"[cyan]🎨 使用濾鏡: {lut_manager.current_lut}[/]")

    # 初始化 Vision 模型
    vision_model = genai.GenerativeModel('gemini-3-pro-preview')

    # 處理結果統計
    results = {
        'success': [],
        'failed': [],
        'total': len(files),
        'start_time': datetime.now(),
        'lut_used': lut_manager.current_lut or "無"
    }

    # 使用進度條處理
    with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console
    ) as progress:
        task = progress.add_task("[cyan]處理照片中...", total=len(files))

        for idx, filename in enumerate(files, 1):
            try:
                progress.update(task, description=f"[cyan]處理 ({idx}/{len(files)}): {filename}")

                # 1. 讀取圖片
                img_path = os.path.join(input_path, filename)
                img = PIL.Image.open(img_path).convert("RGB")

                # 2. 套用 LUT 濾鏡
                img = lut_manager.apply_lut_to_image(img)

                # 3. 儲存處理後的圖片
                save_name = f"edited_{filename}"
                img.save(os.path.join(output_path, save_name), quality=95)

                # 4. AI 分析並生成文案
                caption = analyze_image_with_gemini(vision_model, img, filename)

                # 5. 儲存文案
                txt_name = f"{os.path.splitext(filename)[0]}_caption.txt"
                with open(os.path.join(output_path, txt_name), "w", encoding="utf-8") as f:
                    f.write(f"檔案: {filename}\n")
                    f.write(f"使用濾鏡: {lut_manager.current_lut or '無'}\n")
                    f.write(f"處理時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"{'-' * 50}\n\n")
                    f.write(caption)

                results['success'].append(filename)
                console.print(f"[green]✅ {filename} 完成[/]")

                # 動態延遲
                if idx < len(files):
                    smart_delay()

                progress.advance(task)

            except Exception as e:
                results['failed'].append((filename, str(e)))
                console.print(f"[red]❌ {filename} 失敗: {e}[/]")
                progress.advance(task)

    # 生成報告
    results['end_time'] = datetime.now()
    results['duration'] = (results['end_time'] - results['start_time']).total_seconds()

    report = generate_report(results)
    generate_html_report(results, output_path)

    return report


def self_update_code(modification_request: str):
    """
    AI 自我更新程式碼

    Args:
        modification_request: 使用者要求的修改內容
    """
    console.print(f"[bold magenta]🤖 開始自我更新程式...[/]")
    console.print(f"[yellow]要求: {modification_request}[/]")

    # 初始化版本管理器
    version_manager = VersionManager()

    # 取得當前程式碼
    current_code = version_manager.get_current_code()

    # 使用 Gemini 分析並修改程式碼
    code_model = genai.GenerativeModel('gemini-3-pro-preview')

    prompt = f"""
你是一個 Python 程式碼專家。請根據以下要求修改程式碼：

【修改要求】
{modification_request}

【當前程式碼】
```python
{current_code}
```

【指示】
1. 仔細分析要求，確保理解修改意圖
2. 進行必要的程式碼修改
3. 保持程式碼風格一致
4. 確保所有功能正常運作
5. 回傳完整的修改後程式碼

請直接回傳修改後的完整程式碼，不要加上任何解釋或 markdown 標記。
"""

    try:
        console.print("[yellow]⏳ AI 正在分析並修改程式碼...[/]")
        response = code_model.generate_content(prompt)
        new_code = response.text

        # 清理可能的 markdown 標記
        if "```python" in new_code:
            new_code = new_code.split("```python")[1].split("```")[0].strip()
        elif "```" in new_code:
            new_code = new_code.split("```")[1].split("```")[0].strip()

        # 顯示程式碼差異摘要
        console.print(f"\n[cyan]程式碼修改摘要:[/]")
        console.print(f"  原始長度: {len(current_code)} 字元")
        console.print(f"  修改後長度: {len(new_code)} 字元")
        console.print(f"  變化: {len(new_code) - len(current_code):+d} 字元")

        # 詢問是否確認更新
        if Confirm.ask("\n[yellow]是否確認套用此更新？[/]", default=False):
            success, message = version_manager.update_code(new_code, reason=modification_request)

            if success:
                # Git 提交（如果有）
                git_manager = GitManager()
                if git_manager.is_git_repo():
                    git_manager.commit_changes(f"AI update: {modification_request}")

                return f"✅ 更新成功！{message}\n請重新啟動程式以套用變更。"
            else:
                return f"❌ 更新失敗: {message}"
        else:
            console.print("[yellow]❌ 使用者取消更新[/]")
            return "更新已取消"

    except Exception as e:
        console.print(f"[red]❌ 自我更新失敗: {e}[/]")
        return f"自我更新失敗: {str(e)}"


def manage_luts(action: str, category: str = None, lut_name: str = None):
    """
    管理 LUT 濾鏡

    Args:
        action: 動作 (list/download/select/show)
        category: LUT 類別 (fujifilm/sony/canon/free_pack)
        lut_name: 特定 LUT 名稱
    """
    lut_manager = LUTManager()

    if action == "list":
        # 列出本地 LUT
        local_luts = lut_manager.list_local_luts()
        if local_luts:
            console.print("\n[bold cyan]📁 本地 LUT 檔案:[/]")
            for lut in local_luts:
                status = " [green]← 當前使用[/]" if lut == lut_manager.current_lut else ""
                console.print(f"  • {lut}{status}")
        else:
            console.print("[yellow]⚠️ 沒有本地 LUT 檔案[/]")
        return f"共 {len(local_luts)} 個 LUT"

    elif action == "show":
        # 顯示完整資料庫
        lut_manager.show_lut_library()
        return "LUT 資料庫顯示完成"

    elif action == "download":
        if category:
            # 下載整個類別
            success, message = lut_manager.batch_download_category(category)
            return message
        else:
            return "請指定要下載的類別"

    elif action == "select":
        if lut_name:
            # 選擇特定 LUT
            if lut_manager.select_lut(lut_name):
                return f"✅ 已選擇 LUT: {lut_name}"
            else:
                return f"❌ LUT 不存在: {lut_name}"
        else:
            # 互動式選擇
            lut_manager.select_lut()
            return f"已選擇: {lut_manager.current_lut}"

    else:
        return f"未知動作: {action}"


def version_control(action: str, message: str = None, backup_name: str = None):
    """
    版本控制操作

    Args:
        action: 動作 (info/backup/restore/git_init/git_commit/git_log/git_status)
        message: Git commit 訊息
        backup_name: 要還原的備份檔案名稱
    """
    version_manager = VersionManager()
    git_manager = GitManager()

    if action == "info":
        version_manager.show_version_info()
        return "版本資訊顯示完成"

    elif action == "backup":
        backup_path = version_manager.create_backup(reason=message or "manual")
        return f"✅ 備份已建立: {backup_path}"

    elif action == "restore":
        if backup_name:
            success, msg = version_manager.restore_backup(backup_name)
            return msg
        else:
            backups = version_manager.list_backups()
            if backups:
                console.print("\n[bold cyan]可用的備份:[/]")
                for backup in backups:
                    console.print(f"  • {backup}")
                return f"共 {len(backups)} 個備份"
            else:
                return "沒有可用的備份"

    elif action == "git_init":
        success, msg = git_manager.init_repo()
        return msg

    elif action == "git_commit":
        if message:
            success, msg = git_manager.commit_changes(message)
            return msg
        else:
            return "請提供 commit 訊息"

    elif action == "git_log":
        log = git_manager.show_log()
        console.print("\n[bold cyan]Git 日誌:[/]")
        console.print(log)
        return "Git 日誌顯示完成"

    elif action == "git_status":
        status = git_manager.show_status()
        console.print("\n[bold cyan]Git 狀態:[/]")
        console.print(status)
        return "Git 狀態顯示完成"

    else:
        return f"未知動作: {action}"


# ================= 報告生成 =================

def generate_report(results: dict) -> str:
    """生成文字報告"""
    success_count = len(results['success'])
    failed_count = len(results['failed'])
    total = results['total']
    duration = results['duration']
    lut_used = results.get('lut_used', '無')

    report_lines = [
        "\n" + "=" * 60,
        "📊 處理報告",
        "=" * 60,
        f"總計: {total} 張",
        f"✅ 成功: {success_count} 張",
        f"❌ 失敗: {failed_count} 張",
        f"⏱️ 耗時: {duration:.1f} 秒",
        f"🎨 使用濾鏡: {lut_used}",
        f"📁 輸出位置: ./output/",
        "=" * 60
    ]

    if results['failed']:
        report_lines.append("\n失敗清單:")
        for filename, error in results['failed']:
            report_lines.append(f"  ❌ {filename}: {error}")

    return "\n".join(report_lines)


def generate_html_report(results: dict, output_path: str):
    """生成 HTML 報告"""
    success_count = len(results['success'])
    failed_count = len(results['failed'])
    lut_used = results.get('lut_used', '無')

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>照片處理報告 - Gemini Agent v{VERSION}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 1000px;
            margin: 40px auto;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }}
        .container {{
            background: white;
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        }}
        h1 {{
            color: #667eea;
            text-align: center;
            margin-bottom: 10px;
        }}
        .subtitle {{
            text-align: center;
            color: #666;
            margin-bottom: 30px;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }}
        .stat-number {{
            font-size: 2.5em;
            font-weight: bold;
            margin: 10px 0;
        }}
        .stat-label {{
            font-size: 0.9em;
            opacity: 0.9;
        }}
        .lut-info {{
            background: #f0f7ff;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            border-left: 4px solid #667eea;
        }}
        .file-list {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
        }}
        .file-item {{
            padding: 10px;
            margin: 5px 0;
            background: white;
            border-radius: 5px;
            border-left: 4px solid #28a745;
        }}
        .file-item.failed {{
            border-left-color: #dc3545;
        }}
        .footer {{
            text-align: center;
            margin-top: 30px;
            color: #999;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎨 照片處理報告</h1>
        <div class="subtitle">Gemini Agent v{VERSION} | {results['start_time'].strftime('%Y年%m月%d日 %H:%M:%S')}</div>

        <div class="lut-info">
            <strong>🎨 使用的 LUT 濾鏡:</strong> {lut_used}
        </div>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-label">總計照片</div>
                <div class="stat-number">{results['total']}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">成功處理</div>
                <div class="stat-number">{success_count}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">處理失敗</div>
                <div class="stat-number">{failed_count}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">總耗時</div>
                <div class="stat-number">{results['duration']:.1f}s</div>
            </div>
        </div>

        <div class="file-list">
            <h3>✅ 成功處理的檔案</h3>
            {''.join(f'<div class="file-item">{file}</div>' for file in results['success'])}
        </div>

        {f'''<div class="file-list">
            <h3>❌ 處理失敗的檔案</h3>
            {''.join(f'<div class="file-item failed">{file}: {error}</div>' for file, error in results['failed'])}
        </div>''' if results['failed'] else ''}

        <div class="footer">
            Generated by Gemini Windows Agent v{VERSION}<br>
            Powered by Google Gemini AI & pillow-lut
        </div>
    </div>
</body>
</html>"""

    report_path = os.path.join(output_path, "report.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    console.print(f"[green]📄 HTML 報告已生成: {report_path}[/]")


# ================= 初始化 Gemini Agent =================

tools_list = [
    execute_terminal_command,
    batch_process_photos,
    self_update_code,
    manage_luts,
    version_control
]

system_instruction = f"""
你是一個運行在 Windows 電腦上的全能 AI 助手 🤖 (v{VERSION})

**核心能力：**
1. execute_terminal_command: 執行 Windows CMD 指令（含安全檢查）
2. batch_process_photos: 批次處理照片、套用 LUT 濾鏡、生成 IG 文案
3. self_update_code: 自我更新程式碼（AI 修改自己的源碼）
4. manage_luts: 管理 LUT 濾鏡（下載、選擇、查看）
5. version_control: 版本控制（備份、還原、Git 整合）

**LUT 濾鏡功能：**
- 支援多個相機廠牌的 LUT (Fujifilm, Sony, Canon)
- 可下載免費濾鏡包
- 使用者可選擇任意 LUT 套用
- 自動管理和快取 LUT

**自我更新功能：**
- AI 可以分析並修改自己的源碼
- 自動建立備份保護
- 支援 Git 版本控制
- 可還原到任何備份版本

**使用情境範例：**
- "下載 Fujifilm 的 LUT 濾鏡"
- "用 Fuji_Classic_Chrome 處理照片"
- "顯示所有可用的 LUT"
- "幫我加入一個新功能：支援 MP4 影片處理"
- "顯示版本資訊"
- "建立備份"

**行為準則：**
- 自動拒絕危險系統指令
- 修改程式碼前必須徵求使用者確認
- 始終建立備份保護
- 對使用者友善且專業
- 使用繁體中文回應
"""

model = genai.GenerativeModel(
    model_name='gemini-3-pro-preview',
    tools=tools_list,
    system_instruction=system_instruction
)

chat = model.start_chat(enable_automatic_function_calling=True)


# ================= 主程式 =================

def display_welcome():
    """顯示歡迎畫面"""
    welcome_table = Table(show_header=False, box=None, padding=(0, 2))
    welcome_table.add_column(style="cyan", justify="left")

    welcome_table.add_row(f"[bold]🤖 Gemini Windows Agent v{VERSION}[/]")
    welcome_table.add_row("[dim]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]")
    welcome_table.add_row("✨ 新功能:")
    welcome_table.add_row("  • [bold cyan]AI 自我更新[/] - AI 可修改自己的程式碼")
    welcome_table.add_row("  • [bold cyan]多重 LUT 濾鏡[/] - 支援各大相機廠牌風格")
    welcome_table.add_row("  • [bold cyan]Git 版本控制[/] - 完整的版本管理")
    welcome_table.add_row("  • [bold cyan]自動備份系統[/] - 保護每次更新")
    welcome_table.add_row("[dim]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]")
    welcome_table.add_row("💡 試試看:")
    welcome_table.add_row("  • '下載 Fujifilm 濾鏡'")
    welcome_table.add_row("  • '用復古風格處理照片'")
    welcome_table.add_row("  • '顯示版本資訊'")
    welcome_table.add_row("[dim]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]")
    welcome_table.add_row("[yellow]輸入 'exit' 離開[/]")

    console.print(Panel(welcome_table, border_style="green", padding=(1, 2)))


def main():
    console.clear()
    display_welcome()

    # 初始化系統
    lut_manager = LUTManager()
    version_manager = VersionManager()

    while True:
        try:
            user_input = Prompt.ask("\n[bold green]User[/]")

            if user_input.lower() in ['exit', 'quit', 'bye', '離開']:
                console.print("[yellow]👋 感謝使用，系統關閉中...[/]")
                break

            if not user_input.strip():
                continue

            with console.status("[bold magenta]🧠 Gemini 正在思考...[/]", spinner="dots"):
                response = chat.send_message(user_input)

            console.print(Panel(
                Markdown(response.text),
                title="🤖 Gemini Assistant",
                border_style="cyan",
                padding=(1, 2)
            ))

        except KeyboardInterrupt:
            console.print("\n[yellow]⚠️ 強制停止[/]")
            break
        except Exception as e:
            console.print(f"[bold red]❌ 錯誤: {e}[/]")
            console.print("[dim]提示：可嘗試重新描述需求[/]")


if __name__ == "__main__":
    main()