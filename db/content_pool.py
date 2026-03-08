import json
import os
import random
import yaml
from typing import Any

CONTENT_POOL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 
    "data", "content", "content_pool.yaml"
)

_companies_pool: list[dict] = []
_celebrities_pool: list[dict] = []
_institutions_pool: list[dict] = []
_pool_loaded: bool = False


def _load_pool() -> bool:
    """加载内容池到内存"""
    global _companies_pool, _celebrities_pool, _institutions_pool, _pool_loaded
    
    if _pool_loaded:
        return True
    
    try:
        if not os.path.exists(CONTENT_POOL_PATH):
            print(f"警告: 内容池文件不存在: {CONTENT_POOL_PATH}")
            return False
        
        with open(CONTENT_POOL_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        _companies_pool = data.get("companies", [])
        _celebrities_pool = data.get("celebrities", [])
        _institutions_pool = data.get("institutions", [])
        
        _pool_loaded = True
        return True
    
    except Exception as e:
        print(f"加载内容池失败: {e}")
        return False


def _save_pool() -> None:
    """保存剩余池内容回 YAML（可选，用于断点续玩）"""
    global _companies_pool, _celebrities_pool, _institutions_pool
    
    try:
        os.makedirs(os.path.dirname(CONTENT_POOL_PATH), exist_ok=True)
        
        data = {
            "companies": _companies_pool,
            "celebrities": _celebrities_pool,
            "institutions": _institutions_pool,
        }
        
        with open(CONTENT_POOL_PATH, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
    
    except Exception as e:
        print(f"保存内容池失败: {e}")


def get_pool_status() -> dict:
    """获取池子剩余数量"""
    _load_pool()
    
    return {
        "companies_remaining": len(_companies_pool),
        "celebrities_remaining": len(_celebrities_pool),
        "institutions_remaining": len(_institutions_pool),
        "total_companies": len(_companies_pool),
        "total_celebrities": len(_celebrities_pool),
        "total_institutions": len(_institutions_pool),
    }


def draw_companies(count: int, industry_filter: str | None = None) -> list[dict]:
    """
    从公司池抽取公司
    
    Args:
        count: 抽取数量
        industry_filter: 可选的行业过滤器
    
    Returns:
        list[dict]: 抽取的公司列表（包含 name, industry_tag, description）
    """
    _load_pool()
    
    global _companies_pool
    
    available = _companies_pool.copy()
    
    if industry_filter:
        available = [c for c in available if c.get("industry_tag") == industry_filter]
    
    if len(available) < count:
        return []
    
    selected = random.sample(available, count)
    
    for item in selected:
        if item in _companies_pool:
            _companies_pool.remove(item)
    
    return selected


def draw_celebrities(count: int) -> list[dict]:
    """
    从名人池抽取名人
    
    Args:
        count: 抽取数量
    
    Returns:
        list[dict]: 抽取的名人列表（包含 name, role, influence_power, description）
    """
    _load_pool()
    
    global _celebrities_pool
    
    if len(_celebrities_pool) < count:
        return []
    
    selected = random.sample(_celebrities_pool, count)
    
    for item in selected:
        if item in _celebrities_pool:
            _celebrities_pool.remove(item)
    
    return selected


def draw_institutions(count: int, type_filter: str | None = None) -> list[dict]:
    """
    从机构池抽取机构
    
    Args:
        count: 抽取数量
        type_filter: 可选的策略类型过滤器 (value/hedge_short/quant)
    
    Returns:
        list[dict]: 抽取的机构列表（包含 name, type, capital, description）
    """
    _load_pool()
    
    global _institutions_pool
    
    available = _institutions_pool.copy()
    
    if type_filter:
        available = [i for i in available if i.get("type") == type_filter]
    
    if len(available) < count:
        return []
    
    selected = random.sample(available, count)
    
    for item in selected:
        if item in _institutions_pool:
            _institutions_pool.remove(item)
    
    return selected


def get_company_by_name(name: str) -> dict | None:
    """根据名称从剩余池中获取公司信息"""
    _load_pool()
    
    for c in _companies_pool:
        if c.get("name") == name:
            return c
    return None


def get_celebrity_by_name(name: str) -> dict | None:
    """根据名称从剩余池中获取名人信息"""
    _load_pool()
    
    for c in _celebrities_pool:
        if c.get("name") == name:
            return c
    return None


def get_institution_by_name(name: str) -> dict | None:
    """根据名称从剩余池中获取机构信息"""
    _load_pool()
    
    for i in _institutions_pool:
        if i.get("name") == name:
            return i
    return None
