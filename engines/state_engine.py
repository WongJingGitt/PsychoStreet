"""
状态与惩罚引擎
负责监管热度、坐牢、破产、Buff管理、社交影响力计算等
"""
from __future__ import annotations

import json
import random
import sqlite3
from typing import Any

from constants import (
    SEC_HEAT_INVESTIGATE_THRESHOLD,
    SEC_HEAT_ARREST_THRESHOLD,
    SEC_HEAT_ARREST_PROB,
    SALARY_BY_LEVEL,
    DELUSION_TIER_LOW,
    DELUSION_TIER_MID,
    DELUSION_TIER_HIGH,
    DELUSION_TIER_EFFECTS,
    PRISON_NPC_POOL,
    BANKRUPTCY_SALARY,
    UNDERGROUND_LOAN_INTEREST,
    UNDERGROUND_LOAN_DEADLINE,
)


def check_sec_heat(conn: sqlite3.Connection) -> dict:
    """
    检查监管热度并触发惩罚事件
    
    Args:
        conn: 游戏数据库连接
    
    Returns:
        dict: 触发的事件摘要
    """
    player = conn.execute(
        "SELECT sec_heat, jail_turns_left FROM Player WHERE id=1"
    ).fetchone()
    
    if not player:
        return {"triggered_events": []}
    
    heat = player["sec_heat"]
    events = []
    
    # 逮捕检查
    if heat >= SEC_HEAT_ARREST_THRESHOLD:
        if random.random() < SEC_HEAT_ARREST_PROB:
            _trigger_arrest(conn)
            events.append("ARRESTED")
    
    # 调查检查
    elif heat >= SEC_HEAT_INVESTIGATE_THRESHOLD:
        if random.random() < 0.30:
            _trigger_investigation(conn)
            events.append("INVESTIGATED")
    
    return {"triggered_events": events}


def _trigger_arrest(conn: sqlite3.Connection):
    """
    触发逮捕事件
    """
    conn.execute("""
        UPDATE Player SET
            jail_turns_left = 8,
            sec_heat = 40,
            current_job_company_id = NULL,
            job_performance = 0,
            fame = MAX(0, fame - 30),
            social_reach = CAST(social_reach * 0.6 AS INTEGER)
        WHERE id=1
    """)
    conn.commit()


def _trigger_investigation(conn: sqlite3.Connection):
    """
    触发调查事件
    """
    conn.execute("""
        UPDATE Player SET
            sec_heat = MAX(0, sec_heat - 5),
            cash = cash * 0.85
        WHERE id=1
    """)
    conn.commit()


def auto_work(conn: sqlite3.Connection):
    """
    自动执行"安分上班"
    
    若玩家在职且本回合未提交显式 work_ap，
    自动执行：job_performance+1，所在公司所有 NPC alertness 轻微下降
    
    Args:
        conn: 游戏数据库连接
    """
    player = conn.execute(
        "SELECT current_job_company_id, jail_turns_left FROM Player WHERE id=1"
    ).fetchone()
    
    if not player or not player["current_job_company_id"]:
        return
    
    if player["jail_turns_left"] > 0:
        return
    
    company_id = player["current_job_company_id"]
    
    # 增加绩效
    conn.execute(
        "UPDATE Player SET job_performance=job_performance+1 WHERE id=1"
    )
    
    # 降低所在公司 NPC 的警惕度
    conn.execute(
        "UPDATE CompanyNPC SET alertness=MAX(0, alertness-2) WHERE company_id=?",
        (company_id,)
    )
    
    conn.commit()


def pay_salary(conn: sqlite3.Connection) -> int:
    """
    发放月薪
    
    月末（每4回合）调用
    
    Args:
        conn: 游戏数据库连接
    
    Returns:
        int: 发放的薪资金额，若不满足条件则返回 0
    """
    player = conn.execute(
        "SELECT current_job_company_id, job_level, jail_turns_left FROM Player WHERE id=1"
    ).fetchone()
    
    if not player or not player["current_job_company_id"]:
        return 0
    
    if player["jail_turns_left"] > 0:
        return 0
    
    level = player["job_level"]
    salary = 0
    
    # 根据 job_level 确定薪资
    for level_range, amount in SALARY_BY_LEVEL.items():
        if level in level_range:
            salary = amount
            break
    
    if salary > 0:
        conn.execute(
            "UPDATE Player SET cash=cash+? WHERE id=1",
            (salary,)
        )
        conn.commit()
    
    return salary


