"""
专业Agent实现

包括：
- SQLAgent: 自主决策SQL生成和优化
- AnalysisAgent: 自主决策分析角度和方法
- ReportAgent: 自主决策报告结构和重点
"""

from typing import Optional, Dict, Any, List
from loguru import logger
from openai import OpenAI

from app.agent.base import BaseAgent, AgentRole, Message, MessageType, SharedMemory
from app.config import settings
from app.nlsql.schema_parser import describe_tables
from app.nlsql.sql_generator import generate_sql
from app.nlsql.sql_executor import run_sql


class SQLAgent(BaseAgent):
    """SQL专家Agent - 自主决策SQL生成和优化"""
    
    def __init__(self, shared_memory: SharedMemory):
        super().__init__(
            name="SQLAgent",
            role=AgentRole.SQL,
            description="SQL专家，负责理解业务问题、生成SQL查询、优化查询性能",
            shared_memory=shared_memory
        )
        self.tools = [
            {"name": "generate_sql", "description": "生成SQL查询"},
            {"name": "validate_sql", "description": "验证SQL安全性"},
            {"name": "optimize_sql", "description": "优化SQL性能"},
        ]
    
    async def process(self, message: Message) -> Optional[Message]:
        """处理SQL生成任务"""
        task = message.content.get("task", "")
        context = message.content.get("context", {})
        question = context.get("current_plan", {}).get("question", task)
        
        self.log(f"开始处理SQL任务: {question[:50]}...")
        
        try:
            # 1. 自主决策：分析问题，确定查询策略
            strategy = self._analyze_query_strategy(question)
            self.log(f"查询策略: {strategy['approach']}")
            
            # 2. 生成SQL
            sql, explanation = generate_sql(question)
            
            if not sql:
                return self._create_error_response(message, "无法生成SQL")
            
            # 3. 自主决策：是否需要优化
            if self._should_optimize(sql):
                sql = self._optimize_sql(sql)
                self.log("SQL已优化")
            
            # 4. 执行SQL
            rows, columns = run_sql(sql)
            
            # 5. 自主决策：是否需要采样
            if len(rows) > 100:
                original_count = len(rows)
                rows = rows[:100]
                self.log(f"结果采样: {original_count} -> {len(rows)} 条")
            
            result = {
                "sql": sql,
                "explanation": explanation,
                "data": rows,
                "columns": columns,
                "row_count": len(rows),
                "strategy": strategy,
                "optimized": strategy.get("needs_optimization", False)
            }
            
            self.shared_memory.set("sql_result", result)
            
            return Message(
                sender=self.name,
                receiver=message.sender,
                msg_type=MessageType.RESULT,
                content=result,
                conversation_id=message.conversation_id
            )
            
        except Exception as e:
            self.log(f"SQL处理失败: {e}", "error")
            return self._create_error_response(message, str(e))
    
    def _analyze_query_strategy(self, question: str) -> Dict:
        """自主分析查询策略"""
        question_lower = question.lower()
        
        strategy = {
            "approach": "direct",
            "needs_optimization": False,
            "expected_complexity": "simple"
        }
        
        # 自主决策：判断查询复杂度
        if any(kw in question_lower for kw in ["对比", "比较", "趋势", "变化"]):
            strategy["approach"] = "comparative"
            strategy["expected_complexity"] = "complex"
        
        if any(kw in question_lower for kw in ["最多", "最少", "排名", "top"]):
            strategy["approach"] = "ranking"
            strategy["needs_optimization"] = True
        
        if any(kw in question_lower for kw in ["平均", "总计", "汇总", "统计"]):
            strategy["approach"] = "aggregation"
        
        return strategy
    
    def _should_optimize(self, sql: str) -> bool:
        """自主决策是否需要优化"""
        # 简单规则：如果SQL很长或包含子查询，可能需要优化
        return len(sql) > 200 or "SELECT" in sql.upper().split("FROM")[0].count("SELECT") > 1
    
    def _optimize_sql(self, sql: str) -> str:
        """优化SQL"""
        # 基础优化：确保有LIMIT
        if "LIMIT" not in sql.upper():
            sql = sql.rstrip(";") + " LIMIT 1000;"
        return sql
    
    def _create_error_response(self, message: Message, error: str) -> Message:
        """创建错误响应"""
        return Message(
            sender=self.name,
            receiver=message.sender,
            msg_type=MessageType.ERROR,
            content={"error": error, "agent": self.name},
            conversation_id=message.conversation_id
        )


