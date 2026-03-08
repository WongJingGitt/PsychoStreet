"""
游戏初始化工具
包含 init_player, init_companies, init_npcs, init_macro_events, init_market_prices
"""

import json
import random
import sqlite3
from typing import Any

from constants import (
    WEAKNESS_POOL,
    SECRET_POOL,
    PREFERENCE_POOL,
    FUNDAMENTALS_TEMPLATES,
    TREND_BIAS_BULLISH,
    TREND_BIAS_BEARISH,
    TREND_BIAS_MIXED,
)

from db.content_pool import (
    draw_companies,
    draw_celebrities,
    draw_institutions,
    get_pool_status,
    get_company_by_name,
    get_celebrity_by_name,
)


def _json_response(data: dict) -> str:
    """将字典转换为 JSON 字符串"""
    return json.dumps(data, ensure_ascii=False, indent=2)


def _error_response(error_code: str, message: str = "") -> str:
    """生成错误响应"""
    return _json_response({"error": error_code, "message": message})


# ── 初始化工具实现 ──────────────────────────────────────

def init_player(conn: sqlite3.Connection, name: str, starting_cash: float) -> str:
    """
    初始化玩家
    
    Args:
        conn: 游戏数据库连接
        name: 玩家名称
        starting_cash: 初始资金
    
    Returns:
        str: JSON 格式的响应
    """
    try:
        # 清空旧的玩家数据（支持重新初始化）
        conn.execute("DELETE FROM Player")
        
        # 插入新玩家
        conn.execute(
            """INSERT INTO Player 
               (id, cash, fame, followers, social_reach, audience_tags, sec_heat, 
                jail_turns_left, in_bankruptcy, current_job_company_id, 
                job_level, job_performance, delusion_level)
               VALUES (1, ?, 0, 0, 0, '[]', 0, 0, 0, NULL, 0, 0, 0)""",
            (starting_cash,)
        )
        
        # 更新 GameMeta 中的玩家名称
        conn.execute(
            "UPDATE GameMeta SET value=? WHERE key='player_name'",
            (name,)
        )
        
        conn.commit()
        
        return _json_response({
            "player_id": 1,
            "name": name,
            "cash": starting_cash,
            "message": f"玩家 '{name}' 已创建，初始资金 {starting_cash:,.2f}"
        })
        
    except Exception as e:
        return _error_response("INIT_PLAYER_FAILED", str(e))


