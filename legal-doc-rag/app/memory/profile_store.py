"""
app/memory/profile_store.py —— 多租户用户画像实体存储

【作用与功能】
管理结构化的用户画像信息（如姓名、偏好、关键属性等），与 ChromaDB 的非结构化
长期记忆相分离。数据以 JSON 文件持久化，支持多租户隔离、线程安全读写、基于置信度
的实体合并，并可将画像序列化为提示词文本注入 LLM 上下文。

【主要组成】
- `ProfileStore`：用户画像存储类，提供 get_profile / to_prompt_text /
  merge_entities / clear 等方法

【适用场景】
- 场景1：在 MemorySystem 后台实体提取后，将抽取到的实体合并入画像
- 场景2：组装上下文时调用 to_prompt_text 把用户画像注入 LLM 提示词

【依赖关系】
- 上游调用方：app.memory.memory_manager（实体提取、上下文组装）
- 下游依赖：仅依赖标准库（json / os / threading）与 loguru
"""

import json, os, threading
from datetime import datetime
from loguru import logger

class ProfileStore:
    """
    用户画像实体存储类。
    
    与 ChromaDB 的长期记忆分离，专门用于存储结构化的用户实体信息（如姓名、偏好、关键属性等）。
    
    特点：
    1. 使用 JSON 文件持久化存储
    2. 支持多租户数据隔离
    3. 线程安全（使用 threading.Lock）
    4. 支持实体合并（基于置信度）
    5. 记录访问次数和时间戳
    
    数据结构：
    {
        "tenant_id_1": {
            "实体名1": {"value": "值1", "confidence": 0.9, "source": "llm", "timestamp": "...", "access_count": 1},
            "实体名2": {"value": "值2", "confidence": 0.8, "source": "llm", "timestamp": "...", "access_count": 2}
        },
        "tenant_id_2": {...}
    }
    """
    
    def __init__(self, path="./user_profiles.json"):
        """
        初始化用户画像存储。
        
        参数：
            path (str): 用户画像 JSON 文件的存储路径，默认为 "./user_profiles.json"。
        """
        self.path = path
        self._lock = threading.Lock()  # 线程锁，保证并发安全
        self._data = {}  # 内存中的数据缓存
        self._load()  # 启动时加载数据

    def _load(self):
        """
        从文件加载用户画像数据。
        
        如果文件不存在或加载失败，初始化为空字典。
        """
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    self._data = json.load(f)
            except Exception as e:
                logger.warning("Profile load failed: {}", e)
                self._data = {}

    def _save(self):
        """
        将内存中的数据保存到文件。
        
        保存失败时记录错误日志，但不中断程序运行。
        """
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Profile save failed: {}", e)

    def get_profile(self, tenant_id):
        """
        获取指定租户的完整用户画像。
        
        参数：
            tenant_id (str): 租户 ID。
            
        返回：
            dict: 该租户的用户画像字典。如果不存在则返回空字典。
        """
        with self._lock:
            return dict(self._data.get(tenant_id, {}))

    def to_prompt_text(self, tenant_id):
        """
        将用户画像转换为 LLM 提示词格式。
        
        将用户画像中的实体信息格式化为文本，便于注入到 LLM 的上下文中。
        
        参数：
            tenant_id (str): 租户 ID。
            
        返回：
            str: 格式化后的用户画像文本。如果画像为空则返回空字符串。
        """
        profile = self.get_profile(tenant_id)
        if not profile:
            return ""
        # 按键名排序，确保输出顺序稳定
        items = sorted(profile.items())
        # 格式化为 "键: 值" 的形式
        parts = [k + ": " + v["value"] for k, v in items]
        return "[User Profile]\n" + "\n".join(parts)

    def merge_entities(self, tenant_id, entities):
        """
        合并实体信息到用户画像中。
        
        合并策略：
        1. 如果实体已存在，仅当新置信度更高时才更新值
        2. 无论是否更新，都会增加访问计数
        3. 新实体会直接添加到画像中
        
        参数：
            tenant_id (str): 租户 ID。
            entities (list): 待合并的实体列表，每个元素是包含 key, value, confidence 的字典。
        """
        if not entities:
            return
            
        with self._lock:
            # 确保租户数据存在
            if tenant_id not in self._data:
                self._data[tenant_id] = {}
            profile = self._data[tenant_id]
            
            # 遍历并合并每个实体
            for ent in entities:
                # 提取并清理实体信息
                key = (ent.get("key") or "").strip()
                value = (ent.get("value") or "").strip()
                confidence = min(float(ent.get("confidence") or 0.5), 1.0)
                
                # 跳过无效实体
                if not key or not value:
                    continue
                    
                now = datetime.now().isoformat()
                
                # 处理已存在的实体
                if key in profile:
                    ex = profile[key]
                    # 只有当新置信度更高时才更新值
                    if confidence > (ex.get("confidence") or 0):
                        profile[key] = {
                            "value": value,
                            "confidence": confidence,
                            "source": "llm",
                            "timestamp": now,
                            "access_count": (ex.get("access_count") or 0) + 1,
                        }
                    else:
                        # 即使不更新值，也增加访问计数
                        profile[key]["access_count"] = profile[key].get("access_count", 0) + 1
                else:
                    # 添加新实体
                    profile[key] = {
                        "value": value,
                        "confidence": confidence,
                        "source": "llm",
                        "timestamp": now,
                        "access_count": 1,
                    }
            
            # 保存到文件
            self._save()

    def clear(self, tenant_id):
        """
        清除指定租户的用户画像。
        
        参数：
            tenant_id (str): 租户 ID。
        """
        with self._lock:
            self._data.pop(tenant_id, None)
            self._save()
