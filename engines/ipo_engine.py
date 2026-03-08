"""
IPO（新股上市）引擎
负责新股生成、上市时机判断、初始属性随机化
"""
from __future__ import annotations

import json
import random
import sqlite3
from typing import Any

from constants import (
    MARKET_MAX_STOCKS,
    IPO_CHECK_INTERVAL_MIN,
    IPO_CHECK_INTERVAL_MAX,
    IPO_BASE_PROBABILITY,
    IPO_HOT_INDUSTRY_MULTIPLIER,
    IPO_INITIAL_PRICE_MIN,
    IPO_INITIAL_PRICE_MAX,
    CORE_INDUSTRIES,
    FUNDAMENTALS_TEMPLATES,
)


def should_trigger_ipo(conn: sqlite3.Connection, current_turn: int) -> bool:
    """
    判断本回合是否应该触发 IPO 检测
    
    触发条件：
    - 距离上次 IPO 已过 5~10 回合（随机间隔）
    - 大盘股票数 < 30
    
    Args:
        conn: 游戏数据库连接
        current_turn: 当前回合数
    
    Returns:
        bool: 是否应该触发 IPO
    """
    # 检查大盘股票数
    total_stocks = conn.execute(
        "SELECT COUNT(*) as count FROM Stock WHERE is_delisted=0"
    ).fetchone()["count"]
    
    if total_stocks >= MARKET_MAX_STOCKS:
        return False
    
    # 查询最近一次 IPO 的回合数
    last_ipo = conn.execute(
        "SELECT MAX(listed_turn) as last_turn FROM Stock"
    ).fetchone()["last_turn"]
    
    if last_ipo is None:
        last_ipo = 0
    
    # 计算间隔
    interval = current_turn - last_ipo
    
    # 随机间隔检测
    min_interval = random.randint(IPO_CHECK_INTERVAL_MIN, IPO_CHECK_INTERVAL_MAX)
    
    return interval >= min_interval


def select_ipo_industry(conn: sqlite3.Connection) -> tuple[str, str]:
    """
    选择 IPO 行业（优先热门行业）
    
    热门行业定义：当前有 bullish 宏观趋势的行业
    
    Args:
        conn: 游戏数据库连接
    
    Returns:
        tuple[str, str]: (行业名称, 子标签)
    """
    # 查询活跃的 bullish 趋势
    hot_industries = conn.execute(
        """SELECT industry_tag FROM MacroTrends 
           WHERE is_active=1 AND direction='bullish' AND industry_tag IS NOT NULL"""
    ).fetchall()
    
    hot_industry_tags = [row["industry_tag"] for row in hot_industries]
    
    # 构建行业权重
    industry_weights = []
    for industry, config in CORE_INDUSTRIES.items():
        weight = IPO_HOT_INDUSTRY_MULTIPLIER if industry in hot_industry_tags else 1.0
        industry_weights.append((industry, config, weight))
    
    # 加权随机选择
    total_weight = sum(w for _, _, w in industry_weights)
    rand = random.uniform(0, total_weight)
    
    cumulative = 0
    selected_industry = None
    selected_config = None
    
    for industry, config, weight in industry_weights:
        cumulative += weight
        if rand <= cumulative:
            selected_industry = industry
            selected_config = config
            break
    
    # 随机选择子标签
    sub_tag = random.choice(selected_config["tags"])
    
    return selected_industry, sub_tag


def generate_ipo_stock(
    conn: sqlite3.Connection,
    current_turn: int,
    company_name: str = None,
    description: str = None
) -> dict:
    """
    生成一支新股并上市
    
    如果 company_name 和 description 为 None，则使用占位符
    （实际游戏中应由 LLM 生成）
    
    Args:
        conn: 游戏数据库连接
        current_turn: 当前回合数
        company_name: 公司名称（可选，由 LLM 生成）
        description: 公司描述（可选，由 LLM 生成）
    
    Returns:
        dict: 新股信息
    """
    # 概率检测
    if random.random() > IPO_BASE_PROBABILITY:
        return None
    
    # 选择行业
    industry, sub_tag = select_ipo_industry(conn)
    
    # 生成占位符名称和描述（实际应由 LLM 生成）
    if not company_name:
        company_name = f"【待命名】{industry}{sub_tag}公司"
    
    if not description:
        description = f"一家专注于{sub_tag}领域的{industry}企业"
    
    # 随机生成隐藏属性
    initial_price = round(random.uniform(IPO_INITIAL_PRICE_MIN, IPO_INITIAL_PRICE_MAX), 2)
    fundamental_value = round(initial_price * random.uniform(0.8, 1.2), 2)
    momentum = random.uniform(-2.0, 2.0)
    liquidity = random.uniform(0.5, 1.5)
    pr_defense = random.randint(30, 70)
    scandal_risk = random.randint(0, 20)
    
    # 随机选择隐藏基本面
    hidden_fundamentals = random.sample(FUNDAMENTALS_TEMPLATES, k=random.randint(1, 3))
    fundamentals_text = ", ".join(hidden_fundamentals)
    
    # 插入数据库
    cursor = conn.execute(
        """INSERT INTO Stock 
           (name, industry_tag, description, current_price, 
            hidden_fundamentals, hidden_fundamental_value, hidden_momentum, 
            hidden_liquidity, hidden_pr_defense, hidden_scandal_risk, 
            is_revealed, is_delisted, delisting_risk, consecutive_decline_turns, 
            last_turn_price, listed_turn)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, ?, ?)""",
        (company_name, industry, description, initial_price,
         fundamentals_text, fundamental_value, momentum,
         liquidity, pr_defense, scandal_risk,
         initial_price, current_turn)
    )
    
    stock_id = cursor.lastrowid
    conn.commit()
    
    return {
        "stock_id": stock_id,
        "name": company_name,
        "industry_tag": industry,
        "sub_tag": sub_tag,
        "description": description,
        "initial_price": initial_price,
        "listed_turn": current_turn,
    }


def trigger_ipo(conn: sqlite3.Connection, current_turn: int) -> dict | None:
    """
    触发 IPO 流程（完整流程，包含 LLM 命名）
    
    实际使用时，应该：
    1. 调用此函数生成占位符新股
    2. LLM 根据行业和子标签生成公司名称和描述
    3. 调用 update_ipo_info 更新名称和描述
    
    Args:
        conn: 游戏数据库连接
        current_turn: 当前回合数
    
    Returns:
        dict | None: IPO 信息，如果未触发则返回 None
    """
    if not should_trigger_ipo(conn, current_turn):
        return None
    
    return generate_ipo_stock(conn, current_turn)


def update_ipo_info(conn: sqlite3.Connection, stock_id: int, name: str, description: str):
    """
    更新 IPO 股票的名称和描述（由 LLM 生成后调用）
    
    Args:
        conn: 游戏数据库连接
        stock_id: 股票 ID
        name: 新名称
        description: 新描述
    """
    conn.execute(
        "UPDATE Stock SET name=?, description=? WHERE id=?",
        (name, description, stock_id)
    )
    conn.commit()
