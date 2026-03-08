"""
《发疯华尔街》MCP Server
"""

from __future__ import annotations
from pathlib import Path
import json
import shutil
import sqlite3
from datetime import datetime
from typing import Any

from mcp.server import Server
from mcp.types import Tool, TextContent

from db import global_db, game_db
from db.schema import init_global_db, init_game_db
from constants import DEFAULT_STARTING_CASH, DEFAULT_COMPANY_COUNT, DEFAULT_TOTAL_TURNS
from tools import session_tools, init_tools, turn_tools, trade_tools, intent_tools, job_tools, inventory_tools
from engines.turn_engine import advance_turn


# ── 全局状态 ──────────────────────────────────────────────

_active_game_conn: sqlite3.Connection | None = None
_active_game_id: int | None = None

def _load_game_master_prompt() -> str:
    """从 md 文件加载游戏主持人 prompt，每次调用都重新读取"""
    prompt_path = Path(__file__).parent / "docs" / "GAME_MASTER_PROMPT.md"
    return prompt_path.read_text(encoding="utf-8")


def get_active_conn() -> sqlite3.Connection:
    """
    获取当前激活的游戏数据库连接
    
    Returns:
        sqlite3.Connection: 当前游戏数据库连接
    
    Raises:
        RuntimeError: 无激活游戏时抛出异常
    """
    if _active_game_conn is None:
        raise RuntimeError("NO_ACTIVE_GAME")
    return _active_game_conn


def get_active_game_id() -> int | None:
    """获取当前激活的游戏ID"""
    return _active_game_id


# ── MCP Server 初始化 ──────────────────────────────────────

app = Server("psycho-street")