def tick_buffs(conn: sqlite3.Connection):
    """
    Buff 倒计时
    
    将所有 PlayerBuffs 的 duration_turns -1，清除 duration=0 的 Buff
    
    Args:
        conn: 游戏数据库连接
    """
    # 减少所有非永久 Buff 的剩余回合数
    conn.execute(
        "UPDATE PlayerBuffs SET duration_turns=duration_turns-1 WHERE duration_turns > 0"
    )
    
    # 清除已过期的 Buff
    conn.execute(
        "DELETE FROM PlayerBuffs WHERE duration_turns=0"
    )
    
    conn.commit()


def check_jail_status(conn: sqlite3.Connection) -> bool:
    """
    检查玩家是否在坐牢
    
    Args:
        conn: 游戏数据库连接
    
    Returns:
        bool: 是否在坐牢
    """
    player = conn.execute(
        "SELECT jail_turns_left FROM Player WHERE id=1"
    ).fetchone()
    
    return player and player["jail_turns_left"] > 0


def decrement_jail_time(conn: sqlite3.Connection):
    """
    减少坐牢时间
    
    每回合调用一次
    
    Args:
        conn: 游戏数据库连接
    """
    conn.execute(
        "UPDATE Player SET jail_turns_left=MAX(0, jail_turns_left-1) WHERE id=1"
    )
    conn.commit()


def check_bankruptcy(conn: sqlite3.Connection) -> dict:
    """
    检查破产状态
    
    Returns:
        dict: 包含 in_bankruptcy 和建议操作
    """
    player = conn.execute(
        "SELECT cash, in_bankruptcy FROM Player WHERE id=1"
    ).fetchone()
    
    if not player:
        return {"in_bankruptcy": False}
    
    cash = player["cash"]
    in_bankruptcy = bool(player["in_bankruptcy"])
    
    # 破产判定：现金为负且不在破产状态
    if cash < 0 and not in_bankruptcy:
        conn.execute(
            "UPDATE Player SET in_bankruptcy=1 WHERE id=1"
        )
        conn.commit()
        in_bankruptcy = True
    
    # 退出破产：现金回正
    elif cash >= 0 and in_bankruptcy:
        conn.execute(
            "UPDATE Player SET in_bankruptcy=0 WHERE id=1"
        )
        conn.commit()
        in_bankruptcy = False
    
    return {"in_bankruptcy": in_bankruptcy}


def add_delusion_level(conn: sqlite3.Connection, delta: int):
    """
    增加妄想度
    
    Args:
        conn: 游戏数据库连接
        delta: 妄想度增量
    """
    conn.execute(
        "UPDATE Player SET delusion_level=MIN(100, delusion_level+?) WHERE id=1",
        (delta,)
    )
    conn.commit()


# ── M3: 妄想度梯级系统 ────────────────────────────────────────

