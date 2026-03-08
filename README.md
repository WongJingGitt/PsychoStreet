# 《发疯华尔街》(Psycho Street)

基于大语言模型（LLM）与 MCP 架构的单人文字模拟经营游戏。

## 游戏简介

玩家扮演一名初入股市的散户，通过常规交易和各种离经叛道的"盘外招"积累财富，最终成为能撼动市场的资本巨鳄，或是沦为身败名裂的阶下囚。

### 核心特色

- **黑色幽默叙事**：体验因果报应、啼笑皆非的蝴蝶效应
- **高自由度策略**：任何异想天开的操作都能被系统解析并产生合理（或荒诞）的结果
- **信息不对称博弈**：在隐藏属性与宏观事件共同构成的市场中，挖掘信息差是核心乐趣
- **解压与发泄**：提供虚拟世界中"发疯"的渠道

## V2.0 混沌市场引擎 (Chaos Entity Market Engine)

**全新升级的市场模拟系统**，彻底废弃"静态流动性+线性公式"的旧模型，打造一个"活着的、有情绪的、多方实体博弈"的深海生态系统：

### 核心特性

| 特性 | 说明 |
|------|------|
| **非线性滑点** | 价格冲击呈指数级增长：`(资金/流动性)^1.3` |
| **动态流动性** | 恐慌时流动性收缩至10%，少量抛单引发踩踏 |
| **AI机构博弈** | Value(价值)、Short(做空)、Quant(量化)三类机构独立决策 |
| **蝴蝶效应** | 玩家闲聊→情绪偏移→市场波动 |
| **暗网情报** | rumor(隐藏) vs broadcast(公开)双层信息机制 |

### 五阶段结算管线

```
Phase 1: 注意力溢出 → Phase 2: 机构决策 → Phase 3: 流动性计算
    → Phase 4: 非线性价格 → Phase 5: 级联清算
```

## 技术架构

### LLM / MCP 双层职责

| 职责 | 承担方 | 说明 |
|------|--------|------|
| 自然语言理解 | LLM | 解析玩家自由输入 |
| 现实可行性评估 | LLM | 依据世界知识进行分档评估 |
| 叙事渲染 | LLM | 将结算结果渲染为剧情、新闻 |
| 数值裁决 | MCP | 掷骰子、概率计算 |
| 数据持久化 | MCP | 读写 SQLite 数据库 |
| 事件管理 | MCP | 延时事件与状态管理 |

### 核心系统

- **市场模拟引擎 (V2.0)**：非线性滑点、机构博弈、散户情绪、蝴蝶效应
- **盘外招系统**：自由度极高的操作，通过现实锚定评估
- **NPC 交互系统**：隐藏特质刺探、关系值累积
- **三轴声望体系**：圈内声望 + 粉丝量 + 受众画像
- **破产与监狱闭环**：失败不是终点，是新玩法的入口

## 项目结构

```
PsychoStreet/
├── main.py               # MCP Server 入口
├── db/
│   ├── schema.py         # 数据库表结构定义
│   ├── global_db.py      # global.db 管理
│   └── game_db.py        # game_{id}.db 管理
├── engines/
│   ├── turn_engine.py    # 回合推进主流程
│   ├── market_engine.py  # V2.0 混沌市场引擎
│   ├── intent_engine.py  # 意图检定
│   └── state_engine.py   # 状态与惩罚
├── tools/
│   ├── session_tools.py  # 游戏会话管理
│   ├── init_tools.py     # 游戏初始化 (含 init_institutions)
│   ├── turn_tools.py     # 回合推进工具 (含 investigate_abnormal_movement)
│   └── trade_tools.py    # 股票交易工具
├── migrations/           # 数据迁移脚本
│   ├── migrate_v2_market.py      # V2.0 市场引擎迁移
│   └── migrate_add_ipo_fields.py # IPO 字段迁移
├── tests/               # 测试脚本
│   ├── test_comprehensive.py     # 综合深度测试
│   ├── test_institutions.py     # 机构测试
│   └── test_market_regulation.py # 市场调节测试
├── docs/                # 设计文档
│   ├── GDD.md           # 游戏设计文档
│   ├── MARKET_ENGINE.md # V2.0 引擎设计
│   └── TECH_SPEC.md     # 技术规范
├── constants.py          # 所有数值常量
└── requirements.txt     # 项目依赖
```

