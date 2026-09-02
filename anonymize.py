# -*- coding: utf-8 -*-
"""品种名脱敏模块: 数据分析/展示层的统一名称映射.

设计原则:
- 分析全流程仍使用原始数据(准确性与可复现性不受影响), 仅在"对外展示"时调用本模块改名.
- 大宗商品品类(贵金属/能源类, 如 XAU/XAG/CL)保留真实名称: 与品种研究背景自洽,
  也是跨资产类别的自然组成部分.
- 其余品种(非大宗类,如代币化类合约)统一映射为中性代号 SYM_AA / SYM_AB / ...,
  按首次出现顺序分配, 重复出现保持不变.
- 本文件不包含任何真实品种名称字面量(示例均以占位符代替).
"""

import re

# 大宗商品品类: 保留真名 (黄金/白银/原油等, 与简历/README 口径一致)
KEEP = {"XAU", "XAG", "CL"}

# 报价货币后缀(数据侧统一为 3~4 字母, 如 USDT/USDC/USD), 用通用长度规则剥离
_QUOTE_SUFFIX = re.compile(r"[A-Z]{3,4}$")

_counter = {}


def _sym_code(n: int) -> str:
    """序号 -> 双字母代号: 0->AA, 1->AB, ..., 25->AZ, 26->BA ... 支持任意品种数."""
    c1 = chr(ord("A") + n // 26)
    c2 = chr(ord("A") + n % 26)
    return c1 + c2


def base(symbol: str) -> str:
    """提取合约基名(以占位符示例): 'SYMUSDT Short·Isolated' -> 'SYM'; 'XAUUSDT' -> 'XAU'.

    剥离报价货币后缀后若剩余过短(如本无后缀的4字母基名被误剥), 则保留原样.
    """
    raw = str(symbol)
    # 方向标注(Short/Long/Isolated/Cross)在空格之后, 取第一段即可
    first = raw.split(" ")[0].upper()
    stripped = _QUOTE_SUFFIX.sub("", first)
    if len(stripped) < 2:
        return first
    return stripped


def alias(symbol: str) -> str:
    """合约或基名 -> 展示名. 保留 KEEP 集合真名, 其余按出现顺序分配代号."""
    b = base(symbol)
    if b in KEEP:
        return b
    if b not in _counter:
        _counter[b] = "SYM_" + _sym_code(len(_counter))
    return _counter[b]


def reset() -> None:
    """重置代号计数器(测试/多批次时保证确定性)."""
    _counter.clear()