def check_delusion_tier(conn: sqlite3.Connection) -> dict:
    """
    检查妄想度区间并触发对应效果
    
    根据当前妄想度返回对应区间效果，并在快照中供LLM使用
    
    Args:
        conn: 游戏数据库连接
    
    Returns:
        dict: 包含区间信息和效果描述
    """
    player = conn.execute(
        "SELECT delusion_level, fame FROM Player WHERE id=1"
    ).fetchone()
    
    if not player:
        return {"tier": "normal", "effects": None}
    
    level = player["delusion_level"]
    
    # 判定区间
    if level <= DELUSION_TIER_LOW:
        tier = "normal"
    elif level <= DELUSION_TIER_MID:
        tier = "suspicious"
    elif level <= DELUSION_TIER_HIGH:
        tier = "warning"
    else:
        tier = "psychiatric"
    
    effects = DELUSION_TIER_EFFECTS[tier]
    
    # 应用惩罚（如有）
    if effects.get("penalty"):
        penalty = effects["penalty"]
        
        if "fame_delta" in penalty:
            conn.execute(
                "UPDATE Player SET fame=MAX(0, MIN(100, fame+?)) WHERE id=1",
                (penalty["fame_delta"],)
            )
        
        if "skip_turns" in penalty and tier == "warning":
            # 警告区间：跳过1回合（心理评估）
            conn.execute(
                "UPDATE Player SET jail_turns_left=? WHERE id=1",
                (penalty["skip_turns"],)
            )
        
        if tier == "psychiatric":
            # 精神病院：触发强制事件
            trigger_psychiatric_event(conn)
        
        conn.commit()
    
    return {
        "tier": tier,
        "level": level,
        "effects": effects,
    }


def trigger_psychiatric_event(conn: sqlite3.Connection):
    """
    触发精神病院强制事件
    
    妄想度达到81+时触发，强制跳过3回合，fame清零
    """
    player = conn.execute(
        "SELECT fame, social_reach, audience_tags FROM Player WHERE id=1"
    ).fetchone()
    
    if not player:
        return
    
    # 清零fame
    new_fame = 0
    
    # 粉丝量减半
    new_social_reach = int(player["social_reach"] * 0.5)
    
    # 地下网络标签权重飙升
    import json
    try:
        tags = json.loads(player["audience_tags"]) if player["audience_tags"] else []
    except:
        tags = []
    
    # 增加地下网络标签
    underground_exists = False
    for tag_item in tags:
        if tag_item.get("tag") == "地下网络":
            tag_item["weight"] = tag_item.get("weight", 1.0) + 2.0
            underground_exists = True
            break
    
    if not underground_exists:
        tags.append({"tag": "地下网络", "weight": 3.0})
    
    # 跳过3回合
    conn.execute("""
        UPDATE Player SET
            jail_turns_left = 3,
            fame = ?,
            social_reach = ?,
            audience_tags = ?,
            delusion_level = 50
        WHERE id=1
    """, (new_fame, new_social_reach, json.dumps(tags, ensure_ascii=False)))
    
    conn.commit()


# ── M3: 监狱系统 ─────────────────────────────────────────────

def get_prison_npcs() -> list[dict]:
    """
    获取监狱专属NPC池
    
    这些NPC只有坐过牢的玩家才能接触
    
    Returns:
        list[dict]: 监狱NPC列表
    """
    return PRISON_NPC_POOL.copy()


def init_prison_npcs(conn: sqlite3.Connection) -> list[int]:
    """
    初始化监狱专属NPC
    
    当玩家首次进入监狱时调用
    
    Args:
        conn: 游戏数据库连接
    
    Returns:
        list[int]: 创建的NPC ID列表
    """
    npc_ids = []
    
    for npc_data in PRISON_NPC_POOL:
        # 创建监狱NPC（company_id设为NULL表示不属于任何公司）
        cursor = conn.execute(
            """INSERT INTO CompanyNPC 
               (company_id, name, role, bribe_resistance, alertness, 
                relationship_with_player, hidden_traits)
               VALUES (NULL, ?, ?, 50, 30, 0, ?)""",
            (npc_data["name"], npc_data["role"], 
             json.dumps({"trait": npc_data["trait"]}, ensure_ascii=False))
        )
        npc_ids.append(cursor.lastrowid)
    
    conn.commit()
    return npc_ids


# ── M3: 地下钱庄系统 ─────────────────────────────────────────