# ── 工具注册 ──────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[Tool]:
    """列出所有可用的 MCP 工具"""
    return [
        # ⚠️ 必须第一个调用的工具
        Tool(
            name="get_game_rules",
            description=(
                "【必须最先调用】获取《发疯华尔街》完整游戏规则与主持人行为指南。"
                "在执行任何其他操作（包括 new_game）之前，你必须先调用此工具，"
                "读取并内化其中的规则，之后严格按规则行事。"
            ),
            inputSchema={"type": "object", "properties": {}},
        ),

        # 会话管理工具
        Tool(
            name="new_game",
            description="创建新游戏实例",
            inputSchema={
                "type": "object",
                "properties": {
                    "display_name": {"type": "string", "description": "游戏名称"},
                    "starting_cash": {"type": "number", "description": "初始资金", "default": DEFAULT_STARTING_CASH},
                    "company_count": {"type": "integer", "description": "公司数量", "default": DEFAULT_COMPANY_COUNT},
                },
                "required": ["display_name"],
            },
        ),
        Tool(
            name="load_game",
            description="加载已存在的游戏",
            inputSchema={
                "type": "object",
                "properties": {
                    "game_id": {"type": "integer", "description": "游戏ID"},
                },
                "required": ["game_id"],
            },
        ),
        Tool(
            name="list_games",
            description="列出所有游戏会话",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="save_checkpoint",
            description="创建存档快照",
            inputSchema={
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "description": "存档备注", "default": ""},
                },
            },
        ),
        Tool(
            name="load_checkpoint",
            description="加载存档快照",
            inputSchema={
                "type": "object",
                "properties": {
                    "checkpoint_id": {"type": "integer", "description": "存档ID"},
                },
                "required": ["checkpoint_id"],
            },
        ),
        
        # 初始化工具
        Tool(
            name="init_player",
            description="初始化玩家",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "玩家名称"},
                    "starting_cash": {"type": "number", "description": "初始资金"},
                },
                "required": ["name", "starting_cash"],
            },
        ),
        Tool(
            name="init_companies",
            description="初始化公司与股票（可选：指定公司列表，不指定则从内容池随机抽取）",
            inputSchema={
                "type": "object",
                "properties": {
                    "companies": {
                        "type": "array",
                        "description": "公司列表（可选，不指定则从内容池随机抽取15家）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "industry_tag": {"type": "string"},
                                "description": {"type": "string"},
                            },
                            "required": ["name", "industry_tag", "description"],
                        },
                    },
                },
            },
        ),
        Tool(
            name="init_npcs",
            description="初始化公司NPC（可选：指定NPC列表，不指定则从名人池随机抽取）",
            inputSchema={
                "type": "object",
                "properties": {
                    "npcs": {
                        "type": "array",
                        "description": "NPC列表（可选，不指定则从名人池随机抽取）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "company_id": {"type": "integer"},
                                "name": {"type": "string"},
                                "role": {"type": "string"},
                            },
                            "required": ["company_id", "name", "role"],
                        },
                    },
                },
            },
        ),
        Tool(
            name="init_macro_events",
            description="初始化宏观事件",
            inputSchema={
                "type": "object",
                "properties": {
                    "total_turns": {"type": "integer", "description": "游戏总回合数", "default": DEFAULT_TOTAL_TURNS},
                },
            },
        ),
        Tool(
            name="init_macro_trends",
            description="初始化宏观趋势（持续性风向标）。由 LLM 传入趋势叙事，MCP 自动生成隐藏强度，涨跌均可",
            inputSchema={
                "type": "object",
                "properties": {
                    "trends": {
                        "type": "array",
                        "description": "趋势列表（建议 2~4 条，涵盖不同行业与方向）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name":         {"type": "string", "description": "趋势名称，如 'AI爆发期'"},
                                "description":  {"type": "string", "description": "完整背景叙事（100字以内），落库后每回合复用，保持前后一致"},
                                "industry_tag": {"type": ["string", "null"], "description": "受影响行业标签，null 表示全市场"},
                                "direction":    {"type": "string", "enum": ["bullish", "bearish", "mixed"], "description": "方向：bullish看涨 / bearish看跌 / mixed混沌"},
                                "start_turn":   {"type": "integer", "description": "开始生效回合，默认 1"},
                                "end_turn":     {"type": "integer", "description": "结束回合，-1 表示持续到游戏结束"},
                            },
                            "required": ["name", "description", "direction"],
                        },
                    },
                },
                "required": ["trends"],
            },
        ),
        Tool(
            name="init_market_prices",
            description="初始化市场价格",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="init_institutions",
            description="初始化 AI 机构（价值基金、做空基金、量化基金）。游戏开始时调用，生成 3-5 家独立博弈的 AI 机构",
            inputSchema={
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "机构数量，默认 4", "default": 4},
                },
            },
        ),

        # 回合推进工具
        Tool(
            name="advance_turn",
            description="【每回合必调】推进回合，整合意图处理与状态结算。时间前进，不可逆。",
            inputSchema={
                "type": "object",
                "properties": {
                    "story_log": {
                        "type": "string",
                        "description": "上回合剧情摘要（100字以内），用于记录剧情日志。首次调用填'游戏开始'，后续填上一回合发生的核心事件"
                    },
                    "intents": {
                        "type": "array",
                        "description": "玩家意图数组（无操作填 []）。每个 intent 必须包含 ap_type 字段",
                        "items": {
                            "type": "object",
                            "properties": {
                                "ap_type": {
                                    "type": "string",
                                    "enum": ["scheme_ap", "trade_ap", "work_ap"],
                                    "description": "行动力类型：scheme_ap=盘外招、trade_ap=交易、work_ap=打工"
                                },
                                "intent_type": {
                                    "type": "string",
                                    "description": "具体意图类型，如 post_online / bribe_npc / gather_intel / hire_investigator / spillover（蝴蝶效应）等"
                                },
                                "description": {
                                    "type": "string",
                                    "description": "玩家具体想做什么（自然语言）"
                                },
                                "feasibility_tier": {
                                    "type": "string",
                                    "enum": ["impossible", "hard", "normal", "easy", "trivial"],
                                    "description": "LLM 评估的现实可行性档位"
                                },
                                "execution_method": {
                                    "type": "string",
                                    "enum": ["self", "delegate"],
                                    "description": "执行方式：self=亲自动手，delegate=花钱雇人"
                                },
                                "estimated_cost": {
                                    "type": "number",
                                    "description": "预估成本（delegate 模式需要）"
                                },
                                "illegality_score": {
                                    "type": "integer",
                                    "description": "违法程度 1-10"
                                },
                                "target_stock_id": {
                                    "type": ["integer", "null"],
                                    "description": "目标股票 ID（若操作针对某公司）"
                                },
                                "target_npc_id": {
                                    "type": ["integer", "null"],
                                    "description": "目标 NPC ID（若操作针对某人）"
                                },
                                "action": {
                                    "type": "string",
                                    "enum": ["buy", "sell"],
                                    "description": "交易类型（仅 trade_ap 需要）"
                                },
                                "stock_id": {
                                    "type": "integer",
                                    "description": "股票 ID（仅 trade_ap 需要）"
                                },
                                "quantity": {
                                    "type": "integer",
                                    "description": "交易数量（仅 trade_ap 需要）"
                                },
                                "social_content_tone": {
                                    "type": "string",
                                    "enum": ["conspiracy", "populist", "academic", "underground"],
                                    "description": "社交内容基调（仅 post_online 需要）：conspiracy=阴谋论、populist=散户韭菜、academic=机构跟随者、underground=地下网络"
                                },
                                "sentiment_shift": {
                                    "type": "number",
                                    "description": "蝴蝶效应情绪偏移（-1.0 到 1.0），仅 spillover 类型使用"
                                },
                            },
                            "required": ["ap_type"],
                        },
                    },
                },
                "required": ["story_log", "intents"],
            },
        ),
        Tool(
            name="investigate_abnormal_movement",
            description="调查某股票的异常资金流动。玩家通过此工具可以探查暗网传言（rumor），了解机构建仓等隐藏信息。",
            inputSchema={
                "type": "object",
                "properties": {
                    "stock_id": {"type": "integer", "description": "目标股票 ID"},
                },
                "required": ["stock_id"],
            },
        ),
        Tool(
            name="get_state_snapshot",
            description="【纯只读】获取当前状态快照，不推进回合。用于新对话恢复上下文、查询状态、确认余额等。返回完整玩家状态、持仓、总净值、活跃趋势、最近5回合剧情。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="list_market",
            description="获取全市场股票看板，返回所有股票的当前价格、行业、以及玩家持仓情况（含未实现盈亏）",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="query_stock_price",
            description="查询单支股票价格及详情",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "股票名称或ID"},
                },
                "required": ["ticker"],
            },
        ),
        Tool(
            name="get_npc_logs",
            description="获取NPC交互日志",
            inputSchema={
                "type": "object",
                "properties": {
                    "npc_id": {"type": "integer", "description": "NPC ID"},
                    "limit": {"type": "integer", "description": "最多返回条数", "default": 10},
                },
                "required": ["npc_id"],
            },
        ),
        Tool(
            name="append_npc_log",
            description="追加NPC交互日志",
            inputSchema={
                "type": "object",
                "properties": {
                    "npc_id": {"type": "integer", "description": "NPC ID"},
                    "turn": {"type": "integer", "description": "当前回合数"},
                    "summary": {"type": "string", "description": "交互摘要（≤100字）"},
                },
                "required": ["npc_id", "turn", "summary"],
            },
        ),
        
        # 交易工具
        Tool(
            name="buy_stock",
            description="买入股票",
            inputSchema={
                "type": "object",
                "properties": {
                    "stock_id": {"type": "integer", "description": "股票ID"},
                    "quantity": {"type": "integer", "description": "买入数量"},
                },
                "required": ["stock_id", "quantity"],
            },
        ),
        Tool(
            name="sell_stock",
            description="卖出股票",
            inputSchema={
                "type": "object",
                "properties": {
                    "stock_id": {"type": "integer", "description": "股票ID"},
                    "quantity": {"type": "integer", "description": "卖出数量（-1表示全部）"},
                },
                "required": ["stock_id", "quantity"],
            },
        ),
        
        # 意图检定工具（已废弃，保留以兼容旧存档）
        Tool(
            name="evaluate_intents",
            description="【已废弃】请使用 advance_turn 的 intents 参数代替。此工具仅为兼容旧存档保留。",
            inputSchema={
                "type": "object",
                "properties": {
                    "intents": {
                        "type": "array",
                        "description": "意图数组（最多3条）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "ap_type": {
                                    "type": "string",
                                    "enum": ["scheme_ap", "trade_ap", "work_ap"],
                                    "description": "行动力类型"
                                },
                            },
                            "required": ["ap_type"],
                        },
                    },
                },
                "required": ["intents"],
            },
        ),
        
        # 打工系统工具
        Tool(
            name="apply_job",
            description="申请入职到某公司",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_id": {"type": "integer", "description": "目标公司ID"},
                    "position_level": {
                        "type": "string", 
                        "enum": ["entry", "middle", "high"],
                        "description": "申请的职位级别：entry=基层, middle=中层, high=高管",
                        "default": "entry"
                    },
                },
                "required": ["company_id"],
            },
        ),
        Tool(
            name="quit_job",
            description="从当前公司离职",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_job_info",
            description="查询当前工作状态",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="acquire_item",
            description="获取/购买物品（资产、黑料、凭证等）",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_name": {"type": "string", "description": "物品名称"},
                    "category_tag": {"type": "string", "description": "语义化标签：重资产/致命黑料/暗网凭证/收藏品"},
                    "description": {"type": "string", "description": "详细描述"},
                    "estimated_cost": {"type": "number", "description": "预估成本"},
                    "feasibility_tier": {
                        "type": "string",
                        "enum": ["impossible", "hard", "normal", "easy", "trivial"],
                        "description": "现实可行性档位",
                        "default": "normal"
                    },
                },
                "required": ["item_name", "category_tag", "description", "estimated_cost"],
            },
        ),
        Tool(
            name="update_item_status",
            description="修改物品的语义状态（存放地点、法律状态等）",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "物品ID"},
                    "new_status": {"type": "string", "description": "新状态描述，如'已存入瑞士银行'"},
                },
                "required": ["item_id", "new_status"],
            },
        ),
        Tool(
            name="consume_item",
            description="消耗/销毁/售出物品",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "物品ID"},
                    "cash_gained": {"type": "number", "description": "获得的现金（售出时）", "default": 0},
                    "reason": {"type": "string", "description": "消耗原因"},
                },
                "required": ["item_id"],
            },
        ),
        Tool(
            name="take_loan",
            description="用物品抵押借款",
            inputSchema={
                "type": "object",
                "properties": {
                    "collateral_item_id": {"type": "integer", "description": "抵押物ID"},
                    "loan_amount": {"type": "number", "description": "借款金额"},
                    "duration_turns": {"type": "integer", "description": "借款期限（回合数）"},
                },
                "required": ["collateral_item_id", "loan_amount", "duration_turns"],
            },
        ),
        Tool(
            name="repay_loan",
            description="偿还抵押借款",
            inputSchema={
                "type": "object",
                "properties": {
                    "debt_id": {"type": "integer", "description": "债务ID"},
                },
                "required": ["debt_id"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """执行 MCP 工具调用"""
    global _active_game_conn, _active_game_id
    
    try:
        # ── 规则获取（无需激活游戏，任何时候可调用）──────────────
        if name == "get_game_rules":
            return [TextContent(type="text", text=_load_game_master_prompt())]
        
        # ── 会话管理工具 ──────────────────────────────────────
        elif name == "new_game":
            result = session_tools.new_game(
                display_name=arguments["display_name"],
                starting_cash=arguments.get("starting_cash", DEFAULT_STARTING_CASH),
                company_count=arguments.get("company_count", DEFAULT_COMPANY_COUNT),
            )
            
            # 解析结果获取 game_id 并设置连接
            result_dict = json.loads(result)
            if "game_id" in result_dict:
                _active_game_id = result_dict["game_id"]
                session = global_db.get_game_session(_active_game_id)
                if session:
                    _active_game_conn = game_db.get_game_conn(session["db_path"])
            
            return [TextContent(type="text", text=result)]
        
        elif name == "load_game":
            result = session_tools.load_game(game_id=arguments["game_id"])
            
            # 解析结果并设置连接
            result_dict = json.loads(result)
            if "game_id" in result_dict:
                _active_game_id = result_dict["game_id"]
                session = global_db.get_game_session(_active_game_id)
                if session:
                    _active_game_conn = game_db.get_game_conn(session["db_path"])
            
            return [TextContent(type="text", text=result)]
        
        elif name == "list_games":
            result = session_tools.list_games()
            return [TextContent(type="text", text=result)]
        
        elif name == "save_checkpoint":
            tag = arguments.get("tag", "")
            
            if _active_game_conn is None or _active_game_id is None:
                return [TextContent(type="text", text=json.dumps({"error": "NO_ACTIVE_GAME"}))]
            
            # 获取当前回合
            current_turn = game_db.get_current_turn(_active_game_conn)
            
            # 创建快照文件
            session = global_db.get_game_session(_active_game_id)
            db_path = Path(session["db_path"])
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            checkpoint_path = db_path.parent / f"game_{_active_game_id}_turn_{current_turn}_{tag}.db"
            
            shutil.copy2(db_path, checkpoint_path)
            
            # 插入 GameCheckpoints 记录
            conn = global_db.get_global_conn()
            now = datetime.now().isoformat()
            cursor = conn.execute(
                """INSERT INTO GameCheckpoints 
                   (game_id, turn, tag, db_path, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (_active_game_id, current_turn, tag, str(checkpoint_path), now)
            )
            conn.commit()
            
            result = json.dumps({
                "checkpoint_id": cursor.lastrowid,
                "turn": current_turn,
                "db_path": str(checkpoint_path),
            })
            
            return [TextContent(type="text", text=result)]
        
        elif name == "load_checkpoint":
            checkpoint_id = arguments["checkpoint_id"]
            
            # 查询 checkpoint 信息
            conn = global_db.get_global_conn()
            checkpoint = conn.execute(
                "SELECT * FROM GameCheckpoints WHERE checkpoint_id=?",
                (checkpoint_id,)
            ).fetchone()
            
            if not checkpoint:
                return [TextContent(type="text", text=json.dumps({"error": "CHECKPOINT_NOT_FOUND"}))]
            
            if _active_game_id is None:
                return [TextContent(type="text", text=json.dumps({"error": "NO_ACTIVE_GAME"}))]
            
            # 关闭当前连接
            if _active_game_conn:
                _active_game_conn.close()
            
            # 复制快照到主游戏文件
            session = global_db.get_game_session(_active_game_id)
            main_db_path = Path(session["db_path"])
            checkpoint_path = Path(checkpoint["db_path"])
            
            shutil.copy2(checkpoint_path, main_db_path)
            
            # 重新打开连接
            _active_game_conn = game_db.get_game_conn(main_db_path)
            
            result = json.dumps({
                "success": True,
                "turn": checkpoint["turn"],
                "message": f"已加载存档：第{checkpoint['turn']}回合",
            })
            
            return [TextContent(type="text", text=result)]
        
        # ── 需要激活游戏的工具 ──────────────────────────────────────
        else:
            if _active_game_conn is None:
                # 尝试自动加载激活的游戏
                active_id = global_db.get_active_game_id()
                if active_id:
                    session = global_db.get_game_session(active_id)
                    if session and session["status"] == "active":
                        _active_game_id = active_id
                        _active_game_conn = game_db.get_game_conn(session["db_path"])
                else:
                    return [TextContent(type="text", text=json.dumps({"error": "NO_ACTIVE_GAME"}))]
            
            # ── 初始化工具 ──────────────────────────────────────
            if name == "init_player":
                result = init_tools.init_player(
                    conn=_active_game_conn,
                    name=arguments["name"],
                    starting_cash=arguments["starting_cash"],
                )
            
            elif name == "init_companies":
                companies = arguments.get("companies")
                result = init_tools.init_companies(
                    conn=_active_game_conn,
                    companies=companies,
                )
            
            elif name == "init_npcs":
                npcs = arguments.get("npcs")
                result = init_tools.init_npcs(
                    conn=_active_game_conn,
                    npcs=npcs,
                )
            
            elif name == "init_macro_events":
                result = init_tools.init_macro_events(
                    conn=_active_game_conn,
                    total_turns=arguments.get("total_turns", DEFAULT_TOTAL_TURNS),
                )
            
            elif name == "init_macro_trends":
                result = init_tools.init_macro_trends(
                    conn=_active_game_conn,
                    trends=arguments["trends"],
                )
            
            elif name == "init_market_prices":
                result = init_tools.init_market_prices(conn=_active_game_conn)

            elif name == "init_institutions":
                result = init_tools.init_institutions(
                    conn=_active_game_conn,
                    count=arguments.get("count", 4)
                )

            # ── 回合推进工具 ──────────────────────────────────────
            elif name == "advance_turn":
                story_log = arguments.get("story_log", "")
                intents = arguments.get("intents", [])
                result = turn_tools.tool_advance_turn(
                    conn=_active_game_conn,
                    story_log=story_log,
                    intents=intents
                )
                # 更新 global.db 中的回合数
                if _active_game_id:
                    current_turn = game_db.get_current_turn(_active_game_conn)
                    global_db.update_game_session(_active_game_id, current_turn)
            
            elif name == "get_state_snapshot":
                result = turn_tools.tool_get_state_snapshot(conn=_active_game_conn)
            
            elif name == "list_market":
                result = turn_tools.tool_list_market(conn=_active_game_conn)
            
            elif name == "query_stock_price":
                result = turn_tools.tool_query_stock_price(
                    conn=_active_game_conn,
                    ticker=arguments["ticker"],
                )
            
            elif name == "get_npc_logs":
                result = turn_tools.tool_get_npc_logs(
                    conn=_active_game_conn,
                    npc_id=arguments["npc_id"],
                    limit=arguments.get("limit", 10),
                )

            elif name == "investigate_abnormal_movement":
                result = turn_tools.tool_investigate_abnormal_movement(
                    conn=_active_game_conn,
                    stock_id=arguments["stock_id"],
                )

            elif name == "append_npc_log":
                result = turn_tools.tool_append_npc_log(
                    conn=_active_game_conn,
                    npc_id=arguments["npc_id"],
                    turn=arguments["turn"],
                    summary=arguments["summary"],
                )
            
            # ── 交易工具 ──────────────────────────────────────
            elif name == "buy_stock":
                result = trade_tools.tool_buy_stock(
                    conn=_active_game_conn,
                    stock_id=arguments["stock_id"],
                    quantity=arguments["quantity"],
                )
            
            elif name == "sell_stock":
                result = trade_tools.tool_sell_stock(
                    conn=_active_game_conn,
                    stock_id=arguments["stock_id"],
                    quantity=arguments["quantity"],
                )
            
            # ── 意图检定工具 ──────────────────────────────────────
            elif name == "evaluate_intents":
                result = intent_tools.format_evaluate_intents_response(
                    intent_tools.tool_evaluate_intents(
                        conn=_active_game_conn,
                        intents=arguments["intents"],
                    )
                )
            
            # ── 打工系统工具 ──────────────────────────────────────
            elif name == "apply_job":
                result = job_tools.tool_apply_job(
                    conn=_active_game_conn,
                    company_id=arguments["company_id"],
                    position_level=arguments.get("position_level", "entry"),
                )
            
            elif name == "quit_job":
                result = job_tools.tool_quit_job(conn=_active_game_conn)
            
            elif name == "get_job_info":
                result = job_tools.tool_get_job_info(conn=_active_game_conn)
            
            elif name == "acquire_item":
                current_turn = game_db.get_current_turn(_active_game_conn) if _active_game_conn else 1
                result = inventory_tools.tool_acquire_item(
                    conn=_active_game_conn,
                    current_turn=current_turn,
                    item_name=arguments["item_name"],
                    category_tag=arguments["category_tag"],
                    description=arguments["description"],
                    estimated_cost=arguments["estimated_cost"],
                    feasibility_tier=arguments.get("feasibility_tier", "normal"),
                )
            
            elif name == "update_item_status":
                result = inventory_tools.tool_update_item_status(
                    conn=_active_game_conn,
                    item_id=arguments["item_id"],
                    new_status=arguments["new_status"],
                )
            
            elif name == "consume_item":
                result = inventory_tools.tool_consume_item(
                    conn=_active_game_conn,
                    item_id=arguments["item_id"],
                    cash_gained=arguments.get("cash_gained", 0.0),
                    reason=arguments.get("reason", ""),
                )
            
            elif name == "take_loan":
                current_turn = game_db.get_current_turn(_active_game_conn) if _active_game_conn else 1
                result = inventory_tools.tool_take_loan(
                    conn=_active_game_conn,
                    current_turn=current_turn,
                    collateral_item_id=arguments["collateral_item_id"],
                    loan_amount=arguments["loan_amount"],
                    duration_turns=arguments["duration_turns"],
                )
            
            elif name == "repay_loan":
                result = inventory_tools.tool_repay_loan(
                    conn=_active_game_conn,
                    debt_id=arguments["debt_id"],
                )
            
            else:
                result = json.dumps({"error": "UNKNOWN_TOOL", "message": f"未知工具: {name}"})
            
            return [TextContent(type="text", text=result)]
    
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": "EXECUTION_ERROR", "message": str(e)})
        )]


# ── 启动服务器 ──────────────────────────────────────────────

async def run():
    """启动 MCP Server"""
    # 初始化 global.db
    global_db.get_global_conn()
    
    # 尝试自动加载激活的游戏（添加容错）
    try:
        active_id = global_db.get_active_game_id()
        if active_id:
            session = global_db.get_game_session(active_id)
            if session and session["status"] == "active":
                global _active_game_id, _active_game_conn
                _active_game_id = active_id
                _active_game_conn = game_db.get_game_conn(session["db_path"])
    except Exception as e:
        print(f"[警告] 自动加载游戏失败: {e}")
        # 清除无效的激活游戏ID
        global_db.set_active_game_id(None)
    
    # 启动 MCP Server
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(run())
