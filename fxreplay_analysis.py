# -*- coding: utf-8 -*-
"""FXReplay回测复盘归因分析: 形态/市场背景/方向/MFE"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
matplotlib.rcParams["axes.unicode_minus"] = False
import os

DATA = r"data/Al_Brooks_FXReplay_v3_20260710.xlsx"
OUT = r"./fxreplay_out"
os.makedirs(OUT, exist_ok=True)

df = pd.read_excel(DATA, sheet_name="Trade Log")
# 只统计已平仓且有明确结果的交易(Win/Loss),排除空行与公式错误行(#DIV/0!等)
df = df[df["Win/Loss"].isin(["Win", "Loss"])]
df["Final Result(R)"] = pd.to_numeric(df["Final Result(R)"], errors="coerce")
df["MFE(R)"] = pd.to_numeric(df["MFE(R)"], errors="coerce")

print(f"有效回测交易: {len(df)} 笔 | 胜率: {(df['Win/Loss']=='Win').mean()*100:.1f}% | 总R: {df['Final Result(R)'].sum():+.2f}")

# ============ 图1: 形态归因 ============
g = df.groupby("Setup Pattern").agg(笔数=("Trade ID", "count"), 总R=("Final Result(R)", "sum"))
g = g.sort_values("总R")
fig, ax = plt.subplots(figsize=(10, 5))
colors = ["#d62728" if v < 0 else "#2ca02c" for v in g["总R"]]
ax.barh(g.index, g["总R"], color=colors)
for i, (r, n) in enumerate(zip(g["总R"], g["笔数"])):
    ax.text(r, i, f" {r:+.2f}R ({n}笔)", va="center", fontsize=9)
ax.axvline(0, color="gray", linewidth=1)
ax.set_title("FXReplay回测: 各形态盈亏归因(R)")
ax.set_xlabel("总R")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fxreplay_pattern_pnl.png"), dpi=150)
print("图1已保存: fxreplay_pattern_pnl.png")

# ============ 图2: 市场背景归因 ============
g2 = df.groupby("Market Background").agg(笔数=("Trade ID", "count"),
                                         总R=("Final Result(R)", "sum"),
                                         胜率=("Win/Loss", lambda x: round((x == "Win").mean() * 100, 1)))
g2 = g2.sort_values("总R")
fig, ax = plt.subplots(figsize=(8, 4.5))
colors2 = ["#d62728" if v < 0 else "#2ca02c" for v in g2["总R"]]
ax.barh(g2.index, g2["总R"], color=colors2)
for i, (r, n, w) in enumerate(zip(g2["总R"], g2["笔数"], g2["胜率"])):
    ax.text(r, i, f" {r:+.2f}R ({n}笔, 胜率{w}%)", va="center", fontsize=9)
ax.axvline(0, color="gray", linewidth=1)
ax.set_title("FXReplay回测: 市场背景盈亏归因(R)")
ax.set_xlabel("总R")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fxreplay_background_pnl.png"), dpi=150)
print("图2已保存: fxreplay_background_pnl.png")

# ============ 图3: 方向归因 ============
g3 = df.groupby("Direction").agg(笔数=("Trade ID", "count"), 总R=("Final Result(R)", "sum"))
fig, ax = plt.subplots(figsize=(6, 4))
colors3 = ["#d62728" if v < 0 else "#2ca02c" for v in g3["总R"]]
ax.bar(g3.index, g3["总R"], color=colors3, width=0.4)
for i, (r, n) in enumerate(zip(g3["总R"], g3["笔数"])):
    ax.text(i, r, f" {r:+.2f}R ({n}笔)", ha="center", va="bottom" if r > 0 else "top")
ax.set_title("FXReplay回测: 多空方向盈亏(R)")
ax.set_ylabel("总R")
ax.axhline(0, color="gray", linewidth=1)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fxreplay_direction_pnl.png"), dpi=150)
print("图3已保存: fxreplay_direction_pnl.png")

# ============ 图4: MFE vs 实际R (盈利兑现度) ============
fig, ax = plt.subplots(figsize=(10, 5))
wins_only = df[df["Win/Loss"] == "Win"]
x = range(len(wins_only))
ax.bar([i - 0.18 for i in x], wins_only["MFE(R)"], width=0.36, label="理论最大盈利 MFE(R)", color="#1f77b4")
ax.bar([i + 0.18 for i in x], wins_only["Final Result(R)"], width=0.36, label="实际兑现 R", color="#ff7f0e")
ax.set_xticks(list(x))
ax.set_xticklabels([str(int(t)) for t in wins_only["Trade ID"]], fontsize=8)
ax.set_xlabel("盈利交易编号")
ax.set_ylabel("R")
ax.set_title("FXReplay回测: 盈利单理论盈利(MFE) vs 实际兑现(赚小亏大的直接证据)")
ax.legend()
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fxreplay_mfe_vs_actual.png"), dpi=150)
print("图4已保存: fxreplay_mfe_vs_actual.png")

# 关键数字输出
print("\n=== 关键数字 ===")
print(f"总R: {df['Final Result(R)'].sum():+.2f} | 胜率: {(df['Win/Loss']=='Win').mean()*100:.1f}%")
print(f"平均MFE(R): {df['MFE(R)'].mean():.2f} vs 平均实际R: {df['Final Result(R)'].mean():.3f}")
print(f"兑现率: {df['Final Result(R)'].mean()/df['MFE(R)'].mean()*100:.1f}%")
print("\n按形态:")
print(df.groupby("Setup Pattern").agg(笔数=("Trade ID", "count"), 总R=("Final Result(R)", "sum")).round(2).sort_values("总R", ascending=False).to_string())
print("\n按市场背景:")
print(df.groupby("Market Background").agg(笔数=("Trade ID", "count"), 总R=("Final Result(R)", "sum")).round(2).to_string())
print("\n按方向:")
print(df.groupby("Direction").agg(笔数=("Trade ID", "count"), 总R=("Final Result(R)", "sum")).round(2).to_string())