def underground_loan(
    conn: sqlite3.Connection,
    amount: float,
    current_turn: int
) -> dict:
    """
    地下钱庄借贷
    
    Args:
        conn: 游戏数据库连接
        amount: 借款金额
        current_turn: 当前回合数
    
    Returns:
        dict: 借贷结果
    """
    if amount <= 0:
        return {
            "success": False,
            "error": "INVALID_AMOUNT",
            "message": "借款金额必须大于0"
        }
    
    # 计算利息和还款总额
    interest = UNDERGROUND_LOAN_INTEREST
    repayment = amount * (1 + interest)
    deadline = current_turn + UNDERGROUND_LOAN_DEADLINE
    
    # 增加现金
    conn.execute(
        "UPDATE Player SET cash=cash+? WHERE id=1",
        (amount,)
    )
    
    # 创建还款倒计时事件
    from engines.event_engine import schedule_event
    
    event_id = schedule_event(
        conn,
        event_type="debt_collection",
        target_id=None,
        context={
            "amount": repayment,
            "original_loan": amount,
            "deadline_turn": deadline,
        },
        duration=UNDERGROUND_LOAN_DEADLINE
    )
    
    conn.commit()
    
    return {
        "success": True,
        "loan_amount": amount,
        "interest_rate": interest,
        "repayment_amount": repayment,
        "deadline_turn": deadline,
        "event_id": event_id,
        "message": f"成功借款 ¥{amount:,.0f}，需在{UNDERGROUND_LOAN_DEADLINE}回合内还款 ¥{repayment:,.0f}"
    }


# ── M3: 破产打工系统 ────────────────────────────────────────

def bankruptcy_job(conn: sqlite3.Connection) -> dict:
    """
    破产状态下的底层打工
    
    月末自动发放微薄薪资
    
    Args:
        conn: 游戏数据库连接
    
    Returns:
        dict: 打工结果
    """
    player = conn.execute(
        "SELECT cash, in_bankruptcy, jail_turns_left FROM Player WHERE id=1"
    ).fetchone()
    
    if not player:
        return {"success": False, "error": "PLAYER_NOT_FOUND"}
    
    # 必须在破产状态且不在坐牢
    if not player["in_bankruptcy"]:
        return {"success": False, "error": "NOT_IN_BANKRUPTCY"}
    
    if player["jail_turns_left"] > 0:
        return {"success": False, "error": "IN_JAIL"}
    
    salary = BANKRUPTCY_SALARY
    
    conn.execute(
        "UPDATE Player SET cash=cash+? WHERE id=1",
        (salary,)
    )
    conn.commit()
    
    return {
        "success": True,
        "salary": salary,
        "message": f"你在底层打工赚了 ¥{salary:,.0f}"
    }


