"""
数据库 Schema 定义
包含 global.db 和 game_{id}.db 的所有 CREATE TABLE 语句
"""

# ───────────────────────────────────────────────────────
# global.db - 游戏实例管理数据库
# ───────────────────────────────────────────────────────

GLOBAL_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS GameSessions (
    game_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name  TEXT    NOT NULL,
    db_path       TEXT    NOT NULL UNIQUE,
    created_at    TEXT    NOT NULL,
    last_played_at TEXT   NOT NULL,
    turn          INTEGER NOT NULL DEFAULT 0,
    status        TEXT    NOT NULL DEFAULT 'active'
                          CHECK(status IN ('active','ended','abandoned'))
);

CREATE TABLE IF NOT EXISTS GameCheckpoints (
    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id       INTEGER NOT NULL REFERENCES GameSessions(game_id),
    turn          INTEGER NOT NULL,
    tag           TEXT    NOT NULL DEFAULT '',
    db_path       TEXT    NOT NULL UNIQUE,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS Settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


# ───────────────────────────────────────────────────────
# game_{id}.db - 单局游戏数据库
# ───────────────────────────────────────────────────────

GAME_DB_SCHEMA = """
-- 玩家信息表
CREATE TABLE IF NOT EXISTS Player (
    id                    INTEGER PRIMARY KEY DEFAULT 1,
    cash                  REAL    NOT NULL DEFAULT 0.0,
    fame                  INTEGER NOT NULL DEFAULT 0,
    followers             INTEGER NOT NULL DEFAULT 0,
    social_reach          INTEGER NOT NULL DEFAULT 0,
    audience_tags         TEXT    NOT NULL DEFAULT '[]',
    sec_heat              INTEGER NOT NULL DEFAULT 0,
    jail_turns_left       INTEGER NOT NULL DEFAULT 0,
    in_bankruptcy         INTEGER NOT NULL DEFAULT 0,
    current_job_company_id INTEGER,
    job_level             INTEGER NOT NULL DEFAULT 0,
    job_performance       INTEGER NOT NULL DEFAULT 0,
    delusion_level        INTEGER NOT NULL DEFAULT 0
);

-- 股票/公司表
CREATE TABLE IF NOT EXISTS Stock (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    name                    TEXT    NOT NULL,
    industry_tag            TEXT    NOT NULL,
    description             TEXT    NOT NULL DEFAULT '',
    current_price           REAL    NOT NULL,
    hidden_fundamentals     TEXT    NOT NULL DEFAULT '',
    hidden_fundamental_value REAL   NOT NULL,
    hidden_momentum         REAL    NOT NULL DEFAULT 0.0,
    hidden_liquidity        REAL    NOT NULL,
    hidden_pr_defense       INTEGER NOT NULL DEFAULT 50,
    hidden_scandal_risk     INTEGER NOT NULL DEFAULT 0,
    is_revealed             INTEGER NOT NULL DEFAULT 0,
    is_delisted             INTEGER NOT NULL DEFAULT 0,
    delisting_risk          INTEGER NOT NULL DEFAULT 0,
    consecutive_decline_turns INTEGER NOT NULL DEFAULT 0,
    last_turn_price         REAL    NOT NULL DEFAULT 0.0,
    listed_turn             INTEGER NOT NULL DEFAULT 0,
    base_liquidity          REAL    NOT NULL DEFAULT 1000000.0,
    current_liquidity      REAL    NOT NULL DEFAULT 1000000.0,
    retail_sentiment        REAL    NOT NULL DEFAULT 0.0,
    volatility_index        REAL    NOT NULL DEFAULT 0.0
);

-- 公司NPC表
CREATE TABLE IF NOT EXISTS CompanyNPC (
    npc_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id              INTEGER REFERENCES Stock(id),
    name                    TEXT    NOT NULL,
    role                    TEXT    NOT NULL,
    npc_type                TEXT    NOT NULL DEFAULT 'executive'
                          CHECK(npc_type IN ('executive', 'celebrity', 'politician')),
    influence_power         INTEGER NOT NULL DEFAULT 0,
    bribe_resistance        INTEGER NOT NULL DEFAULT 50,
    alertness               INTEGER NOT NULL DEFAULT 30,
    relationship_with_player INTEGER NOT NULL DEFAULT 0,
    hidden_traits           TEXT    NOT NULL DEFAULT '{}'
);

-- NPC交互日志表
CREATE TABLE IF NOT EXISTS NpcInteractionLog (
    log_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id   INTEGER NOT NULL REFERENCES CompanyNPC(npc_id),
    turn     INTEGER NOT NULL,
    summary  TEXT    NOT NULL
);

-- 玩家持仓表
CREATE TABLE IF NOT EXISTS Portfolio (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id    INTEGER NOT NULL DEFAULT 1,
    stock_id     INTEGER NOT NULL REFERENCES Stock(id),
    quantity     INTEGER NOT NULL DEFAULT 0,
    avg_cost     REAL    NOT NULL DEFAULT 0.0,
    UNIQUE(player_id, stock_id)
);

-- 玩家情报Buff表
CREATE TABLE IF NOT EXISTS PlayerBuffs (
    buff_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id         INTEGER NOT NULL DEFAULT 1,
    buff_type         TEXT    NOT NULL,
    related_entity_id INTEGER,
    data              TEXT    NOT NULL DEFAULT '{}',
    duration_turns    INTEGER NOT NULL DEFAULT -1
);

-- 宏观趋势表（持续性风向，正负均可）
CREATE TABLE IF NOT EXISTS MacroTrends (
    trend_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    description  TEXT    NOT NULL DEFAULT '',
    industry_tag TEXT,
    direction    TEXT    NOT NULL DEFAULT 'bullish'
                         CHECK(direction IN ('bullish','bearish','mixed')),
    price_bias   REAL    NOT NULL,
    start_turn   INTEGER NOT NULL DEFAULT 1,
    end_turn     INTEGER NOT NULL DEFAULT -1,
    is_active    INTEGER NOT NULL DEFAULT 1
);

-- 宏观事件表
CREATE TABLE IF NOT EXISTS MacroEvents (
    event_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_turn          INTEGER NOT NULL,
    trigger_probability   REAL    NOT NULL DEFAULT 0.0,
    industry_tag          TEXT,
    price_impact_multiplier REAL  NOT NULL DEFAULT 1.0,
    description_template  TEXT    NOT NULL,
    is_triggered          INTEGER NOT NULL DEFAULT 0
);

-- 延时事件表
CREATE TABLE IF NOT EXISTS ScheduledEvents (
    event_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id      INTEGER NOT NULL DEFAULT 1,
    event_type     TEXT    NOT NULL,
    target_id      INTEGER,
    turns_remaining INTEGER NOT NULL,
    status         TEXT    NOT NULL DEFAULT 'pending'
                           CHECK(status IN ('pending','triggered','leaked','cancelled')),
    context        TEXT    NOT NULL DEFAULT '{}'
);

-- 行动日志表
CREATE TABLE IF NOT EXISTS ActionLog (
    log_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    turn      INTEGER NOT NULL,
    summary   TEXT    NOT NULL
);

-- 机构表（AI 实体）
CREATE TABLE IF NOT EXISTS Institution (
    inst_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT    NOT NULL,
    type              TEXT    NOT NULL DEFAULT 'value'
                      CHECK(type IN ('value', 'hedge_short', 'quant')),
    capital           REAL    NOT NULL DEFAULT 10000000.0,
    risk_tolerance    REAL    NOT NULL DEFAULT 0.5,
    status            TEXT    NOT NULL DEFAULT 'active'
                      CHECK(status IN ('active', 'bankrupt'))
);

-- 机构持仓表
CREATE TABLE IF NOT EXISTS InstitutionPosition (
    pos_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    inst_id     INTEGER NOT NULL REFERENCES Institution(inst_id),
    stock_id    INTEGER NOT NULL REFERENCES Stock(id),
    position_type TEXT  NOT NULL DEFAULT 'long'
                     CHECK(position_type IN ('long', 'short')),
    volume_usd  REAL    NOT NULL DEFAULT 0.0,
    avg_cost    REAL    NOT NULL DEFAULT 0.0,
    UNIQUE(inst_id, stock_id, position_type)
);

-- 市场痕迹表
CREATE TABLE IF NOT EXISTS MarketTrace (
    trace_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    turn        INTEGER NOT NULL,
    stock_id    INTEGER REFERENCES Stock(id),
    trace_type  TEXT    NOT NULL
                 CHECK(trace_type IN ('broadcast', 'rumor')),
    content     TEXT    NOT NULL
);

-- 游戏元数据表
CREATE TABLE IF NOT EXISTS GameMeta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def init_global_db(conn):
    """
    初始化 global.db 的所有表
    
    Args:
        conn: sqlite3.Connection 对象
    """
    cursor = conn.cursor()
    cursor.executescript(GLOBAL_DB_SCHEMA)
    # 插入默认设置项
    cursor.execute(
        "INSERT OR IGNORE INTO Settings (key, value) VALUES ('active_game_id', NULL)"
    )
    conn.commit()


def init_game_db(conn):
    """
    初始化 game_{id}.db 的所有表
    
    Args:
        conn: sqlite3.Connection 对象
    """
    cursor = conn.cursor()
    cursor.executescript(GAME_DB_SCHEMA)
    conn.commit()
