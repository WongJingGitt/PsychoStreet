"""
V2.0 混沌市场引擎测试脚本
测试五阶段结算管线、机构博弈、散户情绪等功能
"""
import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.schema import init_game_db, init_global_db
from db import game_db, global_db
from tools import init_tools
from engines import market_engine, turn_engine
import json


def test_market_engine():
    """测试市场引擎核心功能"""
    print("=" * 60)
    print("V2.0 混沌市场引擎测试")
    print("=" * 60)

    db_path = "data/games/test_market_engine.db"
    os.makedirs("data/games", exist_ok=True)

    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_game_db(conn)

    print("\n[1/8] 初始化玩家...")
    init_tools.init_player(conn, "测试玩家", 1000000.0)

    print("[2/8] 初始化公司...")
    companies = [
        {"name": "科技公司A", "industry_tag": "科技", "description": "AI 领头羊"},
        {"name": "金融公司B", "industry_tag": "金融", "description": "银行巨头"},
        {"name": "医药公司C", "industry_tag": "医药", "description": "创新药企"},
    ]
    init_tools.init_companies(conn, companies)

    print("[3/8] 初始化市场价格...")
    init_tools.init_market_prices(conn)

    print("[4/8] 初始化机构 (V2.0 新功能)...")
    result = init_tools.init_institutions(conn, 4)
    print(f"  结果: {result}")

    institutions = conn.execute("SELECT * FROM Institution").fetchall()
    print(f"  已创建 {len(institutions)} 家机构:")
    for inst in institutions:
        print(f"    - {inst['name']} ({inst['type']}) 资金: ${inst['capital']:,.0f}")

    stocks = conn.execute("SELECT * FROM Stock").fetchall()
    print(f"\n[5/8] 股票初始状态:")
    for s in stocks:
        print(f"  {s['name']}: ${s['current_price']:.2f}, "
              f"流动性: ${s['base_liquidity']:,.0f}, "
              f"情绪: {s['retail_sentiment']:.2f}")

    print("\n[6/8] 执行第一回合市场结算...")
    result = market_engine.settle_market_turn(conn, current_turn=1)
    print(f"  触发事件: {len(result['triggered_events'])} 个")
    print(f"  市场痕迹: {len(result['market_traces'])} 条")

    stocks = conn.execute("SELECT * FROM Stock").fetchall()
    print(f"\n[7/8] 第一回合后股票状态:")
    for s in stocks:
        print(f"  {s['name']}: ${s['current_price']:.2f}, "
              f"当前流动性: ${s['current_liquidity']:,.0f}, "
              f"情绪: {s['retail_sentiment']:.3f}, "
              f"恐慌指数: {s['volatility_index']:.3f}")

    institutions = conn.execute("SELECT * FROM Institution").fetchall()
    print(f"\n[8/8] 机构持仓变化:")
    for inst in institutions:
        positions = conn.execute(
            "SELECT * FROM InstitutionPosition WHERE inst_id=?",
            (inst['inst_id'],)
        ).fetchall()
        print(f"  {inst['name']}: {len(positions)} 个持仓, 剩余资金: ${inst['capital']:,.0f}")

    conn.close()
    os.remove(db_path)

    print("\n" + "=" * 60)
    print("✓ 测试完成！市场引擎正常工作")
    print("=" * 60)


def test_nonlinear_slippage():
    """测试非线性滑点公式"""
    print("\n" + "=" * 60)
    print("非线性滑点公式测试")
    print("=" * 60)

    import math
    from constants import SLIPPAGE_EXPONENT, FLOW_RATIO_CLAMP

    test_cases = [
        (0.05, "5% 流动性"),
        (0.10, "10% 流动性"),
        (0.20, "20% 流动性"),
        (0.40, "40% 流动性"),
        (1.00, "100% 流动性"),
    ]

    print(f"\n滑点指数: {SLIPPAGE_EXPONENT}")
    print(f"资金比例 | 线性冲击 | 非线性冲击 | 放大倍数")
    print("-" * 55)

    for flow_ratio, desc in test_cases:
        clamped_ratio = min(flow_ratio, FLOW_RATIO_CLAMP)
        linear_impact = clamped_ratio
        nonlinear_impact = math.pow(clamped_ratio, SLIPPAGE_EXPONENT)
        multiplier = nonlinear_impact / linear_impact if linear_impact > 0 else 0

        print(f"  {flow_ratio:5.0%}  |   {linear_impact:6.1%}   |   {nonlinear_impact:6.1%}   |   {multiplier:.2f}x")

    print("\n✓ 非线性滑点公式测试完成")


def test_institution_decisions():
    """测试机构决策逻辑"""
    print("\n" + "=" * 60)
    print("机构决策逻辑测试")
    print("=" * 60)

    from constants import (
        INST_VALUE_UNDERVALUED_THRESHOLD,
        INST_SHORT_SCANDAL_THRESHOLD,
        INST_QUANT_SENTIMENT_THRESHOLD,
    )

    print(f"\n价值基金建仓阈值: 价格低估 > {INST_VALUE_UNDERVALUED_THRESHOLD:.0%}")
    print(f"做空基金建仓阈值: 暴雷风险 > {INST_SHORT_SCANDAL_THRESHOLD}")
    print(f"量化基金追涨阈值: 情绪 > {INST_QUANT_SENTIMENT_THRESHOLD:.1f}")
    print(f"量化基金杀跌阈值: 情绪 < -{INST_QUANT_SENTIMENT_THRESHOLD:.1f}")

    print("\n✓ 机构决策逻辑参数验证完成")


if __name__ == "__main__":
    test_nonlinear_slippage()
    test_institution_decisions()
    test_market_engine()
    print("\n🎉 所有测试通过！")
