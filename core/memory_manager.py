import json
import os
from core.logger import Logger


class MemoryManager:
    def __init__(self, memory_file="core/user_memory.json"):
        self.memory_file = memory_file
        self.data = self._load_memory()

    def _load_memory(self):
        """載入記憶檔案，若不存在則建立預設值"""
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {"user_preferences": []}
        return {"user_preferences": []}

    def save_memory(self):
        """儲存記憶到硬碟"""
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def add_preference(self, text):
        """新增使用者偏好"""
        if text not in self.data["user_preferences"]:
            self.data["user_preferences"].append(text)
            self.save_memory()
            Logger.info(f"已寫入記憶: {text}")
            return f"✅ 已寫入記憶庫: {text}"
        return "⚠️ 此偏好已存在記憶中"

    def get_system_prompt_addition(self):
        """
        v15 改進：讓記憶變成「背景知識」而非「絕對指令」
        """
        if not self.data["user_preferences"]:
            return ""

        context = "\n\n【 🧠 長期記憶庫 (User Context) 】\n"
        context += "以下是使用者過去的偏好，供你參考了解使用者的品味：\n"
        for i, pref in enumerate(self.data["user_preferences"], 1):
            context += f"- {pref}\n"

        context += "\n【 ⚠️ 重要決策邏輯 (Priority Rule) 】\n"
        context += "1. **當前優先**: 如果使用者這次的指令 (如 '聖誕風格', '暖色調') 與長期記憶 (如 '日系冷白') 衝突，請**務必優先執行當前指令**。\n"
        context += "2. **預設回退**: 只有當使用者沒有指定風格 (說 '隨便', '老樣子') 時，才使用長期記憶中的偏好。\n"

        return context