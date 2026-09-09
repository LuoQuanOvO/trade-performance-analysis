# -*- coding: utf-8 -*-
import pandas as pd
import glob, re
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

def num(s):
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return 0.0
    return float(re.sub(r"[A-Za-z]+", "", str(s)).strip() or 0)

pos_file = r"data/positions.csv"
pos = pd.read_csv(pos_file)
for c in ["仓位盈亏", "开仓手续费", "平仓手续费"]:
    pos[c] = pos[c].apply(num)
pos["开仓时间"] = pd.to_datetime(pos["开仓时间"])
pos["月"] = pos["开仓时间"].dt.to_period("M")
pos["手续费"] = pos["开仓手续费"] + pos["平仓手续费"]

print("=== 按月: 手续费 vs 盈亏 ===")
print(f"{'月份':<10}{'笔数':>6}{'手续费':>10}{'盈亏':>10}{'手续费/亏损%':>12}")
for m, g in pos.groupby("月"):
    fee = g["手续费"].sum()
    pnl = g["仓位盈亏"].sum()
    # 亏损极小时占比会被放大到无意义(如除以-0.1),统一显示为"—"
    ratio = f"{abs(fee / pnl) * 100:.1f}" if pnl < -1 else "—"
    print(f"{str(m):<10}{len(g):>6}{fee:>10.1f}{pnl:>10.1f}{ratio:>12}")

def stage(df, start, end):
    m = df[(df["开仓时间"] >= start) & (df["开仓时间"] < end)]
    fee = m["手续费"].sum()
    pnl = m["仓位盈亏"].sum()
    ratio = round(abs(fee / pnl) * 100, 1) if pnl < -1 else None
    return len(m), round(fee, 1), round(pnl, 1), ratio

def fmt_ratio(r):
    return "—" if r is None else f"{r}%"

print()
print("=== 阶段对比(手续费占比变化) ===")
s1 = stage(pos, "2025-01-01", "2025-07-01")
s2 = stage(pos, "2025-07-01", "2026-01-01")
s3 = stage(pos, "2026-01-01", "2027-01-01")
s4 = stage(pos, "2026-05-01", "2027-01-01")
print(f"2025上半年: 笔数{s1[0]:>4} 手续费{s1[1]:>8} 盈亏{s1[2]:>9} 占比{fmt_ratio(s1[3])}")
print(f"2025下半年: 笔数{s2[0]:>4} 手续费{s2[1]:>8} 盈亏{s2[2]:>9} 占比{fmt_ratio(s2[3])}")
print(f"2026年    : 笔数{s3[0]:>4} 手续费{s3[1]:>8} 盈亏{s3[2]:>9} 占比{fmt_ratio(s3[3])}")
print(f"近3个月   : 笔数{s4[0]:>4} 手续费{s4[1]:>8} 盈亏{s4[2]:>9} 占比{fmt_ratio(s4[3])}")
