"""
多Agent协作框架

实现真正的多Agent协作，包括：
- Agent基类（自主决策、工具调用）
- Agent间通信（消息传递、事件驱动）
- 共享记忆（上下文共享、状态同步）
- 协调器（任务分配、冲突解决）
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
from enum import Enum
from loguru import logger
import uuid
import json


class AgentRole(str, Enum):
    """Agent角色"""
    ORCHESTRATOR = "orchestrator"  # 协调者
    PLANNER = "planner"           # 规划者
    SQL = "sql"                   # SQL专家
    ANALYSIS = "analysis"         # 分析专家
    REPORT = "report"             # 报告专家


class MessageType(str, Enum):
    """消息类型"""
    TASK = "task"           # 任务分配
    RESULT = "result"       # 结果返回
    QUERY = "query"         # 查询请求
    FEEDBACK = "feedback"   # 反馈建议
    ERROR = "error"         # 错误报告
    STATUS = "status"       # 状态更新


class Message:
    """Agent间消息"""
    
    def __init__(
        self,
        sender: str,
        receiver: str,
        msg_type: MessageType,
        content: Dict[str, Any],
        conversation_id: Optional[str] = None
    ):
        self.id = str(uuid.uuid4())[:8]
        self.sender = sender
        self.receiver = receiver
        self.msg_type = msg_type
        self.content = content
        self.conversation_id = conversation_id or str(uuid.uuid4())[:8]
        self.timestamp = datetime.now()
        self.requires_response = msg_type in [MessageType.TASK, MessageType.QUERY]
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "sender": self.sender,
            "receiver": self.receiver,
            "type": self.msg_type.value,
            "content": self.content,
            "conversation_id": self.conversation_id,
            "timestamp": self.timestamp.isoformat(),
            "requires_response": self.requires_response
        }


class SharedMemory:
    """共享记忆"""
    
    def __init__(self):
        self.context: Dict[str, Any] = {}
        self.history: List[Dict] = []
        self.max_history = 100
    
    def set(self, key: str, value: Any):
        """设置共享数据"""
        self.context[key] = value
        self._record("set", key, value)
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取共享数据"""
        return self.context.get(key, default)
    
    def update(self, data: Dict[str, Any]):
        """批量更新"""
        self.context.update(data)
        self._record("update", data)
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有共享数据"""
        return self.context.copy()
    
    def _record(self, action: str, *args):
        """记录操作历史"""
        self.history.append({
            "action": action,
            "args": args,
            "timestamp": datetime.now().isoformat()
        })
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]


class BaseAgent(ABC):
    """Agent基类"""
    
    def __init__(
        self,
        name: str,
        role: AgentRole,
        description: str,
        shared_memory: SharedMemory,
        message_queue: Optional[Callable] = None
    ):
        self.name = name
        self.role = role
        self.description = description
        self.shared_memory = shared_memory
        self.message_queue = message_queue
        self.state: Dict[str, Any] = {}
        self.tools: List[Dict] = []
        self.is_active = True
    
    @abstractmethod
    async def process(self, message: Message) -> Optional[Message]:
        """处理消息（子类实现）"""
        pass
    
    def send_message(
        self,
        receiver: str,
        msg_type: MessageType,
        content: Dict[str, Any],
        conversation_id: Optional[str] = None
    ) -> Message:
        """发送消息"""
        msg = Message(
            sender=self.name,
            receiver=receiver,
            msg_type=msg_type,
            content=content,
            conversation_id=conversation_id
        )
        
        if self.message_queue:
            self.message_queue(msg)
        
        logger.debug("[{}] 发送消息给 {}: {}", self.name, receiver, msg_type.value)
        return msg
    
    def log(self, message: str, level: str = "info"):
        """记录日志"""
        log_func = getattr(logger, level)
        log_func("[{}] {}", self.name, message)


class OrchestratorAgent(BaseAgent):
    """协调者Agent - 负责任务分配和协调"""
    
    def __init__(self, shared_memory: SharedMemory, message_queue: Callable):
        super().__init__(
            name="Orchestrator",
            role=AgentRole.ORCHESTRATOR,
            description="协调者，负责任务分解、分配和结果整合",
            shared_memory=shared_memory,
            message_queue=message_queue
        )
        self.agents: Dict[str, BaseAgent] = {}
        self.task_results: Dict[str, Any] = {}
    
    def register_agent(self, agent: BaseAgent):
        """注册Agent"""
        self.agents[agent.name] = agent
        self.log(f"注册Agent: {agent.name} ({agent.role.value})")
    
    async def process(self, message: Message) -> Optional[Message]:
        """处理任务"""
        self.log(f"收到任务: {message.content.get('question', '')[:50]}...")
        
        # 1. 分析任务，制定计划
        plan = await self._create_plan(message)
        self.shared_memory.set("current_plan", plan)
        
        # 2. 按顺序执行各Agent
        results = {}
        for step in plan["steps"]:
            agent_name = step["agent"]
            if agent_name not in self.agents:
                self.log(f"Agent不存在: {agent_name}", "warning")
                continue
            
            agent = self.agents[agent_name]
            
            # 发送任务给Agent
            task_msg = self.send_message(
                receiver=agent_name,
                msg_type=MessageType.TASK,
                content={
                    "task": step["task"],
                    "context": self.shared_memory.get_all(),
                    "depends_on": step.get("depends_on", [])
                },
                conversation_id=message.conversation_id
            )
            
            # 等待Agent处理并返回结果
            result = await agent.process(task_msg)
            if result:
                results[agent_name] = result.content
                self.shared_memory.set(f"result_{agent_name}", result.content)
                self.task_results[agent_name] = result.content
        
        # 3. 整合结果
        final_result = self._integrate_results(results)
        self.shared_memory.set("final_result", final_result)
        
        # 4. 返回最终结果
        return Message(
            sender=self.name,
            receiver="user",
            msg_type=MessageType.RESULT,
            content=final_result,
            conversation_id=message.conversation_id
        )
    
    async def _create_plan(self, message: Message) -> Dict:
        """创建执行计划"""
        question = message.content.get("question", "")
        
        # 根据问题类型制定计划
        plan = {
            "question": question,
            "steps": [
                {
                    "agent": "SQLAgent",
                    "task": f"为以下问题生成SQL: {question}",
                    "depends_on": []
                },
                {
                    "agent": "AnalysisAgent",
                    "task": "分析SQL查询结果，生成业务洞察",
                    "depends_on": ["SQLAgent"]
                },
                {
                    "agent": "ReportAgent",
                    "task": "生成运营建议和报告",
                    "depends_on": ["AnalysisAgent"]
                }
            ]
        }
        
        self.log(f"创建计划: {len(plan['steps'])} 个步骤")
        return plan
    
    def _integrate_results(self, results: Dict[str, Any]) -> Dict:
        """整合各Agent结果"""
        return {
            "question": self.shared_memory.get("current_plan", {}).get("question", ""),
            "sql": results.get("SQLAgent", {}).get("sql", ""),
            "explanation": results.get("SQLAgent", {}).get("explanation", ""),
            "data": results.get("SQLAgent", {}).get("data", []),
            "analysis": results.get("AnalysisAgent", {}).get("analysis", ""),
            "insights": results.get("AnalysisAgent", {}).get("insights", []),
            "recommendations": results.get("ReportAgent", {}).get("recommendations", []),
            "summary": results.get("ReportAgent", {}).get("summary", ""),
            "execution_trace": list(results.keys())
        }