class AnalysisAgent(BaseAgent):
    """分析专家Agent - 自主决策分析角度和方法"""
    
    def __init__(self, shared_memory: SharedMemory):
        super().__init__(
            name="AnalysisAgent",
            role=AgentRole.ANALYSIS,
            description="分析专家，负责解读数据、发现模式、生成业务洞察",
            shared_memory=shared_memory
        )
        self.tools = [
            {"name": "interpret_data", "description": "解读数据含义"},
            {"name": "find_patterns", "description": "发现数据模式"},
            {"name": "detect_anomalies", "description": "检测异常数据"},
        ]
    
    async def process(self, message: Message) -> Optional[Message]:
        """处理分析任务"""
        task = message.content.get("task", "")
        context = message.content.get("context", {})
        
        # 获取SQL结果
        sql_result = self.shared_memory.get("sql_result", {})
        data = sql_result.get("data", [])
        question = context.get("current_plan", {}).get("question", "")
        
        self.log(f"开始分析数据: {len(data)} 条记录")
        
        try:
            # 1. 自主决策：选择分析方法
            analysis_method = self._select_analysis_method(question, data)
            self.log(f"分析方法: {analysis_method}")
            
            # 2. 执行分析
            analysis = await self._perform_analysis(data, question, analysis_method)
            
            # 3. 自主决策：是否需要深入分析
            if self._needs_deep_analysis(analysis):
                deep_insights = await self._deep_analysis(data, analysis)
                analysis["deep_insights"] = deep_insights
            
            # 4. 生成业务洞察
            insights = self._generate_insights(analysis, question)
            
            result = {
                "analysis": analysis.get("summary", ""),
                "details": analysis,
                "insights": insights,
                "method_used": analysis_method,
                "data_quality": self._assess_data_quality(data)
            }
            
            self.shared_memory.set("analysis_result", result)
            
            return Message(
                sender=self.name,
                receiver=message.sender,
                msg_type=MessageType.RESULT,
                content=result,
                conversation_id=message.conversation_id
            )
            
        except Exception as e:
            self.log(f"分析失败: {e}", "error")
            return Message(
                sender=self.name,
                receiver=message.sender,
                msg_type=MessageType.ERROR,
                content={"error": str(e), "agent": self.name},
                conversation_id=message.conversation_id
            )
    
    def _select_analysis_method(self, question: str, data: List[Dict]) -> str:
        """自主选择分析方法"""
        if not data:
            return "empty"
        
        question_lower = question.lower()
        
        # 自主决策：根据问题类型选择方法
        if any(kw in question_lower for kw in ["趋势", "变化", "对比"]):
            return "trend_analysis"
        elif any(kw in question_lower for kw in ["分布", "比例", "占比"]):
            return "distribution_analysis"
        elif any(kw in question_lower for kw in ["异常", "问题", "风险"]):
            return "anomaly_detection"
        elif any(kw in question_lower for kw in ["排名", "top", "最好", "最差"]):
            return "ranking_analysis"
        else:
            return "summary_analysis"
    
    async def _perform_analysis(
        self, data: List[Dict], question: str, method: str
    ) -> Dict:
        """执行分析"""
        analysis = {"method": method, "data_points": len(data)}
        
        if method == "empty":
            analysis["summary"] = "没有数据可供分析"
            return analysis
        
        # 基础统计分析
        if data and isinstance(data[0], dict):
            numeric_fields = [
                k for k, v in data[0].items() 
                if isinstance(v, (int, float))
            ]
            
            for field in numeric_fields:
                values = [d.get(field, 0) for d in data if d.get(field) is not None]
                if values:
                    analysis[f"{field}_stats"] = {
                        "mean": sum(values) / len(values),
                        "min": min(values),
                        "max": max(values),
                        "count": len(values)
                    }
        
        analysis["summary"] = f"基于{method}方法，分析了{len(data)}条数据"
        
        return analysis
    
    def _needs_deep_analysis(self, analysis: Dict) -> bool:
        """自主决策是否需要深入分析"""
        # 如果数据量大或有异常值，需要深入分析
        data_points = analysis.get("data_points", 0)
        return data_points > 50
    
    async def _deep_analysis(self, data: List[Dict], basic_analysis: Dict) -> Dict:
        """深入分析"""
        return {
            "correlation": "需要更多数据进行相关性分析",
            "trend": "数据呈现一定趋势",
            "anomalies": []
        }
    
    def _generate_insights(self, analysis: Dict, question: str) -> List[Dict]:
        """生成业务洞察"""
        insights = []
        
        # 基于分析结果生成洞察
        if analysis.get("data_points", 0) > 0:
            insights.append({
                "type": "data_summary",
                "content": f"共分析了 {analysis['data_points']} 条数据",
                "importance": "medium"
            })
        
        # 检查是否有统计数据
        for key, value in analysis.items():
            if isinstance(value, dict) and "mean" in value:
                insights.append({
                    "type": "statistical",
                    "content": f"{key} 平均值为 {value['mean']:.2f}",
                    "importance": "high"
                })
        
        return insights
    
    def _assess_data_quality(self, data: List[Dict]) -> Dict:
        """评估数据质量"""
        if not data:
            return {"quality": "no_data", "score": 0}
        
        total_fields = 0
        null_fields = 0
        
        for row in data:
            for key, value in row.items():
                total_fields += 1
                if value is None:
                    null_fields += 1
        
        completeness = (total_fields - null_fields) / total_fields if total_fields > 0 else 0
        
        return {
            "quality": "good" if completeness > 0.9 else "fair" if completeness > 0.7 else "poor",
            "score": round(completeness * 100, 1),
            "total_fields": total_fields,
            "null_fields": null_fields
        }