def check_promotion(conn: sqlite3.Connection) -> dict:
    """
    检查晋升条件
    
    job_performance达到阈值时触发晋升检定
    
    Args:
        conn: 游戏数据库连接
    
    Returns:
        dict: 晋升检查结果
    """
    from constants import JOB_LEVEL_THRESHOLD, MAX_JOB_LEVEL
    
    player = conn.execute(
        "SELECT job_level, job_performance, current_job_company_id FROM Player WHERE id=1"
    ).fetchone()
    
    if not player or not player["current_job_company_id"]:
        return {"eligible": False, "reason": "NOT_EMPLOYED"}
    
    level = player["job_level"]
    performance = player["job_performance"]
    
    # 检查是否达到晋升条件
    if performance < JOB_LEVEL_THRESHOLD:
        return {
            "eligible": False,
            "current_level": level,
            "performance": performance,
            "threshold": JOB_LEVEL_THRESHOLD,
            "reason": "PERFORMANCE_INSUFFICIENT"
        }
    
    # 已达到最高级别
    if level >= MAX_JOB_LEVEL:
        return {
            "eligible": False,
            "current_level": level,
            "reason": "MAX_LEVEL_REACHED"
        }
    
    # 晋升检定：基于上司NPC关系值
    company_id = player["current_job_company_id"]
    
    # 获取直属上司NPC（简化：取该公司第一个高层NPC）
    supervisor = conn.execute(
        """SELECT npc_id, relationship_with_player 
           FROM CompanyNPC 
           WHERE company_id=? AND role IN ('CEO', 'CFO', '董事')
           LIMIT 1""",
        (company_id,)
    ).fetchone()
    
    success_rate = 0.5  # 基础50%
    
    if supervisor:
        rel_bonus = supervisor["relationship_with_player"] / 100.0
        success_rate += rel_bonus
    
    success = random.random() < success_rate
    
    if success:
        # 晋升成功
        new_level = level + 1
        conn.execute(
            "UPDATE Player SET job_level=?, job_performance=0 WHERE id=1",
            (new_level,)
        )
        conn.commit()
        
        return {
            "eligible": True,
            "success": True,
            "old_level": level,
            "new_level": new_level,
            "message": f"恭喜！你晋升到了 Level {new_level}"
        }
    else:
        # 晋升失败，绩效减半
        conn.execute(
            "UPDATE Player SET job_performance=? WHERE id=1",
            (performance // 2,)
        )
        conn.commit()
        
        return {
            "eligible": True,
            "success": False,
            "current_level": level,
            "performance": performance // 2,
            "message": "晋升失败，需要继续努力"
        }


# ── 社交影响力计算 ──────────────────────────────────────

def calculate_social_reach(followers: int, audience_tags: list, fame: int) -> int:
    """
    计算社交影响力（纯数值计算，无需 LLM 参与）
    
    社交影响力 = 粉丝基数 × 粉丝质量 × 名气加成
    
    Args:
        followers: 全网粉丝量
        audience_tags: 粉丝画像标签数组 [{"tag": "阴谋论粉丝", "weight": 1.2}, ...]
        fame: 个人名气
    
    Returns:
        social_reach: 社交影响力（用于判断发帖影响股价的强度）
    
    公式说明：
    - 基础影响力：平方根增长，避免后期数值爆炸
      例：1000粉 = 316, 10000粉 = 1000, 100万粉 = 10000
    - 粉丝质量：标签权重越集中 = 粉丝越精准活跃（0.5 ~ 1.0）
    - 名气加成：名人发帖自带流量（fame=100 → 1.5x）
    """
    # 1. 基础影响力（平方根增长）
    base_reach = int(max(1, followers) ** 0.5 * 10)
    
    # 2. 粉丝质量系数（标签权重越集中 = 粉丝越精准活跃）
    if audience_tags and isinstance(audience_tags, list):
        # 提取权重值
        tag_weights = [t.get("weight", 0.0) for t in audience_tags if isinstance(t, dict)]
        if tag_weights:
            # 取前3个最高权重标签
            top_3_weights = sorted(tag_weights, reverse=True)[:3]
            # 归一化权重（假设单个标签权重在 1.0 ~ 2.0 之间）
            normalized_weights = [min(w / 2.0, 1.0) for w in top_3_weights]
            quality_mult = 0.5 + sum(normalized_weights) * 0.5 / 3  # 0.5 ~ 1.0
        else:
            quality_mult = 0.5
    else:
        quality_mult = 0.5  # 无标签 = 粉丝质量低
    
    # 3. 名气加成（名人发帖自带流量）
    fame_mult = 1.0 + fame / 200  # fame=100 → 1.5x
    
    # 4. 最终影响力
    social_reach = int(base_reach * quality_mult * fame_mult)
    
    return social_reach


def update_social_reach(conn: sqlite3.Connection) -> int:
    """
    重新计算并更新玩家的社交影响力
    
    在以下情况调用：
    - 粉丝数变化（涨粉/掉粉）
    - 粉丝画像变化（标签漂移）
    - 名气变化
    
    Args:
        conn: 游戏数据库连接
    
    Returns:
        int: 更新后的 social_reach
    """
    player = conn.execute(
        "SELECT followers, audience_tags, fame FROM Player WHERE id=1"
    ).fetchone()
    
    if not player:
        return 0
    
    audience_tags = json.loads(player["audience_tags"])
    new_social_reach = calculate_social_reach(
        player["followers"],
        audience_tags,
        player["fame"]
    )
    
    conn.execute(
        "UPDATE Player SET social_reach=? WHERE id=1",
        (new_social_reach,)
    )
    conn.commit()
    
    return new_social_reach

