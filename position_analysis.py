# -*- coding: utf-8 -*-
"""完整仓位级分析: 基于历史仓位导出(开平配对,含资金费用)"""
import pandas as pd
import re, glob

from anonymize import alias

def num(s):
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return 0.0
    return float(re.sub(r"[A-Za-z]+", "", str(s)).strip() or 0)

pos_file = r"data/positions.csv"
pos = pd.read_csv(pos_file)
for c in ["平仓量", "平仓价值", "仓位盈亏", "已实现盈亏", "资金费用", "开仓手续费", "平仓手续费"]:
    pos[c] = pos[c].apply(num)

pos["开仓时间"] = pd.to_datetime(pos["开仓时间"])
pos["全部平仓时间"] = pd.to_datetime(pos["全部平仓时间"])
pos["持仓小时"] = (pos["全部平仓时间"] - pos["开仓时间"]).dt.total_seconds() / 3600
pos["方向类型"] = pos["合约"].apply(lambda x: "做多" if "Long" in str(x) else "做空")
pos["品种"] = pos["合约"].apply(alias)

print("=" * 60)
print("完整仓位分析(开平配对)")
print(f"仓位总数: {len(pos)} | 时间范围: {pos['开仓时间'].min()} ~ {pos['开仓时间'].max()}")

print("\n1. 盈亏全景")
print(f"   仓位盈亏合计: {pos['仓位盈亏'].sum():+.2f} 单位")
print(f"   已实现盈亏: {pos['已实现盈亏'].sum():+.2f} 单位")
print(f"   资金费用(过夜成本): {pos['资金费用'].sum():+.2f} 单位")
print(f"   开仓手续费: {pos['开仓手续费'].sum():.2f} | 平仓手续费: {pos['平仓手续费'].sum():.2f}")
print(f"   总成本(手续费+资金费用): {pos['开仓手续费'].sum()+pos['平仓手续费'].sum()+pos['资金费用'].sum():.2f}")

print("\n2. 持仓时长(真实)")
print(f"   平均: {pos['持仓小时'].mean():.1f} 小时 | 中位数: {pos['持仓小时'].median():.1f} 小时")
print(f"   持仓<1小时占比: {(pos['持仓小时']<1).mean()*100:.0f}%")
print(f"   持仓<24小时占比: {(pos['持仓小时']<24).mean()*100:.0f}%")

print("\n3. 仓位方向归因")
d = pos.groupby("方向类型").agg(仓位数=("合约", "count"), 盈亏=("仓位盈亏", "sum"), 胜率=("仓位盈亏", lambda x: round((x > 0).mean() * 100, 1)))
print(d.to_string())

print("\n4. 品种归因(盈亏Top/Bottom 10)")
s = pos.groupby("品种")["仓位盈亏"].sum().sort_values()
print("   最赚:", s.tail(5).to_string().replace("\n", "\n        "))
print("   最亏:", s.head(5).to_string().replace("\n", "\n        "))

print("\n5. 资金费用Top5(长持仓成本)")
print(pos.nlargest(5, "资金费用")[["品种", "方向类型", "持仓小时", "资金费用"]].round(2).to_string())

print("\n6. 每仓位盈亏分布")
import numpy as np
pnl = pos["仓位盈亏"].values
print(f"   盈利仓位: {(pnl > 0).sum()} ({(pnl > 0).mean()*100:.1f}%) | 亏损: {(pnl <= 0).sum()} ({(pnl <= 0).mean()*100:.1f}%)")
print(f"   平均盈利: {pnl[pnl > 0].mean():+.3f} | 平均亏损: {pnl[pnl <= 0].mean():+.3f} | 盈亏比: {abs(pnl[pnl>0].mean()/pnl[pnl<=0].mean()):.2f}")

print("\n7. 盈利仓位最大回吐(MFE模拟)")
print("   盈利仓位中, 最高浮盈(以平仓价-开仓价计算): 说明盈利未充分兑现")
