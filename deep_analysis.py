# -*- coding: utf-8 -*-
"""深度绩效分析:回撤、连亏、时间效应、持仓时长、期望值"""
import pandas as pd
import numpy as np

DATA_PATH = r"data/fills.csv"

df = pd.read_csv(DATA_PATH)
df["时间"] = pd.to_datetime(df["时间"])
for c in ["已实现盈亏", "净盈亏", "手续费"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")

closes = df[df["方向"].str.contains("Close|Liquidation", case=False, na=False)].copy()
closes["月"] = closes["时间"].dt.to_period("M")
closes["星期"] = closes["时间"].dt.dayofweek
closes["小时"] = closes["时间"].dt.hour
closes["方向类型"] = closes["方向"].apply(lambda x: "做多" if "long" in x.lower() else "做空")

pnl = closes["净盈亏"].values
print("=" * 60)
print("1. 最大回撤(按月度累计净值)")
cum = closes.groupby("月")["净盈亏"].sum().cumsum().values
peak = np.maximum.accumulate(cum)
dd = cum - peak
print(f"   最大回撤: {dd.min():.2f} 单位, 发生在月度序列第{np.argmin(dd)+1}个月(相对最高点)")

print("\n1b. 最大回撤(成交明细口径,逐笔累计)")
cum2 = np.cumsum(pnl)
peak2 = np.maximum.accumulate(cum2)
dd2 = cum2 - peak2
i2 = int(np.argmin(dd2))
print(f"   最大回撤: {dd2.min():.2f} 单位 (峰值 {peak2[i2]:+.2f} → 谷值 {cum2[i2]:+.2f})")

print("\n2. 连续盈利/连续亏损(单笔)")
streak = 0
max_win_streak = max_loss_streak = 0
cur_win = cur_loss = 0
for v in pnl:
    if v > 0:
        cur_win += 1; cur_loss = 0
    elif v < 0:
        cur_loss += 1; cur_win = 0
    max_win_streak = max(max_win_streak, cur_win)
    max_loss_streak = max(max_loss_streak, cur_loss)
print(f"   最长连续盈利: {max_win_streak} 笔 | 最长连续亏损: {max_loss_streak} 笔")

print("\n3. 期望值")
exp = pnl.mean()
print(f"   单笔期望收益: {exp:+.4f} 单位")

print("\n4. 星期效应")
week = closes.groupby("星期")["净盈亏"].sum()
week_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
for i, v in week.items():
    n = (closes["星期"] == i).sum()
    print(f"   {week_name[i]}: {v:+.2f} 单位 ({n}笔)")

print("\n5. 时段效应(小时分布)")
hour = closes.groupby("小时")["净盈亏"].sum()
top_gain = hour.nlargest(3)
top_loss = hour.nsmallest(3)
print("   盈利最多的3个时段:", ", ".join(f"{h}时({v:+.2f})" for h, v in top_gain.items()))
print("   亏损最多的3个时段:", ", ".join(f"{h}时({v:+.2f})" for h, v in top_loss.items()))

print("\n6. 持仓时长近似估算(按同品种Open→Close配对)")
opens = df[df["方向"].str.contains("Open", case=False, na=False)].copy()
all_t = pd.concat([
    opens[["时间", "币种", "合约", "成交数量"]].assign(typ="O"),
    closes[["时间", "币种", "合约", "成交数量"]].assign(typ="C"),
]).sort_values("时间")
durations = []
pending = []
for _, r in all_t.iterrows():
    key = (r["币种"], r["合约"])
    if r["typ"] == "O":
        pending.append((key, r["时间"]))
    else:
        for i, (k, t0) in enumerate(pending):
            if k == key:
                durations.append((r["时间"] - t0).total_seconds() / 3600)
                pending.pop(i)
                break
if durations:
    d = np.array(durations)
    print(f"   平均持仓: {d.mean():.1f} 小时 | 中位数: {np.median(d):.1f} 小时 | 最长: {d.max():.1f} 小时")

print("\n7. 每笔风险(R倍数)分布")
risk = pd.to_numeric(closes["净盈亏"], errors="coerce").values
r_losses = risk[risk < 0]
r_wins = risk[risk > 0]
print(f"   亏损笔占总笔数: {len(r_losses)/len(closes)*100:.1f}%")
print(f"   小额亏损(0~-2 单位)占比: {len(r_losses[(r_losses > -2)])/len(closes)*100:.1f}%")

print("\n8. 若改进盈亏比到1.5(模拟): 盈亏同比例调整")
sim = np.where(pnl > 0, pnl * 1.5, pnl)
print(f"   原总盈亏: {pnl.sum():+.2f} -> 模拟盈亏: {sim.sum():+.2f} 单位")

print("\n9. 强平与主动平仓分列")
liq_mask = closes["方向"].str.contains("Liquidation", case=False, na=False)
print(f"   强平(仓位级): {int(liq_mask.sum())} 笔 | 合计 {closes.loc[liq_mask, '净盈亏'].sum():+.2f} 单位")
print(f"   主动平仓: {int((~liq_mask).sum())} 笔 | 合计 {closes.loc[~liq_mask, '净盈亏'].sum():+.2f} 单位")
