"""
app/memory/conversation_store.py —— 对话历史的本地 JSON 文件存储

【作用与功能】
提供对话历史的本地持久化能力：将每一轮或多轮对话以 JSON 文件形式落盘，支持按
对话 ID 保存、加载完整历史，以及按修改时间倒序列出所有对话的元信息。该模块与
 Redis 短期记忆互补，常用于会话级的全量备份或离线审计。

【主要组成】
- `ConversationStore`：对话存储管理器，封装 save / load / list_all 三类操作

【适用场景】
- 场景1：需要把整段对话持久化到磁盘以便后续复盘或继续对话时调用 save/load
- 场景2：在管理后台展示「历史会话列表」时调用 list_all 获取元信息

【依赖关系】
- 上游调用方：app.memory.memory_manager 或其他需要会话落盘的业务代码
- 下游依赖：仅依赖标准库（json / os / uuid / pathlib），无外部服务依赖
"""

import json, os, uuid
from datetime import datetime
from pathlib import Path

class ConversationStore:
    """
    对话历史存储管理器。
    
    提供对话的持久化存储功能：
    - 保存对话消息（自动生成唯一ID或使用指定ID）
    - 加载指定对话的完整历史
    - 列出所有对话的元信息
    
    特点：
    1. 使用 JSON 格式存储对话数据
    2. 自动生成短 UUID 作为对话 ID
    3. 只保存最近 20 条消息以控制存储大小
    4. 按修改时间倒序列出对话
    """
    
    def __init__(self, store_dir="conversations"):
        """
        初始化对话存储器。
        
        参数：
            store_dir (str): 对话数据存储目录的路径，默认为 "conversations"。
                           如果目录不存在会自动创建。
        """
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(exist_ok=True)  # 确保存储目录存在

    def save(self, messages, conv_id=None):
        """
        保存对话消息到存储文件。
        
        如果未提供对话 ID，会自动生成一个短 UUID（8位）作为文件名。
        每次保存都会覆盖同名文件，并记录当前时间戳和消息数量。
        为控制存储大小，只保存最近 20 条消息。
        
        参数：
            messages (list): 对话消息列表，每个元素是包含角色和内容的字典。
            conv_id (str, optional): 对话的唯一标识符。如果未提供，自动生成。
            
        返回：
            str: 对话 ID（可能是自动生成的 UUID 或传入的 conv_id）。
        """
        # 如果未提供对话 ID，生成一个短 UUID
        if conv_id is None:
            conv_id = str(uuid.uuid4())[:8]
            
        # 构建存储文件路径
        path = self.store_dir / f"{conv_id}.json"
        
        # 准备要保存的数据结构
        data = {
            "id": conv_id,
            "timestamp": datetime.now().isoformat(),  # ISO 格式时间戳
            "message_count": len(messages),
            "messages": messages[-20:]  # 只保存最近 20 条消息
        }
        
        # 写入 JSON 文件
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        return conv_id

    def load(self, conv_id):
        """
        加载指定对话的完整历史数据。
        
        参数：
            conv_id (str): 对话的唯一标识符。
            
        返回：
            dict or None: 对话数据字典（包含 id、timestamp、message_count 和 messages），
                        如果对话不存在则返回 None。
        """
        # 构建存储文件路径
        path = self.store_dir / f"{conv_id}.json"
        
        # 如果文件存在则加载并返回，否则返回 None
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return None

    def list_all(self):
        """
        列出所有对话的元信息。
        
        按修改时间倒序返回所有对话的基本信息，不包含具体消息内容。
        
        返回：
            list: 对话元信息列表，每个元素是包含 id、timestamp 和 message_count 的字典。
        """
        result = []
        
        # 获取所有 JSON 文件，按修改时间倒序排序
        for f in sorted(self.store_dir.glob("*.json"), key=os.path.getmtime, reverse=True):
            # 加载并提取元信息
            data = json.load(open(f, encoding="utf-8"))
            result.append({
                "id": data["id"],
                "timestamp": data["timestamp"],
                "message_count": data["message_count"]
            })
            
        return result
