"""
特殊结局判定引擎
负责检查玩家状态是否触发七大特殊结局
"""

import json
import sqlite3

from constants import ENDING_THRESHOLDS


def check_endings(conn: sqlite3.Connection) -> dict:
    """
    检查是否触发特殊结局
    
    每回合结束时调用，基于玩家状态判断是否达成特殊结局
    
    Args:
        conn: 游戏数据库连接
    
    Returns:
        dict: 结局检查结果
            - triggered: bool - 是否触发结局
            - ending_type: str | None - 结局类型
            - ending_data: dict | None - 结局详情
            - message: str - 提示信息
    """
    player = conn.execute(
        """SELECT cash, fame, sec_heat, delusion_level, job_level, job_performance,
                  current_job_company_id, audience_tags, jail_turns_left
           FROM Player WHERE id=1"""
    ).fetchone()
    
    if not player:
        return {"triggered": False, "message": "玩家数据不存在"}
    
    # 按优先级依次检查各结局
    
    # 1. 华尔街疯子（妄想度81+）
    result = _check_wall_street_madman(player)
    if result["triggered"]:
        return result
    
    # 2. 年度最佳员工（晋升为CEO）
    result = _check_best_employee(player, conn)
    if result["triggered"]:
        return result
    
    # 3. 公敌（sec_heat满级）
    result = _check_public_enemy(player)
    if result["triggered"]:
        return result
    
    # 4. 归隐田园（金盆洗手）
    result = _check_retire(player)
    if result["triggered"]:
        return result
    
    # 5. 幕后黑手（低调操控）
    result = _check_puppet_master(player, conn)
    if result["triggered"]:
        return result
    
    # 6. 地下皇帝（监狱路线）
    result = _check_underground_emperor(player, conn)
    if result["triggered"]:
        return result
    
    # 7. 市场崩溃（特殊事件，复杂实现）
    # 暂时跳过，需要额外的全局状态追踪
    
    return {"triggered": False, "message": "暂未达成任何特殊结局"}


def _check_wall_street_madman(player: dict) -> dict:
    """
    检查华尔街疯子结局
    
    触发条件：delusion_level >= 81
    """
    threshold = ENDING_THRESHOLDS["wall_street_madman"]
    
    if player["delusion_level"] >= threshold["delusion_level"]:
        return {
            "triggered": True,
            "ending_type": "wall_street_madman",
            "ending_data": threshold,
            "message": "【结局：华尔街疯子】你的妄想让你成为了一个传奇——虽然是个疯子传奇。"
        }
    
    return {"triggered": False}


def _check_best_employee(player: dict, conn: sqlite3.Connection) -> dict:
    """
    检查年度最佳员工结局
    
    触发条件：job_level = 10 (CEO级别)
    """
    threshold = ENDING_THRESHOLDS["best_employee"]
    
    if player["job_level"] >= threshold["job_level"]:
        # 获取公司名称
        company_name = "某公司"
        if player["current_job_company_id"]:
            company = conn.execute(
                "SELECT name FROM Stock WHERE id=?",
                (player["current_job_company_id"],)
            ).fetchone()
            if company:
                company_name = company["name"]
        
        return {
            "triggered": True,
            "ending_type": "best_employee",
            "ending_data": {
                **threshold,
                "company_name": company_name,
            },
            "message": f"【结局：年度最佳员工】你一路晋升，最终成为了 {company_name} 的CEO。虽然过程可能不太光彩，但结果是好的。"
        }
    
    return {"triggered": False}


def _check_public_enemy(player: dict) -> dict:
    """
    检查公敌结局
    
    触发条件：sec_heat = 100 且 fame = 0
    """
    threshold = ENDING_THRESHOLDS["public_enemy"]
    
    if player["sec_heat"] >= threshold["sec_heat"] and player["fame"] <= threshold["fame"]:
        return {
            "triggered": True,
            "ending_type": "public_enemy",
            "ending_data": threshold,
            "message": "【结局：公敌】你成为了全球头号通缉的经济罪犯，臭名昭著。虽然你最终逃脱了法律制裁，但也失去了一切。"
        }
    
    return {"triggered": False}


def _check_retire(player: dict) -> dict:
    """
    检查归隐田园结局
    
    触发条件：cash >= 100万, sec_heat = 0, fame = 0
    注意：需要玩家主动选择，这里只是检查条件
    """
    threshold = ENDING_THRESHOLDS["retire"]
    
    if (player["cash"] >= threshold["cash"] and 
        player["sec_heat"] <= threshold["sec_heat"] and 
        player["fame"] <= threshold["fame"]):
        return {
            "triggered": True,
            "ending_type": "retire",
            "ending_data": threshold,
            "message": "【结局：归隐田园】你赚够了第一桶金，选择金盆洗手。在这个市场上，能全身而退的人寥寥无几。"
        }
    
    return {"triggered": False}


