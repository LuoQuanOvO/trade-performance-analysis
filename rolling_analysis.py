# -*- coding: utf-8 -*-
"""滑动窗口进步分析: 近一年/半年/三个月/一个月 的指标演进"""
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
for c in ["仓位盈亏"]:
    pos[c] = pos[c].apply(num)
pos["开仓时间"] = pd.to_datetime(pos["开仓时间"])
pos["全部平仓时间"] = pd.to_datetime(pos["全部平仓时间"])
pos["持仓小时"] = (pos["全部平仓时间"] - pos["开仓时间"]).dt.total_seconds() / 3600
pos["方向类型"] = pos["合约"].apply(lambda x: "做多" if "Long" in str(x) else "做空")

OUT = r"."
os.makedirs(OUT, exist_ok=True)

def metrics(df):
    if len(df) == 0:
        return dict(笔数=0, 胜率=float("nan"), 盈亏比=float("nan"), 持仓h=float("nan"), 做空pct=float("nan"), 盈亏=0.0)
    wins = (df["仓位盈亏"] > 0).mean() * 100
    aw = df.loc[df["仓位盈亏"] > 0, "仓位盈亏"].mean()
    al = df.loc[df["仓位盈亏"] < 0, "仓位盈亏"].mean()
    rr = abs(aw / al) if al != 0 else float("nan")
    return dict(
        笔数=len(df), 胜率=round(wins, 1),
        盈亏比=round(rr, 2),
        持仓h=round(df["持仓小时"].median(), 2),
        做空pct=round((df["方向类型"] == "做空").mean() * 100, 1),
        盈亏=round(df["仓位盈亏"].sum(), 2),
    )

END = pos["开仓时间"].max()
print(f"数据截止: {END}")
print("=" * 70)
print(f"{'窗口':<10}{'笔数':>5}{'胜率%':>8}{'盈亏比':>8}{'持仓中位h':>10}{'做空%':>7}{'盈亏单位':>10}")
for label, days in [("近1个月", 30), ("近3个月", 92), ("近半年", 182), ("近1年", 365), ("全部", 9999)]:
    m = pos[pos["开仓时间"] >= END - pd.Timedelta(days=days)]
    r = metrics(m)
    print(f"{label:<10}{r['笔数']:>5}{r['胜率']:>8.1f}{r['盈亏比']:>8.2f}{r['持仓h']:>10.2f}{r['做空pct']:>7.1f}{r['盈亏']:>10.2f}")

# 滑动3个月窗口(月度滑动)画图
pos["月"] = pos["开仓时间"].dt.to_period("M")
months = sorted(pos["月"].unique())
roll_win, roll_rr, roll_pnl, roll_labels = [], [], [], []
for i in range(len(months)):
    start = months[max(0, i - 2)].to_timestamp()
    end = months[i].to_timestamp() + pd.Timedelta(days=32)
    m = pos[(pos["开仓时间"] >= start) & (pos["开仓时间"] < end)]
    if len(m) >= 10:
        r = metrics(m)
        roll_win.append(r["胜率"]); roll_rr.append(r["盈亏比"]); roll_pnl.append(r["盈亏"])
        roll_labels.append(str(months[i]))

fig, ax1 = plt.subplots(figsize=(11, 5))
ax1.plot(roll_labels, roll_win, marker="o", color="#1f77b4", label="滑动3月胜率(%)")
ax1.axhline(50, color="gray", linestyle="--", linewidth=0.8)
ax1.set_ylabel("胜率 (%)", color="#1f77b4")
ax2 = ax1.twinx()
ax2.plot(roll_labels, roll_rr, marker="s", color="#ff7f0e", label="滑动3月盈亏比")
ax2.axhline(1.0, color="orange", linestyle="--", linewidth=0.8)
ax2.set_ylabel("盈亏比", color="#ff7f0e")
ax1.set_xticks(range(len(roll_labels)))
ax1.set_xticklabels(roll_labels, rotation=45, fontsize=8)
ax1.set_title("滑动3个月窗口: 胜率与盈亏比趋势(样本>=10笔)")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "rolling_window_trend.png"), dpi=150)
print("\n图已保存: rolling_window_trend.png")

print("\n最近5个滑动窗口(仅展示样本>=10笔):")
for i in range(max(0, len(roll_labels) - 5), len(roll_labels)):
    print(f"  {roll_labels[i]}: 胜率{roll_win[i]}% | 盈亏比{roll_rr[i]}")
