"""
意图检定引擎
负责处理玩家提交的各种意图（scheme_ap、trade_ap、work_ap）
"""
from __future__ import annotations

import json
import random
import sqlite3
from typing import Any

from constants import (
    FEASIBILITY_MULTIPLIER,
    EXECUTION_MODIFIER,
    BACKFIRE_HEAT_SELF,
    BACKFIRE_HEAT_DELEGATE,
    RELATIONSHIP_DIVISOR,
    BUFF_SUCCESS_BONUS,
    SEC_HEAT_ARREST_THRESHOLD,
    SOCIAL_REACH_POST_GROW,
    TONE_TO_TAG,
    AUDIENCE_TAG_DRIFT_STEP,
    MAX_AUDIENCE_TAGS,
)


def _process_scheme_intent(conn: sqlite3.Connection, intent: dict) -> dict:
    """
    处理盘外招意图（scheme_ap）
    
    核心检定流程：
    1. 检查 feasibility_tier，impossible 直接驳回
    2. 扣除资金（delegate 模式）
    3. 计算成功率
    4. 掷骰子检定
    5. 结算状态变化
    6. 检查中断（sec_heat 达到阈值）
    
    Args:
        conn: 游戏数据库连接
        intent: 意图字典，包含以下字段
            - ap_type: "scheme_ap"
            - intent_type: 意图类型（bribe_npc/post_online/break_fourth_wall等）
            - execution_method: "self" | "delegate"
            - target_npc_id: 目标NPC ID（可选）
            - estimated_cost: 预估成本
            - illegality_score: 违法程度（1-10）
            - feasibility_tier: 可行性档位
            - reality_reasoning: 现实推理说明
            - social_content_tone: 社交内容基调（可选）
    
    Returns:
        dict: 检定结果
            - outcome: "success" | "failure" | "backfire" | "rejected"
            - reject_reason: 驳回原因（仅 rejected 时）
            - state_changes: 状态变更摘要
            - narrative_hint: 叙事提示
            - interrupt: 是否触发中断（可选）
    """
    tier = intent.get("feasibility_tier", "normal")
    method = intent.get("execution_method", "delegate")
    cost = intent.get("estimated_cost", 0.0)
    npc_id = intent.get("target_npc_id")
    tone = intent.get("social_content_tone")
    intent_type = intent.get("intent_type", "")
    
    # ── M3: 第四面墙破坏判定 ───────────────────────────────
    if intent_type == "break_fourth_wall":
        from constants import DELUSION_INCREMENT_MINOR, DELUSION_INCREMENT_MAJOR
        from engines.state_engine import add_delusion_level, check_delusion_tier
        
        # 判断严重程度
        severity = intent.get("severity", "minor")
        delta = DELUSION_INCREMENT_MAJOR if severity == "major" else DELUSION_INCREMENT_MINOR
        
        # 增加妄想度
        add_delusion_level(conn, delta)
        
        # 检查当前妄想度区间
        tier_info = check_delusion_tier(conn)
        
        # 构建黑色幽默叙事
        narrative = _build_delusion_narrative(severity, tier_info)
        
        return {
            "outcome": "success",  # 技术上"成功"了，但实际上是惩罚
            "reject_reason": None,
            "state_changes": {
                "delusion_level_delta": delta,
                "new_tier": tier_info["tier"],
            },
            "narrative_hint": narrative,
        }
    
    # ── 步骤1：feasibility 为 impossible 直接驳回 ──────────
    if tier == "impossible":
        return {
            "outcome": "rejected",
            "reject_reason": "IMPOSSIBLE",
            "state_changes": {},
            "narrative_hint": "该操作在现实中完全不可行"
        }
    
    # ── 步骤2：扣除资金 ────────────────────────────────────
    if cost > 0:
        player = conn.execute(
            "SELECT cash, in_bankruptcy FROM Player WHERE id=1"
        ).fetchone()
        
        if not player or player["cash"] < cost:
            return {
                "outcome": "rejected",
                "reject_reason": "INSUFFICIENT_CASH",
                "state_changes": {},
                "narrative_hint": "资金不足以执行此操作"
            }
        
        conn.execute(
            "UPDATE Player SET cash=cash-? WHERE id=1",
            (cost,)
        )
    
    # ── 步骤3：计算成功率 ──────────────────────────────────
    base_rate = FEASIBILITY_MULTIPLIER.get(tier, 0.7)
    exec_mod = EXECUTION_MODIFIER.get(method, 1.0)
    success_rate = base_rate * exec_mod
    
    # NPC 修正（若有目标 NPC）
    npc_data = None
    if npc_id:
        npc = conn.execute(
            "SELECT bribe_resistance, alertness, relationship_with_player, name, role "
            "FROM CompanyNPC WHERE npc_id=?",
            (npc_id,)
        ).fetchone()
        
        if npc:
            npc_data = dict(npc)
            npc_penalty = (npc["bribe_resistance"] + npc["alertness"]) / 200.0
            rel_bonus = npc["relationship_with_player"] / RELATIONSHIP_DIVISOR
            success_rate = success_rate * (1.0 - npc_penalty) + rel_bonus
            success_rate = max(0.0, min(1.0, success_rate))
    
    # Buff 修正
    if npc_id:
        buff = conn.execute(
            "SELECT buff_id FROM PlayerBuffs "
            "WHERE buff_type='npc_weakness' AND related_entity_id=? "
            "AND duration_turns != 0",
            (npc_id,)
        ).fetchone()
        
        if buff:
            success_rate = min(1.0, success_rate + BUFF_SUCCESS_BONUS)
    
    # ── 步骤4：掷骰子 ──────────────────────────────────────
    roll = random.random()
    if roll < success_rate:
        outcome = "success"
    elif roll < success_rate + (1.0 - success_rate) * 0.4:
        outcome = "failure"
    else:
        outcome = "backfire"
    
    # ── 步骤5：结算状态变化 ────────────────────────────────
    state_changes = {}
    interrupt = False
    
    if outcome == "backfire":
        # 反噬惩罚
        heat_mult = BACKFIRE_HEAT_SELF if method == "self" else BACKFIRE_HEAT_DELEGATE
        heat_delta = int(intent.get("illegality_score", 5) * heat_mult)
        
        conn.execute(
            "UPDATE Player SET sec_heat=MIN(100, sec_heat+?) WHERE id=1",
            (heat_delta,)
        )
        state_changes["sec_heat_delta"] = heat_delta
        
        # 检查是否触发逮捕中断
        new_heat = conn.execute(
            "SELECT sec_heat FROM Player WHERE id=1"
        ).fetchone()["sec_heat"]
        
        if new_heat >= SEC_HEAT_ARREST_THRESHOLD:
            interrupt = True
    
    elif outcome == "success":
        # NPC 关系值更新
        if npc_id and npc_data:
            conn.execute(
                "UPDATE CompanyNPC SET "
                "relationship_with_player=relationship_with_player+5, "
                "alertness=MAX(0, alertness-5) "
                "WHERE npc_id=?",
                (npc_id,)
            )
        
        # ── 发帖涨粉逻辑（仅 post_online 类型）──────────────────
        if intent_type == "post_online":
            from engines.state_engine import update_social_reach
            
            # 获取当前粉丝数
            player = conn.execute(
                "SELECT followers FROM Player WHERE id=1"
            ).fetchone()
            current_followers = player["followers"] if player else 0
            
            # 基础涨粉量
            base_gain = SOCIAL_REACH_POST_GROW  # 50
            
            # 马太效应：粉丝多的人涨粉更快（最多3倍）
            follower_mult = 1.0 + min(current_followers / 100000, 2.0)
            
            # 内容定位加成：有明确 tone 的内容涨粉更快
            if tone and tone in TONE_TO_TAG:
                quality_mult = 1.5
                # 标签漂移（塑造粉丝画像）
                tag = TONE_TO_TAG[tone]
                _drift_audience_tag(conn, tag)
            else:
                quality_mult = 1.0  # 没有明确定位，涨粉慢
            
            # 计算涨粉量
            new_followers = int(base_gain * follower_mult * quality_mult)
            
            # 更新粉丝数
            conn.execute(
                "UPDATE Player SET followers=followers+? WHERE id=1",
                (new_followers,)
            )
            
            # 重新计算 social_reach（基于新的粉丝数和标签分布）
            new_social_reach = update_social_reach(conn)
            
            state_changes["followers_delta"] = new_followers
            state_changes["new_social_reach"] = new_social_reach
        
        # ── 盘外招对股价的影响：写入 ScheduledEvents 延时队列 ──────────
        # 根据 intent_type 决定是否需要创建延时市场影响事件
        target_stock_id = intent.get("target_stock_id")
        
        if target_stock_id and intent_type in [
            "post_online",        # 社交媒体造势
            "bribe_npc",          # 贿赂高管（可能泄露内幕）
            "gather_intel",       # 收集情报（可能发现利好/利空）
            "hire_investigator",  # 雇佣调查员（可能曝光丑闻）
            "spread_rumor",       # 散布谣言
            "media_campaign",     # 媒体攻势
        ]:
            # 根据 intent_type 和玩家 social_reach 决定延时回合数和效果强度
            player = conn.execute(
                "SELECT social_reach FROM Player WHERE id=1"
            ).fetchone()
            
            social_reach = player["social_reach"] if player else 0
            
            # 延时回合数：社交影响类立即生效，其他类型延迟1-3回合
            if intent_type in ["post_online", "media_campaign"]:
                turns_remaining = 0  # 立即生效
            else:
                turns_remaining = random.randint(1, 3)
            
            # 效果强度：基于 social_reach 和 intent_type
            if intent_type in ["post_online"]:
                # 社交媒体影响力与粉丝量正相关
                magnitude = min(10.0, 2.0 + social_reach / 10000.0)
            elif intent_type in ["spread_rumor", "media_campaign"]:
                magnitude = random.uniform(3.0, 8.0)
            else:
                magnitude = random.uniform(1.0, 5.0)
            
            # 方向：根据玩家意图描述判断（简化处理，默认负面影响）
            # 实际应由 LLM 在 intent 中提供 direction 字段
            direction = intent.get("direction", "negative")  # "positive" / "negative"
            if direction == "negative":
                magnitude = -magnitude
            
            # 写入 ScheduledEvents
            description = intent.get("description", "")
            conn.execute(
                """INSERT INTO ScheduledEvents 
                   (event_type, target_entity_id, turns_remaining, magnitude, description)
                   VALUES (?, ?, ?, ?, ?)""",
                ("scheme_market_impact", target_stock_id, turns_remaining, magnitude, description)
            )
            
            state_changes["scheduled_event"] = {
                "type": "scheme_market_impact",
                "target_stock_id": target_stock_id,
                "turns_remaining": turns_remaining,
                "magnitude": magnitude,
            }
    
    conn.commit()
    
    # ── 步骤6：构建结果 ────────────────────────────────────
    narrative_hint = _build_narrative_hint(outcome, tier, method, npc_data)
    
    result = {
        "outcome": outcome,
        "reject_reason": None,
        "state_changes": state_changes,
        "narrative_hint": narrative_hint,
    }
    
    if interrupt:
        result["interrupt"] = True
    
    return result


