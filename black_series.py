# -*- coding: utf-8 -*-
"""
黑色系商品研究 v2: 螺纹钢 基差 + 库存 + 盘面利润 + 正套损益测算 + 跟踪信号
数据源: akshare(免费)
升级点: 基差率历史分位 / 期现正套损益测算(含资金成本) / 盘面利润估算 / 信号触发表
"""
import akshare as ak
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
matplotlib.rcParams["axes.unicode_minus"] = False
import os
import datetime

OUT = r"./black_series"
os.makedirs(OUT, exist_ok=True)

# ============ 参数 ============
AS_OF = os.environ.get("AS_OF", "").strip() or datetime.date.today().strftime("%Y%m%d")  # 数据截止日, 可用环境变量 AS_OF=YYYYMMDD 复现历史
SPOT_LOOKBACK_TRADING_DAYS = 180   # 现货/基差回看窗口(交易日, 非自然日)
FINANCING_RATE = 0.045             # 资金成本年化(正套测算)
HOLD_DAYS = [30, 60]               # 正套持有期情景(天)
PROCESS_FEE = 400                  # 吨钢加工费(估算常数)
IRON_ORE_COEF = 1.6                # 吨钢耗铁矿
COKE_COEF = 0.45                   # 吨钢耗焦炭

# ============ 1. 数据获取 ============
print("=== 1. 获取数据 ===")

def get_main(symbol, start="20250101"):
    df = ak.futures_main_sina(symbol=symbol, start_date=start,
                              end_date=AS_OF)
    df["日期"] = pd.to_datetime(df["日期"])
    df["收盘价"] = pd.to_numeric(df["收盘价"], errors="coerce")
    return df.sort_values("日期").reset_index(drop=True)

print("拉取螺纹钢期货主力连续(2025-01 ~ 至今)...")
fut = get_main("RB0")
print(f"  螺纹期货: {len(fut)} 条, 最新收盘 {fut['收盘价'].iloc[-1]}")

print("拉取铁矿/焦炭期货主力(用于盘面利润)...")
i_fut = get_main("I0")
j_fut = get_main("J0")
print(f"  铁矿: {len(i_fut)} 条 | 焦炭: {len(j_fut)} 条")

print(f"拉取螺纹钢现货价与基差(近{SPOT_LOOKBACK_TRADING_DAYS}个交易日)...")
trade_days = list(fut["日期"].iloc[-SPOT_LOOKBACK_TRADING_DAYS:])  # 取真实交易日序列(非日历日)
basis_rows = []
for i, d in enumerate(trade_days):
    ds = d.strftime("%Y%m%d")
    try:
        df = ak.futures_spot_price(date=ds, vars_list=["RB"])
        if len(df):
            basis_rows.append(df.iloc[0])
    except Exception:
        pass
    if (i + 1) % 50 == 0:
        print(f"  进度: {i+1}/{len(trade_days)}")
basis = pd.DataFrame(basis_rows)
basis["date"] = pd.to_datetime(basis["date"], format="%Y%m%d")
basis = basis.sort_values("date").reset_index(drop=True)
for c in ["dom_basis", "dom_basis_rate", "near_basis", "spot_price", "dominant_contract_price"]:
    basis[c] = pd.to_numeric(basis[c], errors="coerce")
basis = basis.dropna(subset=["dom_basis", "dom_basis_rate"])
print(f"  基差数据: {len(basis)} 条")

print("拉取螺纹钢库存...")
try:
    inv = ak.futures_inventory_em(symbol="螺纹钢")
    inv["日期"] = pd.to_datetime(inv["日期"])
    inv["库存"] = pd.to_numeric(inv["库存"], errors="coerce")
    inv = inv.sort_values("日期").reset_index(drop=True)
    print(f"  库存数据: {len(inv)} 条")
except Exception as e:
    inv = None
    print(f"  库存失败: {e}")

# ============ 2. 基差与分位 ============
print("\n=== 2. 基差率历史分位 ===")
b = basis.copy()
# 基差口径: 现货 - 期货(行业/教材口径); 基差>0=现货升水(期货贴水), <0=现货贴水(期货升水)
b["basis"] = b["spot_price"] - b["dominant_contract_price"]
b["basis_rate"] = b["basis"] / b["spot_price"]
latest_basis = b["basis"].iloc[-1]
latest_rate = b["basis_rate"].iloc[-1]
latest_spot = b["spot_price"].iloc[-1]
pct = (b["basis_rate"] < latest_rate).mean() * 100
print(f"最新基差 {latest_basis:+.0f} 元/吨 | 基差率 {latest_rate*100:+.2f}%")
print(f"基差率处于近{len(b)}个交易日样本的 {pct:.0f}% 分位(越低=期货升水越深)")
print(f"样本内基差率: min {b['basis_rate'].min()*100:+.2f}% | 均值 {b['basis_rate'].mean()*100:+.2f}% | max {b['basis_rate'].max()*100:+.2f}%")

