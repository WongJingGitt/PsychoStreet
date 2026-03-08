"""
游戏数值常量定义
所有可调整的游戏参数集中管理
"""

# ── 市场引擎参数 ─────────────────────────────────────────────
TREND_FACTOR    = 0.5    # momentum 每点对价格的影响系数
REVERT_FACTOR   = 0.05   # 均值回归每回合拉力（5%）
NOISE_FACTOR    = 0.02   # 随机噪声幅度（价格的2%）
DECAY_FACTOR    = 0.85   # momentum 每回合衰减系数
SCANDAL_THRESHOLD = 100  # 暴雷风险累积阈值

# ── V2.0 混沌市场引擎参数 ─────────────────────────────────
RETAIL_POWER = 0.05       # 散户情绪转化资金的乘数
SLIPPAGE_EXPONENT = 1.3   # 滑点指数 (1.0为线性，>1.0为非线性爆炸)
SENTIMENT_DECAY_RATE = 0.8  # 情绪每回合向 0 的自然衰减率
INST_VALUE_UNDERVALUED_THRESHOLD = 0.2  # 价值基金严重低估阈值
INST_VALUE_RISK_LIMIT = 0.3   # 价值基金止损线
INST_SHORT_SCANDAL_THRESHOLD = 80  # 做空基金建仓风险阈值
INST_QUANT_SENTIMENT_THRESHOLD = 0.3  # 量化基金追涨杀跌情绪阈值
INST_CAPITAL_FLOW_RATIO = 0.1  # 机构单次操作资金比例
VOLATILITY_MIN_LIQUIDITY_RATIO = 0.1  # 恐慌时最小流动性比例
FLOW_RATIO_CLAMP = 2.5  # 资金流动比例钳制上限

# ── 宏观趋势（MacroTrends）price_bias 随机范围 ────────────────
# LLM 传入 direction，MCP 在对应区间随机生成 price_bias（隐藏值）
# 单位：每回合注入的 momentum 量（与 TREND_FACTOR 联动影响价格）
TREND_BIAS_BULLISH = (0.4, 1.8)    # 看涨趋势：正偏置范围
TREND_BIAS_BEARISH = (-1.8, -0.4)  # 看跌趋势：负偏置范围
TREND_BIAS_MIXED   = (-1.0, 1.0)   # 混沌趋势：随机方向，出来啥是啥

# ── 交易异动监控（Pump & Dump 防护）────────────────────────────
TRADE_HEAT_LOW_RATIO  = 0.10   # 低档阈值：净交易量/流动性
TRADE_HEAT_MID_RATIO  = 0.20   # 中档阈值
TRADE_HEAT_HIGH_RATIO = 0.40   # 高档阈值
TRADE_HEAT_LOW_DELTA  = 2      # 低档热度增量
TRADE_HEAT_MID_DELTA  = 5      # 中档热度增量
TRADE_HEAT_HIGH_DELTA = 10     # 高档热度增量

# ── feasibility_tier 基础成功率乘数 ────────────────────────────
FEASIBILITY_MULTIPLIER = {
    "impossible": 0.0,
    "hard":       0.3,
    "normal":     0.7,
    "easy":       1.0,
    "trivial":    1.0,
}

# ── execution_method 修正系数 ──────────────────────────────
EXECUTION_MODIFIER = {
    "self":     0.75,   # 亲自动手：成功率打折
    "delegate": 1.00,   # 花钱雇人：正常成功率
}

# ── backfire 惩罚倍率 ──────────────────────────────────────
BACKFIRE_HEAT_SELF     = 2.0   # self 模式 sec_heat 惩罚倍率
BACKFIRE_HEAT_DELEGATE = 1.0   # delegate 模式惩罚倍率

# ── NPC 检定修正 ──────────────────────────────────────────
NPC_BRIBE_BASE       = 0.5    # 行贿基础成功率
RELATIONSHIP_DIVISOR = 100.0  # relationship 每点对成功率的影响除数

# ── Buff 加成 ──────────────────────────────────────────────
BUFF_SUCCESS_BONUS = 0.25  # 持有相关情报时的成功率加成

# ── 状态与惩罚 ────────────────────────────────────────────
SEC_HEAT_INVESTIGATE_THRESHOLD = 80   # 触发调查的热度阈值
SEC_HEAT_ARREST_THRESHOLD      = 100  # 触发逮捕的热度阈值
SEC_HEAT_ARREST_PROB           = 0.8  # 达到100时的逮捕概率

DELUSION_TIER_LOW    = 20   # 妄想度低档
DELUSION_TIER_MID    = 50   # 妄想度中档
DELUSION_TIER_HIGH   = 80   # 妄想度高档

# ── 打工系统 ──────────────────────────────────────────────
SALARY_BY_LEVEL = {
    range(1, 4):  8_000,    # Level 1-3: 月薪 8000
    range(4, 7):  20_000,   # Level 4-6: 月薪 20000
    range(7, 99): 60_000,   # Level 7+: 月薪 60000
}
JOB_LEVEL_THRESHOLD = 20   # job_performance 达到此值触发晋升检定
MAX_JOB_LEVEL       = 10   # CEO 级别