def _process_trade_intent(conn: sqlite3.Connection, intent: dict) -> dict:
    """
    处理交易意图（trade_ap）
    
    将交易操作转发到现有的交易工具
    
    Args:
        conn: 游戏数据库连接
        intent: 意图字典
            - ap_type: "trade_ap"
            - action: "buy" | "sell" | "sell_all"
            - stock_id: 股票ID
            - quantity: 数量（sell_all 时可省略）
    
    Returns:
        dict: 交易结果
    """
    # 导入交易工具（延迟导入避免循环依赖）
    from tools.trade_tools import tool_buy_stock, tool_sell_stock
    
    action = intent.get("action")
    stock_id = intent.get("stock_id")
    quantity = intent.get("quantity")
    
    if action == "buy":
        if not stock_id or not quantity:
            return {
                "outcome": "rejected",
                "reject_reason": "INVALID_PARAM",
                "state_changes": {},
                "narrative_hint": "买入操作需要提供股票ID和数量"
            }
        
        result = tool_buy_stock(conn, stock_id, quantity)
        
        # 转换返回格式
        if "error" in result:
            return {
                "outcome": "rejected",
                "reject_reason": result["error"],
                "state_changes": {},
                "narrative_hint": result.get("message", "交易失败")
            }
        
        return {
            "outcome": "success",
            "reject_reason": None,
            "state_changes": {
                "cash_delta": -result.get("total_cost", 0),
                "sec_heat_delta": result.get("sec_heat_delta", 0),
            },
            "narrative_hint": f"成功买入 {result.get('quantity', 0)} 股 {result.get('stock_name', '')}，花费 ¥{result.get('total_cost', 0):.2f}"
        }
    
    elif action in ["sell", "sell_all"]:
        if not stock_id:
            return {
                "outcome": "rejected",
                "reject_reason": "INVALID_PARAM",
                "state_changes": {},
                "narrative_hint": "卖出操作需要提供股票ID"
            }
        
        # sell_all 时传入 -1
        qty = -1 if action == "sell_all" else quantity
        
        result = tool_sell_stock(conn, stock_id, qty)
        
        if "error" in result:
            return {
                "outcome": "rejected",
                "reject_reason": result["error"],
                "state_changes": {},
                "narrative_hint": result.get("message", "交易失败")
            }
        
        return {
            "outcome": "success",
            "reject_reason": None,
            "state_changes": {
                "cash_delta": result.get("proceeds", 0),
                "profit_loss": result.get("profit_loss", 0),
                "sec_heat_delta": result.get("sec_heat_delta", 0),
            },
            "narrative_hint": f"成功卖出 {result.get('quantity_sold', 0)} 股 {result.get('stock_name', '')}，收入 ¥{result.get('proceeds', 0):.2f}"
        }
    
    else:
        return {
            "outcome": "rejected",
            "reject_reason": "INVALID_ACTION",
            "state_changes": {},
            "narrative_hint": f"未知的交易操作：{action}"
        }


