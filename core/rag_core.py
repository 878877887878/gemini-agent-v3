import os
import chromadb
from chromadb.utils import embedding_functions

class KnowledgeBase:
    def __init__(self, db_path="./chroma_db"):
        self.client = chromadb.PersistentClient(path=db_path)
        # 使用預設 Embedding 模型 (輕量級)
        self.ef = embedding_functions.DefaultEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name="lut_knowledge",
            embedding_function=self.ef
        )

    def index_luts(self, lut_files):
        """
        將 LUT 列表存入向量資料庫
        """
        current_count = self.collection.count()
        if current_count >= len(lut_files):
            return # 已經建立過就不重複建立

        print(f"⚡ 正在建立 LUT 向量知識庫 (共 {len(lut_files)} 個檔案)...")
        
        # 分批處理以避免記憶體溢出
        batch_size = 50
        for i in range(0, len(lut_files), batch_size):
            batch = lut_files[i:i+batch_size]
            ids = []
            docs = []
            metadatas = []
            
            for path in batch:
                filename = os.path.basename(path)
                # 簡單的特徵描述：將檔名中的符號轉為文字，增強語意搜尋
                # 例如: "FLog_to_ETERNA.cube" -> "FLog to ETERNA cube"
                description = filename.replace('_', ' ').replace('-', ' ').replace('.', ' ')
                
                # 避免 ID 重複
                unique_id = filename
                
                ids.append(unique_id)
                docs.append(description)
                metadatas.append({"filename": filename, "path": path})

            try:
                self.collection.upsert(documents=docs, metadatas=metadatas, ids=ids)
            except Exception as e:
                print(f"⚠️ 索引批次 {i} 失敗: {e}")

        print(f"✅ 索引完成")

    def search(self, query, n_results=5):
        """RAG 搜尋：找出跟 query 最相關的濾鏡"""
        # 確保資料庫不為空
        if self.collection.count() == 0:
            return []

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            candidates = []
            if results['metadatas'] and results['metadatas'][0]:
                for meta in results['metadatas'][0]:
                    candidates.append(meta['filename'])
            return candidates
        except Exception:
            return []