## 安装与运行

### 环境要求

- Python >= 3.11
- MCP SDK

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动 MCP Server

```bash
python main.py
```

### 在 Claude Desktop 中配置

编辑 Claude Desktop 配置文件，添加：

```json
{
  "mcpServers": {
    "psycho-street": {
      "command": "python",
      "args": ["C:/path/to/PsychoStreet/main.py"]
    }
  }
}
```

## 快速开始

### 1. 创建新游戏

```
调用 new_game 工具，传入游戏名称和初始资金
```

### 2. 初始化游戏世界 (V2.0)

```
依次调用：
- init_player: 创建玩家角色
- init_companies: 生成公司（由 LLM 提供公司名称和简介）
- init_npcs: 生成 NPC（可选）
- init_macro_events: 生成宏观事件
- init_macro_trends: 生成宏观趋势
- init_market_prices: 设定初始股价
- init_institutions: 初始化 AI 机构 (V2.0 新增)
```

### 3. 开始游戏

```
调用 advance_turn 推进回合，获取状态快照
LLM 基于快照渲染开盘新闻
玩家通过自然语言输入指令
LLM 拆解为意图数组并提交 MCP 检定

V2.0 新增意图类型：
- spillover: 蝴蝶效应（玩家闲聊影响市场情绪）
```

## V2.0 新增工具

| 工具 | 说明 |
|------|------|
| `init_institutions` | 初始化 AI 机构（价值/做空/量化） |
| `investigate_abnormal_movement` | 调查股票异常资金流动（获取 rumor） |

## 测试

### 运行测试

```bash
# 综合测试（推荐）
python tests/test_comprehensive.py

# 机构专项测试
python tests/test_institutions.py

# 市场调节测试
python tests/test_market_regulation.py
```

### 数据迁移

```bash
# 迁移旧存档到 V2.0
python migrations/migrate_v2_market.py
```

## 开发状态

### ✅ M1 - 核心数据流（已完成）

- 数据库 Schema 定义
- 游戏实例管理
- 市场模拟引擎
- 状态快照构建
- 基础交易系统

### ✅ M2 - 盘外招系统（已完成）

- 意图检定引擎
- NPC 交互系统
- 情报与 Buff 系统

### ✅ M3 - 完整体验（已完成）

- 延时事件系统
- 打工系统
- 破产与监狱闭环
- 特殊结局系统

### ✅ V2.0 - 混沌市场引擎（已完成）

- 非线性滑点公式
- AI 机构实体 (Value/Short/Quant)
- 散户情绪传导
- 蝴蝶效应机制
- 暗网情报系统
- 流动性干涸与级联清算

## 核心设计原则

1. **现实锚定**：LLM 首先评估操作的现实可行性
2. **数值隔离**：隐藏属性对 LLM 完全不可见
3. **智能过滤**：状态快照从 50 支股票压缩到 4~8 支
4. **失败即玩法**：破产和监狱是新路线的入口
5. **信息分层**：rumor(隐藏) vs broadcast(公开)

## 文档

- [游戏设计文档 (GDD.md)](./docs/GDD.md) - 完整的游戏设计理念与玩法机制
- [V2.0 引擎设计 (MARKET_ENGINE.md)](./docs/MARKET_ENGINE.md) - 混沌市场引擎详细设计
- [技术开发规范 (TECH_SPEC.md)](./docs/TECH_SPEC.md) - 详细的实现规范与开发指南

## 许可证

MIT License

## 致谢

本项目采用 MCP (Model Context Protocol) 架构，感谢 Anthropic 提供的 MCP SDK。