# ── 社交影响力 ────────────────────────────────────────────
SOCIAL_REACH_GROW_RATE   = 0.05  # 高能见度操作成功后的粉丝增长率
SOCIAL_REACH_BASE_GROW   = 100   # 每次成功的基础粉丝增量
SOCIAL_REACH_POST_GROW   = 50    # 发帖的基础粉丝增量
AUDIENCE_TAG_DRIFT_STEP  = 0.20  # 每次相关操作的标签权重增量
MAX_AUDIENCE_TAGS        = 3     # 最多同时持有标签数

TONE_TO_TAG = {
    "conspiracy":  "阴谋论粉丝",
    "populist":    "散户韭菜",
    "academic":    "机构跟随者",
    "underground": "地下网络",
}

# ── 妄想度 ────────────────────────────────────────────────
DELUSION_INCREMENT_MINOR  = 5   # 轻微破坏第四面墙
DELUSION_INCREMENT_MAJOR  = 15  # 严重注入指令

# 妄想度区间阈值
DELUSION_TIER_LOW  = 20   # 正常区间上限
DELUSION_TIER_MID  = 50   # 可疑区间上限
DELUSION_TIER_HIGH = 80   # 警告区间上限

# 妄想度区间效果描述
DELUSION_TIER_EFFECTS = {
    "normal": {  # 0~20
        "range": (0, 20),
        "npc_reaction": "正常",
        "penalty": None,
        "description": "一切正常，NPC对你没有特别的看法"
    },
    "suspicious": {  # 21~50
        "range": (21, 50),
        "npc_reaction": "觉得你有点奇怪",
        "penalty": {"fame_delta": -5},
        "description": "NPC开始觉得你行为异常，部分外交操作可信度下降"
    },
    "warning": {  # 51~80
        "range": (51, 80),
        "npc_reaction": "普遍认为你精神不稳定",
        "penalty": {"fame_delta": -15, "skip_turns": 1},
        "description": "高级NPC拒绝接触，部分NPC主动向SEC举报，触发心理评估事件"
    },
    "psychiatric": {  # 81~100
        "range": (81, 100),
        "npc_reaction": "华尔街疯子",
        "penalty": {"fame_delta": -30, "skip_turns": 3, "social_reach_mult": 0.5},
        "description": "强制送入精神病院，跳过3回合，fame清零，但地下网络权重飙升"
    }
}

# ── NpcInteractionLog 上限 ───────────────────────────────
NPC_LOG_MAX_RECORDS = 20

# ── 快照 Top Mover 数量 ──────────────────────────────────
SNAPSHOT_TOP_MOVER_COUNT = 3


# ── NPC 特质池（初始化时随机选择）──────────────────────────────
WEAKNESS_POOL = [
    "贪财",
    "好色",
    "爱慕虚荣",
    "恐惧丑闻",
    "家庭压力大",
    "赌博成瘾",
    "政治野心",
]

SECRET_POOL = [
    "参与财务造假",
    "有不公开的情人",
    "与竞争对手有私下来往",
    "挪用公款",
    "持有非法资产",
    "与黑市有关联",
]

PREFERENCE_POOL = [
    "高尔夫球",
    "红酒收藏",
    "佛教信仰",
    "极度注重隐私",
    "喜欢被奉承",
    "崇拜成功人士",
    "痛恨媒体曝光",
]


# ── 公司基本面描述模板（初始化时随机选择）────────────────────
FUNDAMENTALS_TEMPLATES = [
    "财务健康，现金流充裕，管理层稳定",
    "高负债，依赖再融资，基本面偏弱",
    "核心技术壁垒强，但市场渗透率低",
    "依赖单一大客户，客户流失风险高",
    "快速扩张期，亏损但增长强劲",
    "成熟行业现金牛，增长停滞",
    "财务数据存在美化嫌疑，内部知情人看空",
    "隐藏的政府关系提供稳定订单",
]


# ── 默认游戏配置 ────────────────────────────────────────
DEFAULT_STARTING_CASH = 100_000.0  # 默认初始资金
DEFAULT_COMPANY_COUNT = 15         # 默认公司数量（初始股票数）
DEFAULT_TOTAL_TURNS   = 200        # 默认游戏总回合数

# ── 市场动态管理 ──────────────────────────────────────────
MARKET_MIN_STOCKS     = 10         # 大盘最少股票数（低于此数退市机制暂停）
MARKET_MAX_STOCKS     = 30         # 大盘最多股票数（达到此数IPO暂停）