class ReportAgent(BaseAgent):
    """报告专家Agent - 自主决策报告结构和重点"""
    
    def __init__(self, shared_memory: SharedMemory):
        super().__init__(
            name="ReportAgent",
            role=AgentRole.REPORT,
            description="报告专家，负责整合分析结果、生成运营建议、输出结构化报告",
            shared_memory=shared_memory
        )
        self.tools = [
            {"name": "generate_recommendations", "description": "生成运营建议"},
            {"name": "format_report", "description": "格式化报告"},
            {"name": "prioritize_insights", "description": "洞察优先级排序"},
        ]
    
    async def process(self, message: Message) -> Optional[Message]:
        """处理报告生成任务"""
        task = message.content.get("task", "")
        context = message.content.get("context", {})
        
        # 获取之前的分析结果
        sql_result = self.shared_memory.get("sql_result", {})
        analysis_result = self.shared_memory.get("analysis_result", {})
        question = context.get("current_plan", {}).get("question", "")
        
        self.log("开始生成报告...")
        
        try:
            # 1. 自主决策：确定报告重点
            focus = self._determine_focus(question, sql_result, analysis_result)
            self.log(f"报告重点: {focus}")
            
            # 2. 生成运营建议
            recommendations = self._generate_recommendations(
                question, sql_result, analysis_result, focus
            )
            
            # 3. 自主决策：建议优先级排序
            prioritized = self._prioritize_recommendations(recommendations)
            
            # 4. 生成摘要
            summary = self._generate_summary(
                question, sql_result, analysis_result, prioritized
            )
            
            # 5. 格式化输出
            formatted = self._format_output(summary, prioritized, analysis_result)
            
            result = {
                "summary": summary,
                "recommendations": prioritized,
                "formatted_output": formatted,
                "focus_areas": focus,
                "confidence": self._calculate_confidence(analysis_result)
            }
            
            self.shared_memory.set("report_result", result)
            
            return Message(
                sender=self.name,
                receiver=message.sender,
                msg_type=MessageType.RESULT,
                content=result,
                conversation_id=message.conversation_id
            )
            
        except Exception as e:
            self.log(f"报告生成失败: {e}", "error")
            return Message(
                sender=self.name,
                receiver=message.sender,
                msg_type=MessageType.ERROR,
                content={"error": str(e), "agent": self.name},
                conversation_id=message.conversation_id
            )
    
    def _determine_focus(
        self, question: str, sql_result: Dict, analysis_result: Dict
    ) -> List[str]:
        """自主确定报告重点"""
        focus = []
        question_lower = question.lower()
        
        # 自主决策：根据问题和数据确定重点
        if any(kw in question_lower for kw in ["优惠", "券", "核销"]):
            focus.append("coupon_performance")
        
        if any(kw in question_lower for kw in ["司机", "运力"]):
            focus.append("driver_analysis")
        
        if any(kw in question_lower for kw in ["订单", "收入", "金额"]):
            focus.append("order_analysis")
        
        if analysis_result.get("insights"):
            for insight in analysis_result["insights"]:
                if insight.get("importance") == "high":
                    focus.append("key_insight")
                    break
        
        if not focus:
            focus.append("general_overview")
        
        return focus
    
    def _generate_recommendations(
        self,
        question: str,
        sql_result: Dict,
        analysis_result: Dict,
        focus: List[str]
    ) -> List[Dict]:
        """生成运营建议"""
        recommendations = []
        
        # 基于分析结果生成建议
        insights = analysis_result.get("insights", [])
        
        for insight in insights:
            if insight.get("type") == "statistical":
                recommendations.append({
                    "category": "data_driven",
                    "action": f"关注 {insight['content']}",
                    "priority": "high" if insight.get("importance") == "high" else "medium",
                    "basis": insight
                })
        
        # 基于焦点生成建议
        if "coupon_performance" in focus:
            recommendations.append({
                "category": "coupon",
                "action": "分析优惠券使用情况，优化发券策略",
                "priority": "high",
                "basis": "优惠券核销率分析"
            })
        
        if "driver_analysis" in focus:
            recommendations.append({
                "category": "driver",
                "action": "关注司机活跃度，制定激励措施",
                "priority": "medium",
                "basis": "司机行为分析"
            })
        
        # 通用建议
        if sql_result.get("row_count", 0) > 0:
            recommendations.append({
                "category": "general",
                "action": "数据已获取，建议深入分析具体维度",
                "priority": "low",
                "basis": "数据分析完成"
            })
        
        return recommendations
    
    def _prioritize_recommendations(self, recommendations: List[Dict]) -> List[Dict]:
        """自主决策：建议优先级排序"""
        priority_order = {"high": 0, "medium": 1, "low": 2}
        return sorted(
            recommendations,
            key=lambda x: priority_order.get(x.get("priority", "low"), 3)
        )
    
    def _generate_summary(
        self,
        question: str,
        sql_result: Dict,
        analysis_result: Dict,
        recommendations: List[Dict]
    ) -> str:
        """生成摘要"""
        data_count = sql_result.get("row_count", 0)
        insights_count = len(analysis_result.get("insights", []))
        recs_count = len(recommendations)
        
        summary = f"针对问题「{question}」，系统分析了 {data_count} 条数据，"
        summary += f"发现了 {insights_count} 个业务洞察，"
        summary += f"提出了 {recs_count} 条运营建议。"
        
        if recommendations:
            high_priority = [r for r in recommendations if r.get("priority") == "high"]
            if high_priority:
                summary += f"其中 {len(high_priority)} 条为高优先级建议，建议重点关注。"
        
        return summary
    
    def _format_output(
        self, summary: str, recommendations: List[Dict], analysis_result: Dict
    ) -> str:
        """格式化输出"""
        output = f"## 分析摘要\n\n{summary}\n\n"
        
        output += "## 运营建议\n\n"
        for i, rec in enumerate(recommendations, 1):
            priority_emoji = "🔴" if rec["priority"] == "high" else "🟡" if rec["priority"] == "medium" else "🟢"
            output += f"{i}. {priority_emoji} **{rec['category']}**: {rec['action']}\n"
        
        if analysis_result.get("insights"):
            output += "\n## 关键洞察\n\n"
            for insight in analysis_result["insights"][:3]:
                output += f"- {insight['content']}\n"
        
        return output
    
    def _calculate_confidence(self, analysis_result: Dict) -> float:
        """计算置信度"""
        # 基于数据质量和分析结果计算置信度
        data_quality = analysis_result.get("data_quality", {})
        quality_score = data_quality.get("score", 50)
        
        insights_count = len(analysis_result.get("insights", []))
        
        # 基础置信度
        confidence = 0.5
        
        # 数据质量加分
        confidence += (quality_score / 100) * 0.3
        
        # 洞察数量加分
        if insights_count > 0:
            confidence += min(insights_count * 0.05, 0.2)
        
        return round(min(confidence, 1.0), 2)