def _check_puppet_master(player: dict, conn: sqlite3.Connection) -> dict:
    """
    检查幕后黑手结局
    
    触发条件：fame <= 20, sec_heat <= 20, portfolio价值 >= 500万
    """
    threshold = ENDING_THRESHOLDS["puppet_master"]
    
    # 检查声望和热度
    if (player["fame"] > threshold["fame_max"] or 
        player["sec_heat"] > threshold["sec_heat_max"]):
        return {"triggered": False}
    
    # 计算持仓价值
    portfolio_value = player["cash"]  # 现金
    
    holdings = conn.execute(
        """SELECT p.quantity, s.current_price
           FROM Portfolio p
           JOIN Stock s ON p.stock_id = s.id
           WHERE p.player_id=1 AND p.quantity > 0"""
    ).fetchall()
    
    for holding in holdings:
        portfolio_value += holding["quantity"] * holding["current_price"]
    
    if portfolio_value >= threshold["portfolio_value"]:
        return {
            "triggered": True,
            "ending_type": "puppet_master",
            "ending_data": {
                **threshold,
                "portfolio_value": portfolio_value,
            },
            "message": f"【结局：幕后黑手】你始终保持低调，悄悄操控着整个市场。持仓价值 ¥{portfolio_value:,.0f}，却没人知道你是谁。"
        }
    
    return {"triggered": False}


def _check_underground_emperor(player: dict, conn: sqlite3.Connection) -> dict:
    """
    检查地下皇帝结局
    
    触发条件：累计坐牢20回合 + underground_network权重 >= 3.0
    
    注意：累计坐牢时间需要额外追踪，这里简化处理
    """
    threshold = ENDING_THRESHOLDS["underground_emperor"]
    
    # 解析受众标签
    try:
        tags = json.loads(player["audience_tags"]) if player["audience_tags"] else []
    except json.JSONDecodeError:
        tags = []
    
    # 查找地下网络标签权重
    underground_weight = 0.0
    for tag_item in tags:
        if tag_item.get("tag") == "地下网络":
            underground_weight = tag_item.get("weight", 1.0)
            break
    
    # 检查条件（简化：假设jail_turns_left > 0表示有坐牢经历）
    # 实际应该追踪累计坐牢时间
    if underground_weight >= threshold["underground_network_weight"]:
        # 这里需要额外的累计坐牢时间追踪
        # 暂时用简单检查替代
        return {
            "triggered": True,
            "ending_type": "underground_emperor",
            "ending_data": {
                **threshold,
                "underground_weight": underground_weight,
            },
            "message": f"【结局：地下皇帝】你在监狱中建立了庞大的地下网络，出狱后成为黑白两道通吃的大人物。"
        }
    
    return {"triggered": False}


def get_ending_progress(conn: sqlite3.Connection) -> dict:
    """
    获取各结局的进度信息
    
    用于UI展示玩家距离各结局还有多远
    
    Args:
        conn: 游戏数据库连接
    
    Returns:
        dict: 各结局的进度信息
    """
    player = conn.execute(
        """SELECT cash, fame, sec_heat, delusion_level, job_level,
                  current_job_company_id, audience_tags
           FROM Player WHERE id=1"""
    ).fetchone()
    
    if not player:
        return {}
    
    progress = {}
    
    # 华尔街疯子
    progress["wall_street_madman"] = {
        "current": player["delusion_level"],
        "target": ENDING_THRESHOLDS["wall_street_madman"]["delusion_level"],
        "percent": min(100, player["delusion_level"] / 81.0 * 100),
    }
    
    # 年度最佳员工
    progress["best_employee"] = {
        "current": player["job_level"],
        "target": ENDING_THRESHOLDS["best_employee"]["job_level"],
        "percent": player["job_level"] / 10.0 * 100,
    }
    
    # 公敌
    sec_ok = player["sec_heat"] >= 100
    fame_ok = player["fame"] <= 0
    progress["public_enemy"] = {
        "conditions": {
            "sec_heat": {"current": player["sec_heat"], "target": 100, "met": sec_ok},
            "fame": {"current": player["fame"], "target": 0, "met": fame_ok},
        },
        "percent": (100 if sec_ok else player["sec_heat"]) * 0.5 + (100 if fame_ok else (100 - player["fame"]) * 0.5),
    }
    
    # 归隐田园
    cash_ok = player["cash"] >= 1_000_000
    sec_ok = player["sec_heat"] <= 0
    fame_ok = player["fame"] <= 0
    progress["retire"] = {
        "conditions": {
            "cash": {"current": player["cash"], "target": 1_000_000, "met": cash_ok},
            "sec_heat": {"current": player["sec_heat"], "target": 0, "met": sec_ok},
            "fame": {"current": player["fame"], "target": 0, "met": fame_ok},
        },
        "percent": sum([
            100 if cash_ok else min(100, player["cash"] / 10_000),
            100 if sec_ok else (100 - player["sec_heat"]),
            100 if fame_ok else (100 - player["fame"]),
        ]) / 3.0,
    }
    
    # 幕后黑手
    fame_ok = player["fame"] <= 20
    sec_ok = player["sec_heat"] <= 20
    progress["puppet_master"] = {
        "conditions": {
            "fame": {"current": player["fame"], "target": 20, "met": fame_ok},
            "sec_heat": {"current": player["sec_heat"], "target": 20, "met": sec_ok},
        },
        "percent": sum([
            100 if fame_ok else max(0, (20 - player["fame"]) / 20 * 100),
            100 if sec_ok else max(0, (20 - player["sec_heat"]) / 20 * 100),
        ]) / 2.0,
    }
    
    # 地下皇帝
    try:
        tags = json.loads(player["audience_tags"]) if player["audience_tags"] else []
    except:
        tags = []
    
    underground_weight = 0.0
    for tag_item in tags:
        if tag_item.get("tag") == "地下网络":
            underground_weight = tag_item.get("weight", 1.0)
            break
    
    progress["underground_emperor"] = {
        "underground_weight": underground_weight,
        "target": 3.0,
        "percent": min(100, underground_weight / 3.0 * 100),
    }
    
    return progress