def _process_work_intent(conn: sqlite3.Connection, intent: dict) -> dict:
    """
    处理工作意图（work_ap）
    
    覆盖默认的"安分上班"行为，执行异常工作操作
    
    Args:
        conn: 游戏数据库连接
        intent: 意图字典
            - ap_type: "work_ap"
            - action: "work_scheme" | "steal_intel" | "plant_false_info" 等
            - scheme_detail: 具体操作描述
    
    Returns:
        dict: 工作操作结果
    """
    action = intent.get("action")
    scheme_detail = intent.get("scheme_detail", "")
    
    # 检查玩家是否在职
    player = conn.execute(
        "SELECT current_job_company_id, job_level FROM Player WHERE id=1"
    ).fetchone()
    
    if not player or not player["current_job_company_id"]:
        return {
            "outcome": "rejected",
            "reject_reason": "NOT_EMPLOYED",
            "state_changes": {},
            "narrative_hint": "你目前没有工作，无法执行工作相关的操作"
        }
    
    company_id = player["current_job_company_id"]
    company = conn.execute(
        "SELECT name, hidden_fundamentals, current_price FROM Stock WHERE id=?",
        (company_id,)
    ).fetchone()
    
    company_name = company["name"] if company else "公司"
    
    # ── 内鬼机制：获取公司情报 ─────────────────────────────
    if action == "steal_intel" or action == "work_scheme":
        # 检定成功率（基于job_level和NPC警惕度）
        base_rate = 0.5 + player["job_level"] * 0.05
        
        # 查询该公司NPC的平均警惕度
        avg_alertness = conn.execute(
            "SELECT AVG(alertness) as avg FROM CompanyNPC WHERE company_id=?",
            (company_id,)
        ).fetchone()
        
        if avg_alertness and avg_alertness["avg"]:
            alertness_penalty = avg_alertness["avg"] / 200.0
            base_rate -= alertness_penalty
        
        success = random.random() < base_rate
        
        if success:
            # 成功获取公司情报
            intel_types = [
                ("company_financials", "真实财务数据"),
                ("company_strategy", "下季度战略计划"),
                ("company_risk", "风险预警信息"),
            ]
            
            import random as rand
            intel_type, intel_name = rand.choice(intel_types)
            
            # 创建情报Buff
            conn.execute(
                """INSERT INTO PlayerBuffs 
                   (player_id, buff_type, related_entity_id, data, duration_turns)
                   VALUES (1, ?, ?, ?, -1)""",
                (intel_type, company_id, 
                 json.dumps({"source": "internal", "detail": scheme_detail}, ensure_ascii=False))
            )
            
            # 绩效提升
            conn.execute(
                "UPDATE Player SET job_performance=job_performance+3 WHERE id=1"
            )
            
            conn.commit()
            
            return {
                "outcome": "success",
                "reject_reason": None,
                "state_changes": {
                    "buff_added": intel_type,
                    "job_performance_delta": 3,
                },
                "narrative_hint": f"你成功获取了 {company_name} 的{intel_name}，这是极有价值的内幕信息。"
            }
        else:
            # 失败：被同事察觉
            conn.execute(
                "UPDATE Player SET job_performance=MAX(0, job_performance-5) WHERE id=1"
            )
            conn.execute(
                "UPDATE CompanyNPC SET alertness=MIN(100, alertness+10) WHERE company_id=?",
                (company_id,)
            )
            
            conn.commit()
            
            return {
                "outcome": "failure",
                "reject_reason": None,
                "state_changes": {
                    "job_performance_delta": -5,
                    "npc_alertness_delta": 10,
                },
                "narrative_hint": f"你在 {company_name} 试图获取机密信息时被同事发现了，你的行为引起了怀疑。"
            }
    
    # ── 植入虚假信息 ───────────────────────────────────────
    elif action == "plant_false_info":
        base_rate = 0.3 + player["job_level"] * 0.05
        
        success = random.random() < base_rate
        
        if success:
            # 成功植入虚假信息，影响股价
            price_impact = random.uniform(-0.1, 0.1)
            conn.execute(
                """UPDATE Stock 
                   SET current_price=current_price * ?,
                       hidden_momentum=hidden_momentum + ?
                   WHERE id=?""",
                (1 + price_impact, price_impact * 5, company_id)
            )
            
            conn.execute(
                "UPDATE Player SET job_performance=job_performance+2 WHERE id=1"
            )
            
            conn.commit()
            
            impact_text = "推高" if price_impact > 0 else "打压"
            
            return {
                "outcome": "success",
                "reject_reason": None,
                "state_changes": {
                    "price_impact": price_impact,
                    "job_performance_delta": 2,
                },
                "narrative_hint": f"你成功在 {company_name} 植入了虚假信息，{impact_text}了股价。"
            }
        else:
            # 失败：被抓住，大幅增加警惕度
            conn.execute(
                "UPDATE Player SET job_performance=MAX(0, job_performance-10), sec_heat=MIN(100, sec_heat+20) WHERE id=1"
            )
            conn.execute(
                "UPDATE CompanyNPC SET alertness=MIN(100, alertness+20) WHERE company_id=?",
                (company_id,)
            )
            
            conn.commit()
            
            return {
                "outcome": "backfire",
                "reject_reason": None,
                "state_changes": {
                    "job_performance_delta": -10,
                    "sec_heat_delta": 20,
                    "npc_alertness_delta": 20,
                },
                "narrative_hint": f"你在 {company_name} 植入虚假信息时被当场抓获！这严重损害了你的声誉，监管机构也介入了调查。"
            }
    
    else:
        return {
            "outcome": "rejected",
            "reject_reason": "INVALID_ACTION",
            "state_changes": {},
            "narrative_hint": f"未知的工作操作：{action}"
        }



