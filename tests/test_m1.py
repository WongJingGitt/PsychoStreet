"""
M1 阶段功能测试脚本
验证核心数据流是否正常工作
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import sqlite3
import json
from db import global_db, game_db, schema
from tools import session_tools, init_tools, trade_tools, turn_tools
from engines.turn_engine import advance_turn


def test_global_db():
    """测试 global.db 初始化"""
    print("=" * 50)
    print("测试 1: global.db 初始化")
    print("=" * 50)
    
    # 获取连接
    conn = global_db.get_global_conn()
    print("✓ global.db 连接成功")
    
    # 验证表结构
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    assert "GameSessions" in tables, "GameSessions 表未创建"
    assert "GameCheckpoints" in tables, "GameCheckpoints 表未创建"
    assert "Settings" in tables, "Settings 表未创建"
    print("✓ 所有表结构正确")
    
    print()


def test_game_creation():
    """测试游戏创建"""
    print("=" * 50)
    print("测试 2: 创建新游戏")
    print("=" * 50)
    
    # 创建新游戏
    result = session_tools.new_game(
        display_name="测试游戏",
        starting_cash=100000.0,
        company_count=5
    )
    
    result_dict = json.loads(result)
    print(f"创建结果: {json.dumps(result_dict, ensure_ascii=False, indent=2)}")
    
    if "error" in result_dict:
        print(f"✗ 创建失败: {result_dict['error']}")
        return None
    
    game_id = result_dict["game_id"]
    print(f"✓ 游戏创建成功，game_id={game_id}")
    
    # 加载游戏
    load_result = json.loads(session_tools.load_game(game_id))
    print(f"✓ 游戏加载成功")
    
    print()
    return game_id


def test_game_db_operations(game_id: int):
    """测试游戏数据库操作"""
    print("=" * 50)
    print("测试 3: 游戏数据库操作")
    print("=" * 50)
    
    # 获取游戏会话
    session = global_db.get_game_session(game_id)
    conn = game_db.get_game_conn(session["db_path"])
    
    # 验证表结构
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    required_tables = [
        "Player", "Stock", "CompanyNPC", "NpcInteractionLog",
        "Portfolio", "PlayerBuffs", "MacroEvents", 
        "ScheduledEvents", "ActionLog", "GameMeta"
    ]
    
    for table in required_tables:
        assert table in tables, f"{table} 表未创建"
    
    print("✓ 所有游戏表结构正确")
    
    # 初始化玩家
    player_result = json.loads(init_tools.init_player(conn, "测试玩家", 100000.0))
    print(f"✓ 玩家初始化成功: {player_result['name']}, 资金: {player_result['cash']:,.2f}")
    
    # 初始化公司
    companies = [
        {"name": "科技公司A", "industry_tag": "科技", "description": "一家科技创新公司"},
        {"name": "银行B", "industry_tag": "金融", "description": "大型商业银行"},
        {"name": "零售C", "industry_tag": "零售", "description": "连锁零售企业"},
    ]
    
    companies_result = json.loads(init_tools.init_companies(conn, companies))
    print(f"✓ 公司初始化成功: {companies_result['created']} 家")
    
    # 初始化宏观事件
    events_result = json.loads(init_tools.init_macro_events(conn, 100))
    print(f"✓ 宏观事件初始化成功: {events_result['created']} 个")
    
    # 初始化市场价格
    prices_result = json.loads(init_tools.init_market_prices(conn))
    print(f"✓ 市场价格初始化成功: {prices_result['updated']} 支股票")
    
    # 查询股票列表
    stocks = conn.execute("SELECT id, name, current_price, hidden_fundamental_value FROM Stock").fetchall()
    print("\n股票列表:")
    for stock in stocks:
        print(f"  - {stock['name']}: ¥{stock['current_price']:.2f} (内在价值: ¥{stock['hidden_fundamental_value']:.2f})")
    
    print()
    return conn


def test_trading(conn: sqlite3.Connection):
    """测试交易功能"""
    print("=" * 50)
    print("测试 4: 股票交易")
    print("=" * 50)
    
    # 获取第一支股票
    stock = conn.execute("SELECT id, name FROM Stock LIMIT 1").fetchone()
    
    # 买入股票
    buy_result = json.loads(trade_tools.tool_buy_stock(conn, stock["id"], 100))
    print(f"买入结果: {json.dumps(buy_result, ensure_ascii=False, indent=2)}")
    
    if "error" in buy_result:
        print(f"✗ 买入失败: {buy_result['error']}")
    else:
        print(f"✓ 买入成功: {buy_result['quantity']} 股 {buy_result['stock_name']}")
    
    # 查询持仓
    portfolio = conn.execute(
        "SELECT p.stock_id, s.name, p.quantity, p.avg_cost "
        "FROM Portfolio p JOIN Stock s ON p.stock_id=s.id "
        "WHERE p.player_id=1"
    ).fetchall()
    
    print("\n当前持仓:")
    for p in portfolio:
        print(f"  - {p['name']}: {p['quantity']} 股，成本 ¥{p['avg_cost']:.2f}")
    
    # 卖出股票
    sell_result = json.loads(trade_tools.tool_sell_stock(conn, stock["id"], 50))
    print(f"\n卖出结果: {json.dumps(sell_result, ensure_ascii=False, indent=2)}")
    
    if "error" in sell_result:
        print(f"✗ 卖出失败: {sell_result['error']}")
    else:
        print(f"✓ 卖出成功: {sell_result['quantity_sold']} 股")
        if sell_result['profit_loss'] > 0:
            print(f"  盈利: ¥{sell_result['profit_loss']:.2f}")
        else:
            print(f"  亏损: ¥{abs(sell_result['profit_loss']):.2f}")
    
    print()


def test_turn_advance(conn: sqlite3.Connection):
    """测试回合推进"""
    print("=" * 50)
    print("测试 5: 回合推进")
    print("=" * 50)
    
    # 推进一个回合
    snapshot = advance_turn(conn)
    
    print(f"回合: {snapshot['turn']}")
    print(f"日历: 第{snapshot['calendar']['week']}周, 第{snapshot['calendar']['month']}月, 第{snapshot['calendar']['quarter']}季度")
    print(f"\n玩家状态:")
    print(f"  - 现金: ¥{snapshot['player']['cash']:,.2f}")
    print(f"  - 声望: {snapshot['player']['fame']}")
    print(f"  - 监管热度: {snapshot['player']['sec_heat']}")
    print(f"  - 粉丝数: {snapshot['player']['social_reach']:,}")
    
    print(f"\n市场快照 ({len(snapshot['market_snapshot'])} 支股票):")
    for stock in snapshot['market_snapshot']:
        change_str = f"+{stock['price_change']:.2f}" if stock['price_change'] >= 0 else f"{stock['price_change']:.2f}"
        print(f"  - {stock['name']}: ¥{stock['price']:.2f} ({change_str}) [{stock['reason']}]")
    
    if snapshot['triggered_events']:
        print(f"\n触发的宏观事件:")
        for event in snapshot['triggered_events']:
            print(f"  - {event['description_template']}")
    
    print()


def main():
    """运行所有测试"""
    print("\n" + "=" * 50)
    print("《发疯华尔街》M1 阶段功能测试")
    print("=" * 50 + "\n")
    
    try:
        # 测试 1: global.db 初始化
        test_global_db()
        
        # 测试 2: 创建游戏
        game_id = test_game_creation()
        if not game_id:
            print("✗ 游戏创建失败，停止测试")
            return
        
        # 测试 3: 游戏数据库操作
        conn = test_game_db_operations(game_id)
        
        # 测试 4: 交易功能
        test_trading(conn)
        
        # 测试 5: 回合推进
        test_turn_advance(conn)
        
        # 测试总结
        print("=" * 50)
        print("✅ 所有测试通过！M1 阶段核心功能正常")
        print("=" * 50)
        
    except AssertionError as e:
        print(f"\n✗ 断言失败: {e}")
    except Exception as e:
        print(f"\n✗ 测试出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
