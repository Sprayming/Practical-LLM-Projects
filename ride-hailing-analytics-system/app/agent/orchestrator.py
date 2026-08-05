"""
多Agent协作调度器

实现真正的多Agent协作：
- 注册多个专业Agent
- 通过消息传递协调
- 共享记忆同步状态
- 自主决策和反馈
"""

import asyncio
from typing import Dict, Any, Optional, Callable
from loguru import logger
from datetime import datetime

from app.agent.base import (
    OrchestratorAgent, SharedMemory, Message, MessageType
)
from app.agent.agents import SQLAgent, AnalysisAgent, ReportAgent


class MultiAgentOrchestrator:
    """多Agent协作调度器"""
    
    def __init__(self):
        # 创建共享记忆
        self.shared_memory = SharedMemory()
        
        # 消息队列（用于Agent间通信）
        self.message_log = []
        
        # 创建协调者
        self.orchestrator = OrchestratorAgent(
            shared_memory=self.shared_memory,
            message_queue=self._handle_message
        )
        
        # 创建专业Agent
        self.sql_agent = SQLAgent(shared_memory=self.shared_memory)
        self.analysis_agent = AnalysisAgent(shared_memory=self.shared_memory)
        self.report_agent = ReportAgent(shared_memory=self.shared_memory)
        
        # 注册Agent到协调者
        self.orchestrator.register_agent(self.sql_agent)
        self.orchestrator.register_agent(self.analysis_agent)
        self.orchestrator.register_agent(self.report_agent)
        
        logger.info("多Agent系统初始化完成: {}", [
            self.sql_agent.name,
            self.analysis_agent.name,
            self.report_agent.name
        ])
    
    def _handle_message(self, message: Message):
        """处理Agent间消息"""
        self.message_log.append({
            "id": message.id,
            "sender": message.sender,
            "receiver": message.receiver,
            "type": message.msg_type.value,
            "timestamp": message.timestamp.isoformat()
        })
        
        logger.debug(
            "消息传递: {} -> {} ({})",
            message.sender,
            message.receiver,
            message.msg_type.value
        )
    
    async def process(self, question: str) -> Dict[str, Any]:
        """处理用户问题"""
        logger.info("收到问题: {}", question[:100])
        
        # 创建用户消息
        user_message = Message(
            sender="user",
            receiver="Orchestrator",
            msg_type=MessageType.TASK,
            content={"question": question}
        )
        
        # 协调者处理
        result = await self.orchestrator.process(user_message)
        
        # 构建最终结果
        final_result = {
            "question": question,
            "result": result.content if result else {},
            "agent_trace": self._get_agent_trace(),
            "shared_context": self.shared_memory.get_all(),
            "execution_time": datetime.now().isoformat(),
            "agents_used": [
                self.sql_agent.name,
                self.analysis_agent.name,
                self.report_agent.name
            ]
        }
        
        return final_result
    
    def _get_agent_trace(self) -> Dict[str, Any]:
        """获取Agent执行轨迹"""
        return {
            "message_count": len(self.message_log),
            "messages": self.message_log[-10:],  # 最近10条消息
            "shared_memory_keys": list(self.shared_memory.context.keys())
        }
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        return {
            "agents": {
                "Orchestrator": {
                    "role": self.orchestrator.role.value,
                    "status": "active" if self.orchestrator.is_active else "inactive",
                    "registered_agents": list(self.orchestrator.agents.keys())
                },
                "SQLAgent": {
                    "role": self.sql_agent.role.value,
                    "status": "active" if self.sql_agent.is_active else "inactive",
                    "tools": [t["name"] for t in self.sql_agent.tools]
                },
                "AnalysisAgent": {
                    "role": self.analysis_agent.role.value,
                    "status": "active" if self.analysis_agent.is_active else "inactive",
                    "tools": [t["name"] for t in self.analysis_agent.tools]
                },
                "ReportAgent": {
                    "role": self.report_agent.role.value,
                    "status": "active" if self.report_agent.is_active else "inactive",
                    "tools": [t["name"] for t in self.report_agent.tools]
                }
            },
            "shared_memory_size": len(self.shared_memory.context),
            "message_log_size": len(self.message_log)
        }


# 全局实例（兼容旧接口）
multi_agent_orchestrator = MultiAgentOrchestrator()


# 兼容旧接口的函数
def run_agent(question: str) -> Dict[str, Any]:
    """运行Agent（同步包装）"""
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(multi_agent_orchestrator.process(question))
        return result
    finally:
        loop.close()


async def run_agent_async(question: str) -> Dict[str, Any]:
    """运行Agent（异步）"""
    return await multi_agent_orchestrator.process(question)
