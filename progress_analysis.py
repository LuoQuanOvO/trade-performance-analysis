# -*- coding: utf-8 -*-
"""进步轨迹分析: 按时间段切分仓位,看胜率/盈亏比/持仓时长/方向比例的变化"""
import pandas as pd
import re, glob
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
matplotlib.rcParams["axes.unicode_minus"] = False
import os

def num(s):
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return 0.0
    return float(re.sub(r"[A-Za-z]+", "", str(s)).strip() or 0)

pos_file = r"data/positions.csv"
pos = pd.read_csv(pos_file)
for c in ["仓位盈亏", "开仓手续费", "平仓手续费"]:
    pos[c] = pos[c].apply(num)

pos["开仓时间"] = pd.to_datetime(pos["开仓时间"])
pos["全部平仓时间"] = pd.to_datetime(pos["全部平仓时间"])
pos["持仓小时"] = (pos["全部平仓时间"] - pos["开仓时间"]).dt.total_seconds() / 3600
pos["方向类型"] = pos["合约"].apply(lambda x: "做多" if "Long" in str(x) else "做空")

OUT = r"."
os.makedirs(OUT, exist_ok=True)

# 按月份统计滑动指标
pos["月"] = pos["开仓时间"].dt.to_period("M")

def month_metrics(df):
    if len(df) == 0:
        return {}
    wins = (df["仓位盈亏"] > 0).mean() * 100
    avg_win = df.loc[df["仓位盈亏"] > 0, "仓位盈亏"].mean()
    avg_loss = df.loc[df["仓位盈亏"] < 0, "仓位盈亏"].mean()
    rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    hold = df["持仓小时"].median()
    short_pct = (df["方向类型"] == "做空").mean() * 100
    total = df["仓位盈亏"].sum()
    return {"胜率": wins, "盈亏比": rr, "持仓中位(h)": hold, "做空占比%": short_pct, "月盈亏": total, "月数": df["月"].nunique(), "笔数": len(df)}

rows = {}
for m, g in pos.groupby("月"):
    rows[str(m)] = month_metrics(g)

idx = sorted(rows.keys())
metrics = pd.DataFrame([rows[k] for k in idx], index=idx)

pd.set_option("display.width", 200)
print("=== 月度指标演进 ===")
print(metrics.round(2).to_string())

# 三个阶段的对比(2025上半年 / 2025下半年 / 2026)
def stage(df, start, end):
    m = df[(df["开仓时间"] >= start) & (df["开仓时间"] < end)]
    return month_metrics(m)

s1 = stage(pos, "2025-01-01", "2025-07-01")
s2 = stage(pos, "2025-07-01", "2026-01-01")
s3 = stage(pos, "2026-01-01", "2027-01-01")
print("\n=== 阶段对比(2025上 / 2025下 / 2026) ===")
print("阶段      胜率  盈亏比  持仓h  做空%  月均盈亏  笔数")
for name, s in [("2025上", s1), ("2025下", s2), ("2026", s3)]:
    print(f"{name}  {s['胜率']:5.1f}%  {s['盈亏比']:.2f}  {s['持仓中位(h)']:5.1f}  {s['做空占比%']:5.1f}  {s['月盈亏']/max(s['月数'],1):+.2f}  {s['笔数']}")

# ============ 图1: 月度胜率+盈亏比演进 ============
fig, ax1 = plt.subplots(figsize=(11, 5))
ax1.plot(range(len(idx)), metrics["胜率"], marker="o", color="#1f77b4", label="胜率(%)")
ax1.set_ylabel("胜率 (%)", color="#1f77b4")
ax1.axhline(50, color="gray", linestyle="--", linewidth=0.8)
ax1.set_xticks(range(len(idx)))
ax1.set_xticklabels(idx, rotation=45, fontsize=8)
ax2 = ax1.twinx()
ax2.plot(range(len(idx)), metrics["盈亏比"], marker="s", color="#ff7f0e", label="盈亏比")
ax2.set_ylabel("盈亏比", color="#ff7f0e")
ax1.set_title("月度胜率与盈亏比演进(进步轨迹)")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "progress_winrate_rr.png"), dpi=150)
print("\n图1已保存: progress_winrate_rr.png")

# ============ 图2: 月度盈亏柱状+做空占比 ============
fig, ax1 = plt.subplots(figsize=(11, 5))
colors = ["#d62728" if v < 0 else "#2ca02c" for v in metrics["月盈亏"]]
ax1.bar(range(len(idx)), metrics["月盈亏"], color=colors, alpha=0.7, label="月度盈亏(单位)")
ax1.set_ylabel("月度盈亏 (单位)")
ax1.set_xticks(range(len(idx)))
ax1.set_xticklabels(idx, rotation=45, fontsize=8)
ax2 = ax1.twinx()
ax2.plot(range(len(idx)), metrics["做空占比%"], marker="^", color="#9467bd", label="做空占比(%)")
ax2.set_ylabel("做空占比 (%)", color="#9467bd")
ax1.set_title("月度盈亏与做空占比(空优于多的策略调整)")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "progress_monthly_pnl_short.png"), dpi=150)
print("图2已保存: progress_monthly_pnl_short.png")

# 结论判断: 是否有进步
print("\n=== 进步判定 ===")
if s1["笔数"] and s3["笔数"]:
    print(f"胜率: {s1['胜率']:.1f}% -> {s3['胜率']:.1f}%")
    print(f"盈亏比: {s1['盈亏比']:.2f} -> {s3['盈亏比']:.2f}")
    print(f"持仓时长: {s1['持仓中位(h)']:.1f}h -> {s3['持仓中位(h)']:.1f}h")
    print(f"做空占比: {s1['做空占比%']:.1f}% -> {s3['做空占比%']:.1f}%")