# ── 退市机制 ──────────────────────────────────────────────
DELISTING_CONSECUTIVE_DECLINE = 8  # 连续下跌回合数触发退市
DELISTING_SEVERE_DECLINE_TURNS = 3 # 连续暴跌回合数触发退市
DELISTING_SEVERE_DECLINE_THRESHOLD = 0.20  # 暴跌阈值（单回合跌幅）
DELISTING_CRASH_THRESHOLD = 0.50   # 一次性暴跌阈值（单回合跌幅）
DELISTING_MIN_PRICE = 1.0          # 最低价格（低于此价格触发退市）

# ── IPO 机制 ──────────────────────────────────────────────
IPO_CHECK_INTERVAL_MIN = 5         # IPO 检测最小间隔（回合）
IPO_CHECK_INTERVAL_MAX = 10        # IPO 检测最大间隔（回合）
IPO_BASE_PROBABILITY = 0.3         # IPO 基础概率
IPO_HOT_INDUSTRY_MULTIPLIER = 2.0  # 热门行业IPO概率倍数
IPO_INITIAL_PRICE_MIN = 10.0       # IPO 初始价格下限
IPO_INITIAL_PRICE_MAX = 50.0       # IPO 初始价格上限

# 核心行业配置（用于初始化和IPO）
CORE_INDUSTRIES = {
    "科技": {"min_count": 3, "tags": ["AI", "芯片", "软件", "互联网"]},
    "金融": {"min_count": 2, "tags": ["银行", "证券", "保险"]},
    "消费": {"min_count": 2, "tags": ["零售", "餐饮", "电商"]},
    "医药": {"min_count": 2, "tags": ["制药", "医疗器械", "生物科技"]},
    "能源": {"min_count": 2, "tags": ["新能源", "传统能源", "电力"]},
    "地产": {"min_count": 2, "tags": ["房地产开发", "物业管理"]},
    "制造": {"min_count": 2, "tags": ["汽车", "机械", "电子制造"]},
}


# ── M3: 延时事件系统 ──────────────────────────────────────
EVENT_LEAK_PROBABILITY = 0.05     # 消息泄露概率（每回合每事件）
MAX_SCHEDULED_EVENTS   = 10       # 玩家同时进行的延时事件上限

# 延时事件类型与默认持续时间
EVENT_TYPE_DURATION = {
    "hire_investigator": 2,       # 雇私家侦探：2回合
    "bribe_npc": 1,               # 贿赂NPC：即时或1回合
    "arrange_meeting": 2,         # 安排会面：2回合
    "major_scheme": 4,            # 重大策划：4回合
    "underground_loan": 1,        # 地下钱庄借贷：即时
}


# ── M3: 监狱与破产系统 ────────────────────────────────────
# 监狱专属NPC池
PRISON_NPC_POOL = [
    {"name": "老张", "role": "白领犯罪导师", "trait": "金融犯罪前科"},
    {"name": "黑龙", "role": "地下网络大佬", "trait": "黑市渠道"},
    {"name": "阿强", "role": "黑帮线人", "trait": "暴力催收"},
    {"name": "眼镜王", "role": "内幕交易老手", "trait": "情报网络"},
    {"name": "疯子刘", "role": "精神病院常客", "trait": "疯子圈情报"},
]

# 破产状态底层打工薪资
BANKRUPTCY_SALARY = 2_000  # 每月2000元

# 地下钱庄利率
UNDERGROUND_LOAN_INTEREST = 0.15  # 借款利息15%/回合
UNDERGROUND_LOAN_DEADLINE = 5     # 还款期限（回合）


# ── M3: 特殊结局触发阈值 ────────────────────────────────────
ENDING_THRESHOLDS = {
    "best_employee": {  # 年度最佳员工
        "job_level": 10,
        "job_performance": 100,
        "description": "在对家公司一路晋升为CEO"
    },
    "public_enemy": {  # 公敌
        "sec_heat": 100,
        "fame": 0,
        "description": "成为全球头号通缉经济犯"
    },
    "retire": {  # 归隐田园
        "cash": 1_000_000,
        "sec_heat": 0,
        "fame": 0,
        "description": "赚到第一桶金后主动金盆洗手"
    },
    "puppet_master": {  # 幕后黑手
        "fame_max": 20,
        "sec_heat_max": 20,
        "portfolio_value": 5_000_000,
        "description": "保持极低声望与热度，悄悄操控市场"
    },
    "wall_street_madman": {  # 华尔街疯子
        "delusion_level": 81,
        "description": "妄想度达到81+，被送入精神病院"
    },
    "underground_emperor": {  # 地下皇帝
        "jail_turns_total": 20,  # 累计坐牢20回合
        "underground_network_weight": 3.0,
        "description": "通过监狱人脉控制地下生态"
    },
    "market_collapse": {  # 市场崩溃
        "trigger_type": "special_event",
        "description": "通过影响力触发全球经济崩溃事件"
    }
}


# ── M3: ActionLog 配置 ─────────────────────────────────────
ACTIONLOG_MAX_LENGTH = 200      # 每条日志最大字数
ACTIONLOG_MAX_RECORDS = 100     # 最多保留100条记录