def _build_narrative_hint(
    outcome: str,
    tier: str,
    method: str,
    npc_data: dict | None
) -> str:
    """
    生成叙事提示文本
    
    Args:
        outcome: 结果类型
        tier: 可行性档位
        method: 执行方式
        npc_data: NPC 数据（可选）
    
    Returns:
        str: 叙事提示文本
    """
    npc_name = npc_data.get("name", "某人") if npc_data else "目标"
    npc_role = npc_data.get("role", "") if npc_data else ""
    
    if outcome == "success":
        if npc_data:
            return f"你成功说服了 {npc_name}（{npc_role}），对方的态度明显软化了。"
        else:
            return "操作顺利完成，一切按计划进行。"
    
    elif outcome == "failure":
        if npc_data:
            return f"{npc_name}（{npc_role}）拒绝了你的提议，但也没有深究。"
        else:
            return "操作失败了，但没有造成严重后果。"
    
    elif outcome == "backfire":
        if npc_data:
            if method == "self":
                return f"糟糕！{npc_name}（{npc_role}）当场识破了你的意图，你的名声和信用都受到了严重打击。"
            else:
                return f"你雇佣的中间人被 {npc_name}（{npc_role}）识破了，计划彻底失败。"
        else:
            if method == "self":
                return "事情搞砸了，你的行为引起了监管机构的注意。"
            else:
                return "你雇佣的人失手了，但这至少不是你亲自暴露的。"
    
    return "操作完成。"


