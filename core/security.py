import subprocess
from rich.console import Console

console = Console()

# ✅ 白名單：只允許這些指令開頭 (您可以自行擴充)
ALLOWED_COMMANDS = [
    "git",      # git status, commit, push...
    "dir", "ls", # 檔案列表
    "echo",     # 測試用
    "type", "cat", # 查看檔案內容
    "whoami", "ver", "cd", "mkdir"
]

# 🚫 黑名單：目前依要求留空 (原本建議擋 del, rm 等)
BANNED_KEYWORDS = []

def execute_safe_command(command: str):
    """
    安全版本的指令執行工具。
    """
    cmd_lower = command.lower().strip()
    
    # 1. 檢查白名單
    is_allowed = any(cmd_lower.startswith(allowed) for allowed in ALLOWED_COMMANDS)
    if not is_allowed:
        return f"🚫 安全攔截：指令 '{command}' 不在允許清單中。僅支援: {', '.join(ALLOWED_COMMANDS)}"

    # 2. 檢查黑名單 (目前為空，不會觸發)
    if BANNED_KEYWORDS and any(banned in cmd_lower for banned in BANNED_KEYWORDS):
        return f"🚫 安全攔截：指令包含危險關鍵字。"

    # 3. 執行
    try:
        console.print(f"[dim]🛡️ 執行安全指令: {command}[/]")
        # timeout=30 防止指令卡死
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=30 
        )
        if result.returncode == 0:
            # 限制輸出長度以免塞爆 Context
            return f"✅ 執行成功:\n{result.stdout[:2000]}" 
        else:
            return f"❌ 執行失敗:\n{result.stderr[:2000]}"
    except subprocess.TimeoutExpired:
        return "⚠️ 執行逾時 (超過 30 秒)"
    except Exception as e:
        return f"⚠️ 系統錯誤: {str(e)}"