def init_companies(conn: sqlite3.Connection, companies: list[dict] | None = None) -> str:
    """
    初始化公司与股票
    
    Args:
        conn: 游戏数据库连接
        companies: 公司列表（可选）。如果为空，则从内容池随机抽取。
            - name: 公司名称
            - industry_tag: 行业标签
            - description: 公司简介
    
    Returns:
        str: JSON 格式的响应
    """
    try:
        if not companies:
            pool_status = get_pool_status()
            available = pool_status.get("companies_remaining", 0)
            if available == 0:
                return _error_response(
                    "COMPANY_POOL_EXHAUSTED",
                    "公司池已用完，请先在游戏设定中定义公司列表，或调用新股上市逻辑"
                )
            companies = draw_companies(15)
        
        stock_ids = []
        
        for company in companies:
            # 随机生成隐藏属性
            fundamental_value = random.uniform(20.0, 500.0)
            momentum = random.uniform(-3.0, 3.0)
            liquidity = random.uniform(50_000.0, 2_000_000.0)
            pr_defense = random.randint(20, 80)
            scandal_risk = random.randint(0, 20)
            fundamentals = random.choice(FUNDAMENTALS_TEMPLATES)
            
            # 初始价格围绕内在价值波动
            current_price = fundamental_value * random.uniform(0.7, 1.3)
            current_price = round(current_price, 2)
            
            # 插入股票记录
            cursor = conn.execute(
                """INSERT INTO Stock 
                   (name, industry_tag, description, current_price, 
                    hidden_fundamentals, hidden_fundamental_value, 
                    hidden_momentum, hidden_liquidity, 
                    hidden_pr_defense, hidden_scandal_risk, is_revealed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (company["name"], company["industry_tag"], company["description"],
                 current_price, fundamentals, fundamental_value, 
                 momentum, liquidity, pr_defense, scandal_risk)
            )
            
            stock_ids.append(cursor.lastrowid)
        
        conn.commit()
        
        return _json_response({
            "created": len(stock_ids),
            "stock_ids": stock_ids,
            "message": f"已创建 {len(stock_ids)} 家公司"
        })
        
    except Exception as e:
        return _error_response("INIT_COMPANIES_FAILED", str(e))


def init_npcs(conn: sqlite3.Connection, npcs: list[dict] | None = None) -> str:
    """
    初始化公司 NPC
    
    Args:
        conn: 游戏数据库连接
        npcs: NPC列表（可选）。如果为空，则从名人池随机抽取。
            - company_id: 所属公司ID
            - name: NPC名称
            - role: 职位
    
    Returns:
        str: JSON 格式的响应
    """
    try:
        if not npcs:
            pool_status = get_pool_status()
            available = pool_status.get("celebrities_remaining", 0)
            if available == 0:
                return _error_response(
                    "CELEBRITY_POOL_EXHAUSTED",
                    "名人池已用完，请先在游戏设定中定义 NPC 列表"
                )
            
            companies = conn.execute("SELECT id, name FROM Stock").fetchall()
            npcs = []
            
            for company in companies:
                celebs = draw_celebrities(2)
                for celeb in celebs:
                    npcs.append({
                        "company_id": company["id"],
                        "name": celeb["name"],
                        "role": celeb["role"]
                    })
        
        npc_ids = []
        
        for npc in npcs:
            # 随机生成隐藏特质
            hidden_traits = {
                "weakness": random.choice(WEAKNESS_POOL),
                "secret": random.choice(SECRET_POOL),
                "preference": random.choice(PREFERENCE_POOL),
            }
            
            # 随机生成属性
            bribe_resistance = random.randint(20, 80)
            alertness = random.randint(10, 40)
            
            # 插入 NPC 记录
            cursor = conn.execute(
                """INSERT INTO CompanyNPC 
                   (company_id, name, role, bribe_resistance, alertness, 
                    relationship_with_player, hidden_traits)
                   VALUES (?, ?, ?, ?, ?, 0, ?)""",
                (npc["company_id"], npc["name"], npc["role"], 
                 bribe_resistance, alertness, json.dumps(hidden_traits, ensure_ascii=False))
            )
            
            npc_ids.append(cursor.lastrowid)
        
        conn.commit()
        
        return _json_response({
            "created": len(npc_ids),
            "npc_ids": npc_ids,
            "message": f"已创建 {len(npc_ids)} 个 NPC"
        })
        
    except Exception as e:
        return _error_response("INIT_NPCS_FAILED", str(e))


def init_macro_events(conn: sqlite3.Connection, total_turns: int) -> str:
    """
    初始化宏观事件
    
    Args:
        conn: 游戏数据库连接
        total_turns: 游戏总回合数
    
    Returns:
        str: JSON 格式的响应
    """
    try:
        # 1. 生成定时事件（财报季，每13回合一次）
        quarter_events = 0
        for turn in range(13, total_turns + 1, 13):
            price_impact = random.uniform(0.85, 1.15)
            conn.execute(
                """INSERT INTO MacroEvents 
                   (trigger_turn, trigger_probability, industry_tag, 
                    price_impact_multiplier, description_template, is_triggered)
                   VALUES (?, 0.0, NULL, ?, '季度财报发布，市场整体波动', 0)""",
                (turn, price_impact)
            )
            quarter_events += 1
        
        # 2. 生成随机黑天鹅事件（5~8个）
        black_swan_events = random.randint(5, 8)
        
        # 获取已有行业标签
        cursor = conn.execute("SELECT DISTINCT industry_tag FROM Stock")
        industries = [row[0] for row in cursor.fetchall()]
        
        for _ in range(black_swan_events):
            trigger_prob = random.uniform(0.03, 0.08)
            # 50% 概率影响特定行业，50% 概率影响全市场
            industry_tag = random.choice(industries + [None]) if industries else None
            price_impact = random.uniform(0.6, 1.4)
            
            description_templates = [
                "行业监管政策突变，市场震荡",
                "宏观经济数据不及预期，投资者情绪受挫",
                "国际局势紧张，避险资产受追捧",
                "行业龙头发布预警，板块承压",
                "央行货币政策调整，流动性预期变化",
            ]
            description = random.choice(description_templates)
            
            conn.execute(
                """INSERT INTO MacroEvents 
                   (trigger_turn, trigger_probability, industry_tag, 
                    price_impact_multiplier, description_template, is_triggered)
                   VALUES (-1, ?, ?, ?, ?, 0)""",
                (trigger_prob, industry_tag, price_impact, description)
            )
        
        conn.commit()
        
        total_events = quarter_events + black_swan_events
        
        return _json_response({
            "created": total_events,
            "quarter_events": quarter_events,
            "random_events": black_swan_events,
            "message": f"已创建 {total_events} 个宏观事件"
        })
        
    except Exception as e:
        return _error_response("INIT_MACRO_EVENTS_FAILED", str(e))


def init_macro_trends(conn: sqlite3.Connection, trends: list) -> str:
    """
    初始化宏观趋势（持续性风向标）
    
    由 LLM 传入趋势的叙事信息，MCP 生成隐藏的 price_bias 数值。
    
    Args:
        conn: 游戏数据库连接
        trends: 趋势列表，每项包含：
            - name (str): 趋势名称，如 "AI爆发期"
            - description (str): LLM 生成的背景叙事，落库保存确保一致性
            - industry_tag (str | null): 受影响行业，null 表示全市场
            - direction (str): "bullish" / "bearish" / "mixed"
            - start_turn (int): 开始回合，默认 1
            - end_turn (int): 结束回合，-1 表示持续到游戏结束
    
    Returns:
        str: JSON 格式的响应，含已创建的 trend_id 列表（不含 price_bias）
    """
    _BIAS_RANGES = {
        "bullish": TREND_BIAS_BULLISH,
        "bearish": TREND_BIAS_BEARISH,
        "mixed":   TREND_BIAS_MIXED,
    }
    
    try:
        created = []
        for t in trends:
            name         = t.get("name", "未命名趋势")
            description  = t.get("description", "")
            industry_tag = t.get("industry_tag")
            direction    = t.get("direction", "bullish")
            start_turn   = int(t.get("start_turn", 1))
            end_turn     = int(t.get("end_turn", -1))
            
            if direction not in _BIAS_RANGES:
                direction = "bullish"
            
            lo, hi = _BIAS_RANGES[direction]
            price_bias = round(random.uniform(lo, hi), 3)
            
            cursor = conn.execute(
                """INSERT INTO MacroTrends
                   (name, description, industry_tag, direction,
                    price_bias, start_turn, end_turn, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
                (name, description, industry_tag, direction,
                 price_bias, start_turn, end_turn)
            )
            created.append({
                "trend_id": cursor.lastrowid,
                "name": name,
                "industry_tag": industry_tag,
                "direction": direction,
                "start_turn": start_turn,
                "end_turn": end_turn,
            })
        
        conn.commit()
        return _json_response({
            "created": len(created),
            "trends": created,
            "message": f"已创建 {len(created)} 条宏观趋势"
        })
    
    except Exception as e:
        return _error_response("INIT_MACRO_TRENDS_FAILED", str(e))


def init_market_prices(conn: sqlite3.Connection) -> str:
    """
    初始化市场价格（基于内在价值）

    Args:
        conn: 游戏数据库连接

    Returns:
        str: JSON 格式的响应
    """
    try:
        cursor = conn.execute(
            "SELECT id, hidden_fundamental_value FROM Stock"
        )
        stocks = cursor.fetchall()

        updated = 0
        for stock_id, fundamental_value in stocks:
            current_price = fundamental_value * random.uniform(0.80, 1.20)
            current_price = round(current_price, 2)

            conn.execute(
                "UPDATE Stock SET current_price=? WHERE id=?",
                (current_price, stock_id)
            )
            updated += 1

        conn.commit()

        return _json_response({
            "updated": updated,
            "message": f"已初始化 {updated} 支股票的价格"
        })

    except Exception as e:
        return _error_response("INIT_MARKET_PRICES_FAILED", str(e))


def init_institutions(conn: sqlite3.Connection, count: int = 4, types: list[str] | None = None) -> str:
    """
    初始化 AI 机构

    Args:
        conn: 游戏数据库连接
        count: 机构数量，默认 4 家
        types: 指定机构类型列表，如 ["value", "hedge_short", "quant"]（可选，默认从内容池抽取）

    Returns:
        str: JSON 格式的响应
    """
    try:
        existing = conn.execute("SELECT COUNT(*) FROM Institution").fetchone()[0]
        if existing > 0:
            return _json_response({
                "created": 0,
                "message": f"机构已存在 ({existing} 家)，跳过初始化"
            })

        pool_status = get_pool_status()
        available = pool_status.get("institutions_remaining", 0)
        
        if available < count:
            return _error_response(
                "INSTITUTION_POOL_EXHAUSTED",
                f"机构池剩余 {available} 家，不足以创建 {count} 家"
            )

        created = []

        if types is None:
            drawn = draw_institutions(count)
        else:
            drawn = []
            for t in types:
                pool = draw_institutions(1, type_filter=t)
                if pool:
                    drawn.extend(pool)
            if len(drawn) < count:
                remaining = count - len(drawn)
                extra = draw_institutions(remaining)
                drawn.extend(extra)

        for inst in drawn:
            capital = inst.get("capital", random.uniform(50_000_000, 200_000_000))
            risk_tolerance = random.uniform(0.3, 0.8)

            cursor = conn.execute(
                """INSERT INTO Institution (name, type, capital, risk_tolerance, status)
                   VALUES (?, ?, ?, ?, 'active')""",
                (inst["name"], inst["type"], capital, risk_tolerance)
            )
            created.append({
                "inst_id": cursor.lastrowid,
                "name": inst["name"],
                "type": inst["type"],
                "capital": round(capital, 2),
            })

        conn.commit()

        return _json_response({
            "created": len(created),
            "institutions": created,
            "message": f"已创建 {len(created)} 家 AI 机构"
        })

    except Exception as e:
        return _error_response("INIT_INSTITUTIONS_FAILED", str(e))


# ── MCP 工具包装函数 ──────────────────────────────────────

def tool_init_player(name: str, starting_cash: float) -> str:
    """MCP 工具：初始化玩家（需要连接参数）"""
    # 注意：实际使用时需要从 main.py 获取连接
    raise NotImplementedError("tool_init_player 需要在 main.py 中实现")


def tool_init_companies(companies: list[dict]) -> str:
    """MCP 工具：初始化公司（需要连接参数）"""
    raise NotImplementedError("tool_init_companies 需要在 main.py 中实现")


def tool_init_npcs(npcs: list[dict]) -> str:
    """MCP 工具：初始化 NPC（需要连接参数）"""
    raise NotImplementedError("tool_init_npcs 需要在 main.py 中实现")


def tool_init_macro_events(total_turns: int) -> str:
    """MCP 工具：初始化宏观事件（需要连接参数）"""
    raise NotImplementedError("tool_init_macro_events 需要在 main.py 中实现")


def tool_init_market_prices() -> str:
    """MCP 工具：初始化市场价格（需要连接参数）"""
    raise NotImplementedError("tool_init_market_prices 需要在 main.py 中实现")


def list_available_companies() -> str:
    """
    列出内容池中剩余可用的公司
    
    Returns:
        str: JSON 格式的公司列表
    """
    from db.content_pool import _load_pool, _companies_pool
    
    _load_pool()
    
    return _json_response({
        "available": len(_companies_pool),
        "companies": [
            {"name": c["name"], "industry_tag": c["industry_tag"]}
            for c in _companies_pool
        ]
    })


def get_pool_status_tool() -> str:
    """
    获取内容池剩余状态
    
    Returns:
        str: JSON 格式的状态信息
    """
    return _json_response(get_pool_status())