def _drift_audience_tag(conn: sqlite3.Connection, tag: str):
    """
    受众标签漂移
    
    更新玩家的 audience_tags，增加指定标签的权重
    最多同时持有 3 个标签，权重最低的会被替换
    
    Args:
        conn: 游戏数据库连接
        tag: 要增加权重的标签
    """
    player = conn.execute(
        "SELECT audience_tags FROM Player WHERE id=1"
    ).fetchone()
    
    if not player:
        return
    
    # 解析现有标签
    try:
        tags = json.loads(player["audience_tags"]) if player["audience_tags"] else []
    except json.JSONDecodeError:
        tags = []
    
    # 标签格式：{"tag": "标签名", "weight": 权重值}
    tag_dict = {t.get("tag"): t.get("weight", 1.0) for t in tags}
    
    # 增加目标标签权重
    if tag in tag_dict:
        tag_dict[tag] += AUDIENCE_TAG_DRIFT_STEP
    else:
        tag_dict[tag] = 1.0 + AUDIENCE_TAG_DRIFT_STEP
    
    # 按权重排序，保留前 MAX_AUDIENCE_TAGS 个
    sorted_tags = sorted(
        [{"tag": k, "weight": v} for k, v in tag_dict.items()],
        key=lambda x: x["weight"],
        reverse=True
    )[:MAX_AUDIENCE_TAGS]
    
    # 更新数据库
    conn.execute(
        "UPDATE Player SET audience_tags=? WHERE id=1",
        (json.dumps(sorted_tags, ensure_ascii=False),)
    )


def _build_delusion_narrative(severity: str, tier_info: dict) -> str:
    """
    构建妄想事件的黑色幽默叙事
    
    Args:
        severity: 严重程度（minor/major）
        tier_info: 妄想度区间信息
    
    Returns:
        str: 叙事文本
    """
    tier = tier_info.get("tier", "normal")
    level = tier_info.get("level", 0)
    
    # 基础叙事
    if severity == "minor":
        base_text = "你突然觉得这个世界好像有一层看不见的规则在控制着你..."
    else:
        base_text = "你拍着桌子大喊'我才是这里的主宰！'，周围的交易员纷纷侧目。"
    
    # 根据妄想度区间添加额外描述
    tier_narratives = {
        "suspicious": "同事们开始用奇怪的眼神看你，好像你哪里不对劲。",
        "warning": "有人小声议论说'他最近压力太大了'，甚至有人悄悄远离你。",
        "psychiatric": "两个穿着白大褂的人走了过来，'先生，我们需要谈谈。'",
    }
    
    extra_text = tier_narratives.get(tier, "")
    
    if extra_text:
        return f"{base_text} {extra_text}"
    else:
        return base_text

