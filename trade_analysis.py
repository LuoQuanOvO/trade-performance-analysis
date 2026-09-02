# -*- coding: utf-8 -*-
"""
Trade Performance Analysis
对个人衍生品实盘交易记录进行绩效归因分析
数据: 交易所成交明细导出CSV(本地, 不入库)
"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
matplotlib.rcParams["axes.unicode_minus"] = False
import os

from anonymize import alias

DATA_PATH = r"data/fills.csv"
OUT_DIR = r"."

os.makedirs(OUT_DIR, exist_ok=True)

# ---------- 1. 数据读取与清洗 ----------
df = pd.read_csv(DATA_PATH)
df["时间"] = pd.to_datetime(df["时间"])
for c in ["已实现盈亏", "净盈亏", "手续费"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")

closes = df[df["方向"].str.contains("Close|Liquidation", case=False, na=False)].copy()
closes["月"] = closes["时间"].dt.to_period("M")

print(f"总成交记录: {len(df)} 条, 平仓记录: {len(closes)} 笔")
print(f"时间范围: {df['时间'].min()} ~ {df['时间'].max()}")

# ---------- 2. 核心绩效指标 ----------
total_pnl = closes["净盈亏"].sum()
total_fee = df["手续费"].sum()
win_rate = (closes["净盈亏"] > 0).mean() * 100
wins = closes[closes["净盈亏"] > 0]["净盈亏"]
losses = closes[closes["净盈亏"] < 0]["净盈亏"]
profit_factor = abs(wins.sum() / losses.sum()) if losses.sum() else float("inf")

print("=" * 50)
print(f"净盈亏(扣费): {total_pnl:+.2f} 单位")
print(f"手续费: {total_fee:.2f} 单位")
print(f"胜率: {win_rate:.1f}%")
print(f"平均盈利: {wins.mean():+.3f} | 平均亏损: {losses.mean():+.3f} | 盈亏比: {abs(wins.mean()/losses.mean()):.2f}")
print(f"盈亏因子(Profit Factor): {profit_factor:.2f}")
print("=" * 50)

# ---------- 3. 图表1: 月度净值曲线 ----------
monthly = closes.groupby("月")["净盈亏"].sum().cumsum()
fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(monthly.index.astype(str), monthly.values, marker="o", linewidth=2)
ax.axhline(0, color="gray", linestyle="--", linewidth=1)
ax.set_title("月度累计净盈亏曲线(单位)")
ax.set_xlabel("月份")
ax.set_ylabel("累计净盈亏 (单位)")
ax.tick_params(axis="x", rotation=45)
fig.tight_layout()
fig.savefig(os.path.join(OUT_DIR, "1_monthly_equity.png"), dpi=150)
print("图表1已保存: 1_monthly_equity.png")

# ---------- 4. 图表2: 单笔盈亏分布 ----------
fig, ax = plt.subplots(figsize=(10, 5))
bins = pd.cut(closes["净盈亏"], bins=40).value_counts().sort_index()
ax.bar([str(b) for b in bins.index], bins.values, width=0.8)
ax.set_title("单笔交易盈亏分布")
ax.set_xlabel("单笔净盈亏区间 (单位)")
ax.set_ylabel("笔数")
ax.tick_params(axis="x", rotation=90, labelsize=8)
fig.tight_layout()
fig.savefig(os.path.join(OUT_DIR, "2_pnl_distribution.png"), dpi=150)
print("图表2已保存: 2_pnl_distribution.png")

# ---------- 5. 图表3: 按品种盈亏归因(主流资产白名单+其他聚合) ----------
# 展示名统一走 anonymize.alias(非大宗类->SYM_*, 贵金属/能源类保留); 其余品种聚合为"其他"
closes["品种"] = closes["合约"].apply(alias)
by_symbol_all = closes.groupby("品种")["净盈亏"].sum()
main_symbols = [s for s in closes["品种"].unique() if s not in ("其他",)]
# 主流 = 出现笔数最多的前4个品种, 其余聚合为其他; 避免真实名称出现在图表
top_n = by_symbol_all.abs().sort_values(ascending=False).head(4).index.tolist()
by_symbol = by_symbol_all[top_n].sort_values()
others_sum = by_symbol_all.drop(top_n).sum()
if others_sum != 0:
    by_symbol = pd.concat([by_symbol, pd.Series({"其他": others_sum})]).sort_values()
fig, ax = plt.subplots(figsize=(10, 5))
colors = ["#d62728" if v < 0 else "#2ca02c" for v in by_symbol.values]
ax.barh([str(x) for x in by_symbol.index], by_symbol.values, color=colors)
ax.set_title("各品种累计盈亏(单位, 主流资产+其他)")
ax.set_xlabel("累计盈亏 (单位)")
for i, v in enumerate(by_symbol.values):
    ax.text(v, i, f" {v:.1f}", va="center", fontsize=8)
fig.tight_layout()
fig.savefig(os.path.join(OUT_DIR, "3_symbol_pnl.png"), dpi=150)
print("图表3已保存: 3_symbol_pnl.png")

# ---------- 6. 图表4: 多空方向对比 ----------
closes["方向类型"] = closes["方向"].apply(lambda x: "做多" if "long" in x.lower() else "做空")
dir_pnl = closes.groupby("方向类型")["净盈亏"].sum()
fig, ax = plt.subplots(figsize=(6, 5))
ax.bar(dir_pnl.index, dir_pnl.values, color=["#d62728", "#2ca02c"])
for i, v in enumerate(dir_pnl.values):
    ax.text(i, v, f" {v:.1f}", ha="center", va="bottom" if v > 0 else "top")
ax.set_title("多空方向盈亏对比(单位)")
ax.set_ylabel("累计盈亏 (单位)")
fig.tight_layout()
fig.savefig(os.path.join(OUT_DIR, "4_direction_pnl.png"), dpi=150)
print("图表4已保存: 4_direction_pnl.png")

# ---------- 7. 汇总指标导出 ----------
summary = pd.DataFrame({
    "指标": ["总成交记录", "平仓笔数", "时间范围", "净盈亏(单位)", "手续费(单位)",
             "胜率(%)", "平均盈利(单位)", "平均亏损(单位)", "盈亏比", "盈亏因子"],
    "数值": [len(df), len(closes), f"{df['时间'].min().date()} ~ {df['时间'].max().date()}",
             round(total_pnl, 2), round(total_fee, 2), round(win_rate, 1),
             round(wins.mean(), 3), round(losses.mean(), 3),
             round(abs(wins.mean() / losses.mean()), 2), round(profit_factor, 2)],
})
summary.to_csv(os.path.join(OUT_DIR, "summary.csv"), index=False, encoding="utf-8-sig")
monthly.to_frame("累计净盈亏").to_csv(os.path.join(OUT_DIR, "monthly_cum_pnl.csv"), encoding="utf-8-sig")
_disp_pnl = by_symbol.copy()
_disp_pnl.to_frame("净盈亏").to_csv(os.path.join(OUT_DIR, "symbol_pnl.csv"), encoding="utf-8-sig")

print("\n全部完成, 输出目录:", OUT_DIR)
