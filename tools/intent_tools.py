"""
意图检定工具
MCP工具入口，负责管理AP限制和中断机制
"""

import json
import sqlite3
from typing import Any

from engines.intent_engine import (
    _process_scheme_intent,
    _process_trade_intent,
    _process_work_intent,
)
from constants import SEC_HEAT_ARREST_THRESHOLD


def tool_evaluate_intents(
    conn: sqlite3.Connection,
    intents: list[dict]
) -> dict:
    """
    意图检定工具入口
    
    接收意图数组，依次执行检定，支持中断机制
    
    Args:
        conn: 游戏数据库连接
        intents: 意图数组，每项包含：
            - ap_type: "scheme_ap" | "trade_ap" | "work_ap"
            - 其他字段因类型而异（见 intent_engine.py）
    
    Returns:
        dict: 完整结果集
            {
                "results": [
                    {
                        "index": int,
                        "ap_type": str,
                        "outcome": "success" | "failure" | "backfire" | "rejected",
                        "reject_reason": str | None,
                        "state_changes": dict,
                        "narrative_hint": str
                    }
                ],
                "interrupted": bool,
                "interrupt_reason": str | None
            }
    """
    results = []
    interrupted = False
    interrupt_reason = None
    
    # AP 计数器：每种类型每回合最多使用 1 次
    ap_used = {
        "trade_ap": 0,
        "scheme_ap": 0,
        "work_ap": 0,
    }
    
    # 遍历意图数组
    for idx, intent in enumerate(intents):
        # 检查意图格式
        if not isinstance(intent, dict):
            results.append({
                "index": idx,
                "ap_type": "unknown",
                "outcome": "rejected",
                "reject_reason": "INVALID_INTENT_FORMAT",
                "state_changes": {},
                "narrative_hint": "意图格式错误"
            })
            continue
        
        ap_type = intent.get("ap_type")
        
        # 检查 AP 类型
        if not ap_type or ap_type not in ap_used:
            results.append({
                "index": idx,
                "ap_type": ap_type or "unknown",
                "outcome": "rejected",
                "reject_reason": "INVALID_AP_TYPE",
                "state_changes": {},
                "narrative_hint": f"未知的AP类型：{ap_type}"
            })
            continue
        
        # 检查 AP 是否已用尽
        if ap_used[ap_type] >= 1:
            results.append({
                "index": idx,
                "ap_type": ap_type,
                "outcome": "rejected",
                "reject_reason": "AP_EXHAUSTED",
                "state_changes": {},
                "narrative_hint": f"本回合的 {ap_type} 已用完"
            })
            continue
        
        # 根据 AP 类型分发处理
        try:
            if ap_type == "scheme_ap":
                result = _process_scheme_intent(conn, intent)
            elif ap_type == "trade_ap":
                result = _process_trade_intent(conn, intent)
            elif ap_type == "work_ap":
                result = _process_work_intent(conn, intent)
            else:
                result = {
                    "outcome": "rejected",
                    "reject_reason": "UNSUPPORTED_AP_TYPE",
                    "state_changes": {},
                    "narrative_hint": f"暂不支持的AP类型：{ap_type}"
                }
        except Exception as e:
            result = {
                "outcome": "rejected",
                "reject_reason": "INTERNAL_ERROR",
                "state_changes": {},
                "narrative_hint": f"处理意图时发生错误：{str(e)}"
            }
        
        # 记录结果
        result["index"] = idx
        result["ap_type"] = ap_type
        results.append(result)
        
        # 更新 AP 计数器（即使被 rejected 也计数）
        ap_used[ap_type] += 1
        
        # 检查中断标记
        if result.get("interrupt"):
            interrupted = True
            interrupt_reason = "SEC_HEAT_REACHED_ARREST_THRESHOLD"
            break
        
        # 如果 outcome 是 rejected，仍然继续处理后续意图
        # 只有 interrupt 标记才会中断
    
    return {
        "results": results,
        "interrupted": interrupted,
        "interrupt_reason": interrupt_reason,
    }


def format_evaluate_intents_response(result: dict) -> str:
    """
    格式化 evaluate_intents 工具的返回值为 JSON 字符串
    
    Args:
        result: tool_evaluate_intents 返回的字典
    
    Returns:
        str: JSON 格式的响应字符串
    """
    return json.dumps(result, ensure_ascii=False, indent=2)
