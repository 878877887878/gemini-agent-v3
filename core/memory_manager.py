import json
import os


class MemoryManager:
    def __init__(self, memory_file="core/user_memory.json"):
        self.memory_file = memory_file
        self.data = self._load_memory()

    def _load_memory(self):
        """載入記憶檔案，若不存在則建立預設值"""
        # 確保目錄存在
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
        """新增使用者偏好 (避免重複)"""
        if text not in self.data["user_preferences"]:
            self.data["user_preferences"].append(text)
            self.save_memory()
            return f"✅ 已寫入記憶庫: {text}"
        return "⚠️ 此偏好已存在記憶中"

    def get_system_prompt_addition(self):
        """產生注入到 System Prompt 的文字"""
        if not self.data["user_preferences"]:
            return ""

        context = "\n\n【 🧠 長期記憶與使用者偏好 】\n請務必遵守以下已學習到的規則：\n"
        for i, pref in enumerate(self.data["user_preferences"], 1):
            context += f"{i}. {pref}\n"

        return context