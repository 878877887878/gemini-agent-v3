import subprocess
from rich.console import Console
from core.logger import Logger

console = Console()

# ✅ 白名單
ALLOWED_COMMANDS = [
    "git", "dir", "ls", "echo", "type", "cat",
    "whoami", "ver", "cd", "mkdir", "ping"
]

BANNED_KEYWORDS = []


def execute_safe_command(command: str):
    """
    安全版本的指令執行工具 (v15 Fix: 解決 Windows 編碼錯誤)
    """
    cmd_lower = command.lower().strip()

    # 1. 檢查白名單
    is_allowed = any(cmd_lower.startswith(allowed) for allowed in ALLOWED_COMMANDS)
    if not is_allowed:
        return f"🚫 安全攔截：指令 '{command}' 不在允許清單中。"

    # 3. 執行
    try:
        Logger.debug(f"執行指令: {command}")

        # v15 關鍵修正：
        # 1. shell=True 在 Windows 會使用 cmd.exe，其編碼通常是 cp950 (Big5)
        # 2. 我們嘗試用 utf-8 解碼，若失敗則用 errors='replace' 忽略亂碼，防止 Crash
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',  # [Fix] 遇到無法解碼的字元用 ? 取代，不要報錯
            timeout=30
        )

        if result.returncode == 0:
            return f"✅ 執行成功:\n{result.stdout[:2000]}"
        else:
            return f"❌ 執行失敗:\n{result.stderr[:2000]}"

    except subprocess.TimeoutExpired:
        return "⚠️ 執行逾時 (超過 30 秒)"
    except Exception as e:
        Logger.error(f"指令執行錯誤: {e}")
        return f"⚠️ 系統錯誤: {str(e)}"