# ============ 3. 期现正套损益测算 ============
# 口径说明: 基差取自主力连续合约(换月存在跳变),测算为近似;
# 成本仅计资金成本(年化4.5%),未计仓储/增值税/交割费用,实际净收益更低。
print("\n=== 3. 期现正套损益测算(买入现货+卖出期货) ===")
print(f"现货 {latest_spot:.0f} | 期货 {b['dominant_contract_price'].iloc[-1]:.0f} | 基差 {latest_basis:+.0f}")
mean_basis = b["basis"].mean()
scenarios = {"收敛至样本均值": mean_basis, "收敛至平水(0)": 0.0, "期货升水20元": -20.0, "期货升水50元": -50.0}
for days in HOLD_DAYS:
    financing = latest_spot * FINANCING_RATE * days / 365
    print(f"\n-- 持有 {days} 天 | 资金成本 {financing:.1f} 元/吨(年化{FINANCING_RATE*100:.1f}%) --")
    print(f"  {'目标基差':<12}{'基差收益':>10}{'资金成本':>10}{'净收益':>10}")
    for name, target in scenarios.items():
        # 正套盈亏 = 目标基差 - 初始基差(基差=现货-期货); 基差向上收敛(向平水/现货升水)时正套盈利
        profit = target - latest_basis
        net = profit - financing
        print(f"  {name:<12}{profit:+8.1f}{financing:>10.1f}{net:+10.1f}")
    breakeven = latest_basis + financing
    print(f"  → 盈亏平衡目标基差: {breakeven:+.1f} 元/吨 (净收益>0 需基差收敛至该水平以上)")

# ============ 4. 盘面利润 ============
print("\n=== 4. 盘面利润估算(螺纹-1.6×铁矿-0.45×焦炭-加工费) ===")
profit_df = fut[["日期", "收盘价"]].merge(i_fut[["日期", "收盘价"]], on="日期", suffixes=("_rb", "_i"))
profit_df = profit_df.merge(j_fut[["日期", "收盘价"]], on="日期")
profit_df = profit_df.rename(columns={"收盘价": "收盘价_j"})
profit_df["盘面利润"] = profit_df["收盘价_rb"] - IRON_ORE_COEF * profit_df["收盘价_i"] - COKE_COEF * profit_df["收盘价_j"] - PROCESS_FEE
profit_df = profit_df.dropna(subset=["盘面利润"])
last_profit = profit_df["盘面利润"].iloc[-1]
print(f"最新盘面利润: {last_profit:+.0f} 元/吨")
print(f"样本均值: {profit_df['盘面利润'].mean():+.0f} | 近120日均值: {profit_df['盘面利润'].iloc[-120:].mean():+.0f}")

# ============ 5. 跟踪信号 ============
print("\n=== 5. 跟踪信号触发状态 ===")
signals = []
if inv is not None and len(inv) >= 2:
    inv_30d = inv[inv["日期"] >= inv["日期"].max() - pd.Timedelta(days=30)]
    d_inv = inv_30d["库存"].iloc[-1] - inv_30d["库存"].iloc[0] if len(inv_30d) >= 2 else 0
else:
    d_inv = None

def signal(no, name, cond, desc):
    signals.append((no, name, "✅ 触发" if cond else "⏸ 未触发", desc))
    print(f"  {no}. [{name}] {'✅ 触发' if cond else '⏸ 未触发'} — {desc}")

d_inv_str = f"{d_inv:+.0f}" if d_inv is not None else "N/A"
signal("S1", "基差修复观察", d_inv is not None and d_inv < 0 and pct > 70,
       f"去库({d_inv_str}) + 基差率高分位({pct:.0f}%) → 期货深贴水,去库支撑现货,贴水有望修复(基差回落),关注反套/锁价机会")
signal("S2", "收敛止盈", pct < 30,
       f"基差率分位({pct:.0f}%)过低 → 期货升水处于历史高位,基差收敛接近完成,反套止盈/离场;正套观察(当前绝对基差小,收敛空间有限)")
signal("S3", "基差修复受阻", d_inv is not None and d_inv > 0 and pct > 70,
       "累库 + 期货深贴水(现货升水高位) → 基本面偏弱,基差修复受阻风险")
signal("S4", "减产预期", last_profit < 0,
       f"盘面利润 {last_profit:+.0f} 元/吨 → 钢厂亏损,减产预期升温,关注供应收缩对现货支撑")
signal("S5", "增产压力", last_profit > 500,
       f"盘面利润 {last_profit:+.0f} 元/吨 → 钢厂高利润,增产动力强,关注供应压力")

# ============ 6. 图表 ============
print("\n=== 6. 生成图表 ===")

# 图1: 期货价格+基差
fig, ax1 = plt.subplots(figsize=(12, 5))
ax1.plot(fut["日期"], fut["收盘价"], color="#1f77b4", linewidth=1.2, label="螺纹钢期货主力连续(RB0)")
ax1.set_ylabel("价格 (元/吨)", color="#1f77b4")
ax2 = ax1.twinx()
ax2.bar(b["date"], b["basis"], color=["#2ca02c" if v > 0 else "#d62728" for v in b["basis"]], alpha=0.6, width=1.5, label="基差(现货-期货)")
ax2.axhline(0, color="gray", linewidth=0.8)
ax2.set_ylabel("基差 (现货-期货, 元/吨)", color="#555")
ax1.set_title("螺纹钢: 期货价格与基差走势")
fig.autofmt_xdate()
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc="best", fontsize=9)
fig.tight_layout()
fig.text(0.01, 0.005, "注: 价格线为连续合约(RB0), 基差口径为即期主力合约, 换月时两者存在差异", fontsize=8, color="#888888")
fig.savefig(os.path.join(OUT, "rb_price_basis.png"), dpi=150)
print("图1: rb_price_basis.png")

# 图2: 基差率 + 当前分位标注
fig, ax = plt.subplots(figsize=(12, 4.5))
ax.plot(b["date"], b["basis_rate"] * 100, color="#9467bd", marker="o", markersize=3, linewidth=1)
ax.axhline(0, color="gray", linewidth=0.8)
ax.axhline(latest_rate * 100, color="red", linewidth=1.2, linestyle="--", label=f"当前基差率 {latest_rate*100:+.2f}% (近{len(b)}日{pct:.0f}%分位)")
ax.set_ylabel("基差率 (%)")
ax.set_title("螺纹钢基差率走势(基差/现货价)")
ax.legend(fontsize=9)
fig.autofmt_xdate()
fig.tight_layout()
fig.savefig(os.path.join(OUT, "rb_basis_rate.png"), dpi=150)
print("图2: rb_basis_rate.png")

# 图3: 基差率分布直方图(分位可视化)
fig, ax = plt.subplots(figsize=(9, 4.5))
ax.hist(b["basis_rate"] * 100, bins=30, color="#9467bd", alpha=0.75)
ax.axvline(latest_rate * 100, color="red", linewidth=2, label=f"当前 {latest_rate*100:+.2f}% (第{pct:.0f}百分位)")
ax.set_xlabel("基差率 (%)")
ax.set_ylabel("天数")
ax.set_title(f"基差率分布(近{len(b)}个交易日)")
ax.legend(fontsize=9)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "rb_basis_hist.png"), dpi=150)
print("图3: rb_basis_hist.png")

# 图4: 库存
if inv is not None:
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.plot(inv["日期"], inv["库存"], color="#d62728", linewidth=1.2)
    ax.set_ylabel("库存")
    ax.set_title("螺纹钢库存走势")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "rb_inventory.png"), dpi=150)
    print("图4: rb_inventory.png")

# 图5: 价格-库存相关性
if inv is not None:
    merged = pd.merge(fut[["日期", "收盘价"]], inv[["日期", "库存"]], on="日期", how="inner")
    if len(merged) > 10:
        corr = merged["收盘价"].corr(merged["库存"])
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.scatter(merged["库存"], merged["收盘价"], alpha=0.5, s=15)
        ax.set_xlabel("库存")
        ax.set_ylabel("期货收盘价 (元/吨)")
        ax.set_title(f"价格与库存相关性 r={corr:.2f}")
        fig.tight_layout()
        fig.savefig(os.path.join(OUT, "rb_price_inv_corr.png"), dpi=150)
        print(f"图5: rb_price_inv_corr.png (r={corr:.2f})")

# 图6: 盘面利润
fig, ax = plt.subplots(figsize=(12, 4.5))
ax.plot(profit_df["日期"], profit_df["盘面利润"], color="#ff7f0e", linewidth=1.2)
ax.axhline(0, color="gray", linewidth=0.8)
ax.axhline(last_profit, color="red", linewidth=1.2, linestyle="--", label=f"当前 {last_profit:+.0f} 元/吨")
ax.set_ylabel("元/吨")
ax.set_title("螺纹钢盘面利润估算(螺纹-1.6×铁矿-0.45×焦炭-加工费)")
ax.legend(fontsize=9)
fig.autofmt_xdate()
fig.tight_layout()
fig.savefig(os.path.join(OUT, "rb_profit.png"), dpi=150)
print("图6: rb_profit.png")

# ============ 7. 汇总 ============
print("\n=== 7. 汇总 ===")
print(f"螺纹钢期货最新价: {fut['收盘价'].iloc[-1]} 元/吨 ({fut['日期'].iloc[-1].date()})")
print(f"最新基差: {latest_basis:+.0f} 元/吨, 基差率 {latest_rate*100:+.2f}% (近{len(b)}日{pct:.0f}%分位)")
print(f"最新盘面利润: {last_profit:+.0f} 元/吨")
if inv is not None and d_inv is not None:
    print(f"最新库存: {inv['库存'].iloc[-1]:.0f}, 近30日变化 {d_inv:+.0f}")
print(f"输出目录: {OUT}")
