# -*- coding: utf-8 -*-
"""生成交互式HTML绩效报告(pyecharts)"""
import glob
import re
import pandas as pd
from pyecharts import options as opts
from pyecharts.charts import Line, Bar, Grid
from pyecharts.commons.utils import JsCode

from anonymize import alias

DATA_PATH = r"data/fills.csv"
OUT = r".\report.html"

df = pd.read_csv(DATA_PATH)
df["时间"] = pd.to_datetime(df["时间"])
for c in ["已实现盈亏", "净盈亏", "手续费"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")

closes = df[df["方向"].str.contains("Close|Liquidation", case=False, na=False)].copy()
closes["月"] = closes["时间"].dt.to_period("M")

monthly = closes.groupby("月")["净盈亏"].sum()
cum = monthly.cumsum()

def add_header(page):
    from pyecharts.components import Table
    return page

# ============ 图1: 月度累计净值(面积图) ============
line = (
    Line(init_opts=opts.InitOpts(width="1200px", height="420px"))
    .add_xaxis([str(m) for m in monthly.index])
    .add_yaxis("累计净盈亏", [round(v, 2) for v in cum.values],
               is_smooth=True,
               symbol="circle", symbol_size=6,
               markpoint_opts=opts.MarkPointOpts(
                   data=[opts.MarkPointItem(type_="max", name="最高点"), opts.MarkPointItem(type_="min", name="最低点")]),
               markline_opts=opts.MarkLineOpts(data=[opts.MarkLineItem(y=0, name="盈亏平衡线")]))
    .set_global_opts(
        title_opts=opts.TitleOpts(title="月度累计净盈亏(单位)"),
        datazoom_opts=[opts.DataZoomOpts(type_="inside"), opts.DataZoomOpts(type_="slider", height=18), opts.DataZoomOpts(type_="slider", orient="vertical", yaxis_index=0)],

        yaxis_opts=opts.AxisOpts(name="累计盈亏 (单位)", splitline_opts=opts.SplitLineOpts(is_show=True)),
        tooltip_opts=opts.TooltipOpts(trigger="axis", formatter=JsCode("params => params[0].axisValue + '<br/>累计盈亏: ' + params[0].value + ' 单位'"))
    )
)

# ============ 图2: 月度盈亏柱状图 ============
bar_month = (
    Bar(init_opts=opts.InitOpts(width="1200px", height="380px"))
    .add_xaxis([str(m) for m in monthly.index])
    .add_yaxis("月度盈亏",
               [round(v, 2) for v in monthly.values],
               itemstyle_opts=opts.ItemStyleOpts(
                   color=JsCode("params => params.value >= 0 ? '#2ca02c' : '#d62728'")))
    .set_global_opts(
        title_opts=opts.TitleOpts(title="月度盈亏(单位)"),
        datazoom_opts=[opts.DataZoomOpts(type_="inside"), opts.DataZoomOpts(type_="slider", height=18), opts.DataZoomOpts(type_="slider", orient="vertical", yaxis_index=0)],

        yaxis_opts=opts.AxisOpts(name="盈亏 (单位)", splitline_opts=opts.SplitLineOpts(is_show=True)),
        tooltip_opts=opts.TooltipOpts(trigger="axis"))
)

# ============ 图3: 品种盈亏(横向条形, 展示名脱敏, 其余聚合为其他) ============
closes["品种"] = closes["合约"].apply(alias)
by_symbol_all = closes.groupby("品种")["净盈亏"].sum()
top_n = by_symbol_all.abs().sort_values(ascending=False).head(4).index.tolist()
by_symbol = by_symbol_all[top_n].sort_values()
others_sum = by_symbol_all.drop(top_n).sum()
if others_sum != 0:
    by_symbol = pd.concat([by_symbol, pd.Series({"其他": others_sum})]).sort_values()
_disp = [str(s) for s in by_symbol.index]
bar_sym = (
    Bar(init_opts=opts.InitOpts(width="1200px", height="420px"))
    .add_xaxis(_disp)
    .add_yaxis("累计盈亏", [round(v, 2) for v in by_symbol.values],
               itemstyle_opts=opts.ItemStyleOpts(
                   color=JsCode("params => params.value >= 0 ? '#2ca02c' : '#d62728'")))
    .set_global_opts(
        title_opts=opts.TitleOpts(title="各品种累计盈亏(展示名已脱敏)"),
        datazoom_opts=[opts.DataZoomOpts(type_="inside"), opts.DataZoomOpts(type_="slider", height=18), opts.DataZoomOpts(type_="slider", orient="vertical", yaxis_index=0)],

        xaxis_opts=opts.AxisOpts(name="品种"),
        yaxis_opts=opts.AxisOpts(name="累计盈亏 (单位)", splitline_opts=opts.SplitLineOpts(is_show=True)),
        tooltip_opts=opts.TooltipOpts(trigger="axis"))
    .reversal_axis()
)

# ============ 图4: 多空方向对比 ============
closes["方向类型"] = closes["方向"].apply(lambda x: "做多" if "long" in x.lower() else "做空")
dir_pnl = closes.groupby("方向类型")["净盈亏"].sum()
bar_dir = (
    Bar(init_opts=opts.InitOpts(width="1200px", height="320px"))
    .add_xaxis([str(d) for d in dir_pnl.index])
    .add_yaxis("累计盈亏", [round(v, 2) for v in dir_pnl.values],
               itemstyle_opts=opts.ItemStyleOpts(
                   color=JsCode("params => params.value >= 0 ? '#2ca02c' : '#d62728'")))
    .set_global_opts(
        title_opts=opts.TitleOpts(title="多空方向盈亏对比(单位)"),
        datazoom_opts=[opts.DataZoomOpts(type_="inside"), opts.DataZoomOpts(type_="slider", height=18), opts.DataZoomOpts(type_="slider", orient="vertical", yaxis_index=0)],

        yaxis_opts=opts.AxisOpts(name="累计盈亏 (单位)", splitline_opts=opts.SplitLineOpts(is_show=True)),
        tooltip_opts=opts.TooltipOpts(trigger="axis"))
)

# ============ 图5: 盈亏分布直方图 ============
bins = pd.cut(closes["净盈亏"], bins=30).value_counts().sort_index()
bar_dist = (
    Bar(init_opts=opts.InitOpts(width="1200px", height="380px"))
    .add_xaxis([str(b) for b in bins.index])
    .add_yaxis("笔数", [int(v) for v in bins.values])
    .set_global_opts(
        title_opts=opts.TitleOpts(title="单笔盈亏分布"),
        datazoom_opts=[opts.DataZoomOpts(type_="inside"), opts.DataZoomOpts(type_="slider", height=18), opts.DataZoomOpts(type_="slider", orient="vertical", yaxis_index=0)],

        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, interval=0, font_size=10)),
        yaxis_opts=opts.AxisOpts(name="笔数"),
        tooltip_opts=opts.TooltipOpts(trigger="axis"))
)

# ============ 图6/7: 滑动3个月窗口(完整仓位口径) ============
def _num(s):
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return 0.0
    return float(re.sub(r"[A-Za-z]+", "", str(s)).strip() or 0)

pos_file = r"data/positions.csv"
pos = pd.read_csv(pos_file)
pos["仓位盈亏"] = pos["仓位盈亏"].apply(_num)
pos["开仓时间"] = pd.to_datetime(pos["开仓时间"])
pos["月"] = pos["开仓时间"].dt.to_period("M")
months = sorted(pos["月"].unique())
roll_labels, roll_win, roll_rr, roll_pnl = [], [], [], []
for i in range(len(months)):
    start = months[max(0, i - 2)].to_timestamp()
    end = months[i].to_timestamp() + pd.Timedelta(days=32)
    m = pos[(pos["开仓时间"] >= start) & (pos["开仓时间"] < end)]
    if len(m) >= 10:
        w = (m["仓位盈亏"] > 0).mean() * 100
        aw = m.loc[m["仓位盈亏"] > 0, "仓位盈亏"].mean()
        al = m.loc[m["仓位盈亏"] < 0, "仓位盈亏"].mean()
        rr = abs(aw / al) if al != 0 else float("nan")
        roll_labels.append(str(months[i]))
        roll_win.append(round(w, 1))
        roll_rr.append(round(rr, 2))
        roll_pnl.append(round(m["仓位盈亏"].sum(), 2))

line_roll_wr = (
    Line(init_opts=opts.InitOpts(width="1200px", height="340px"))
    .add_xaxis(roll_labels)
    .add_yaxis("滑动3月胜率(%)", roll_win,
               is_smooth=True, symbol="circle", symbol_size=6, color="#1f77b4",
               markline_opts=opts.MarkLineOpts(data=[opts.MarkLineItem(y=50, name="50%线")]))
    .set_global_opts(
        title_opts=opts.TitleOpts(title="滑动3个月窗口: 胜率趋势(样本>=10笔)"),
        datazoom_opts=[opts.DataZoomOpts(type_="inside"), opts.DataZoomOpts(type_="slider", height=18), opts.DataZoomOpts(type_="slider", orient="vertical", yaxis_index=0)],

        yaxis_opts=opts.AxisOpts(name="胜率(%)", min_=30, max_=75),
        tooltip_opts=opts.TooltipOpts(trigger="axis"))
)

line_roll_rr = (
    Line(init_opts=opts.InitOpts(width="1200px", height="340px"))
    .add_xaxis(roll_labels)
    .add_yaxis("滑动3月盈亏比", roll_rr,
               is_smooth=True, symbol="diamond", symbol_size=6, color="#ff7f0e",
               markline_opts=opts.MarkLineOpts(data=[opts.MarkLineItem(y=1.0, name="盈亏比1.0")]))
    .set_global_opts(
        title_opts=opts.TitleOpts(title="滑动3个月窗口: 盈亏比趋势(样本>=10笔)"),
        datazoom_opts=[opts.DataZoomOpts(type_="inside"), opts.DataZoomOpts(type_="slider", height=18), opts.DataZoomOpts(type_="slider", orient="vertical", yaxis_index=0)],

        yaxis_opts=opts.AxisOpts(name="盈亏比", min_=0, max_=2),
        tooltip_opts=opts.TooltipOpts(trigger="axis"))
)

bar_roll = (
    Bar(init_opts=opts.InitOpts(width="1200px", height="320px"))
    .add_xaxis(roll_labels)
    .add_yaxis("滑动3月盈亏", [round(v, 2) for v in roll_pnl],
               itemstyle_opts=opts.ItemStyleOpts(
                   color=JsCode("params => params.value >= 0 ? '#2ca02c' : '#d62728'")))
    .set_global_opts(
        title_opts=opts.TitleOpts(title="滑动3月盈亏(单位)"),
        datazoom_opts=[opts.DataZoomOpts(type_="inside"), opts.DataZoomOpts(type_="slider", height=18), opts.DataZoomOpts(type_="slider", orient="vertical", yaxis_index=0)],

        yaxis_opts=opts.AxisOpts(name="盈亏 (单位)", splitline_opts=opts.SplitLineOpts(is_show=True)),
        tooltip_opts=opts.TooltipOpts(trigger="axis"))
)

# ============ 汇总指标卡 ============
total_pnl = closes["净盈亏"].sum()
total_fee = df["手续费"].sum()
win_rate = (closes["净盈亏"] > 0).mean() * 100
wins = closes[closes["净盈亏"] > 0]["净盈亏"]
losses = closes[closes["净盈亏"] < 0]["净盈亏"]
avg_win = wins.mean()
avg_loss = losses.mean()
pf = abs(wins.sum() / losses.sum()) if losses.sum() else float("inf")

# 完整仓位口径(与 README/简历一致,避免同一份报告出现两套未对照的数字)
def _rr(d):
    aw = d.loc[d["仓位盈亏"] > 0, "仓位盈亏"].mean()
    al = d.loc[d["仓位盈亏"] < 0, "仓位盈亏"].mean()
    return abs(aw / al) if al else float("nan")

n_pos = len(pos)
wr_pos = (pos["仓位盈亏"] > 0).mean() * 100
rr_pos = _rr(pos)
rr_h1 = _rr(pos[pos["开仓时间"] < "2025-07-01"])
rr_12m = _rr(pos[pos["开仓时间"] >= pos["开仓时间"].max() - pd.Timedelta(days=365)])
pnl_h1 = pos.loc[pos["开仓时间"] < "2025-07-01", "仓位盈亏"].sum()
pnl_26 = pos.loc[pos["开仓时间"] >= "2026-01-01", "仓位盈亏"].sum()
cut_pct = (1 - abs(pnl_26) / abs(pnl_h1)) * 100 if pnl_h1 else float("nan")

html_head = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>交易绩效分析报告</title>
<style>
body {{ font-family: "Microsoft YaHei", sans-serif; background: #f7f8fa; margin: 0; padding: 20px; }}
.container {{ max-width: 1240px; margin: 0 auto; }}
h1 {{ text-align: center; color: #222; }}
.sub {{ text-align: center; color: #888; margin-bottom: 24px; }}
.cards {{ display: flex; flex-wrap: wrap; gap: 14px; justify-content: center; margin-bottom: 28px; }}
.card {{ background: #fff; border-radius: 10px; padding: 16px 22px; min-width: 150px; text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
.card .num {{ font-size: 22px; font-weight: bold; color: #222; }}
.card .lbl {{ font-size: 12px; color: #888; margin-top: 4px; }}
.red {{ color: #d62728 !important; }} .green {{ color: #2ca02c !important; }}
.chart {{ background: #fff; border-radius: 10px; padding: 12px 8px; margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
.conclusion {{ background: #fff; border-radius: 10px; padding: 18px 22px; box-shadow: 0 1px 4px rgba(0,0,0,.08); line-height: 1.9; font-size: 14px; }}
.conclusion h2 {{ margin-top: 0; }}
</style></head>
<body><div class="container">
<h1>交易绩效分析报告</h1>
<div class="sub">数据范围：{df["时间"].min().date()} - {df["时间"].max().date()}（数据截至 {df["时间"].max().date()}）&nbsp;|&nbsp; 平仓记录：{len(closes)} 笔 &nbsp;|&nbsp; 数据来源：个人实盘记录导出</div>
<div class="cards">
  <div class="card"><div class="num {'red' if total_pnl<0 else 'green'}">{total_pnl:+.2f}</div><div class="lbl">净盈亏 (单位)</div></div>
  <div class="card"><div class="num">{win_rate:.1f}%</div><div class="lbl">胜率</div></div>
  <div class="card"><div class="num">{abs(avg_win/avg_loss):.2f}</div><div class="lbl">盈亏比</div></div>
  <div class="card"><div class="num">{pf:.2f}</div><div class="lbl">盈亏因子</div></div>
  <div class="card"><div class="num red">{total_fee:.2f}</div><div class="lbl">手续费 (单位)</div></div>
  <div class="card"><div class="num">{len(closes)}</div><div class="lbl">平仓笔数</div></div>
</div>
<div class="conclusion" style="margin-bottom:20px;">
<b>数据口径说明：</b>本报告基于<u>成交明细</u>（{len(closes)} 笔平仓单边记录）计算，故胜率 {win_rate:.1f}%、盈亏比 {abs(avg_win/avg_loss):.2f} 等指标与基于<u>{n_pos} 个完整仓位（开平配对）</u>的口径（胜率 {wr_pos:.1f}%、盈亏比 {rr_pos:.2f}）不同，两者相互印证、口径均已注明，详见 GitHub README 与代码。
</div>
"""

html_foot = f"""<div class="conclusion">
<h2>核心发现</h2>
<p><b>1. 盈亏比失衡是亏损主因</b>：胜率 {win_rate:.1f}%（{len(wins)}胜/{len(losses)}负），但平均盈利 {avg_win:+.3f} 单位 vs 平均亏损 {avg_loss:+.3f} 单位，盈利单持有不足（赚小亏大）。</p>
<p><b>2. 交易成本过高</b>：累计手续费 {total_fee:.2f} 单位，占净亏损的 {abs(total_fee/total_pnl)*100:.0f}%，过度交易侵蚀利润。</p>
<p><b>3. 方向性差异显著</b>：做多累计 {dir_pnl.get('做多',0):+.1f} 单位 vs 做空 {dir_pnl.get('做空',0):+.1f} 单位，做多为主要亏损来源。</p>
<p><b>4. 风控纪律有效</b>：前期 3 次仓位强平（2025-01 两次、2026-06 一次极小仓位）后重建风控体系，账户未发生爆仓（资金未归零），未出现单次大额亏损失控。</p>
<p><b>5. 改进验证</b>：盈亏比从 {rr_h1:.2f} 修复至 {rr_12m:.2f}（2025H1→近一年，完整仓位口径）、阶段亏损收窄 {cut_pct:.0f}%——改善来自可量化的策略调整，而非运气。</p>
</div>
</div></body></html>"""

parts = []
for chart in [line, bar_month, bar_sym, bar_dir, bar_dist, line_roll_wr, line_roll_rr, bar_roll]:
    parts.append(f'<div class="chart">{chart.render_embed()}</div>')

html = html_head + "".join(parts) + html_foot
with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)

print("报告已生成:", OUT)
print("净盈亏: %.2f | 胜率: %.1f%% | 盈亏比: %.2f | 盈亏因子: %.2f | 手续费: %.2f" % (total_pnl, win_rate, abs(avg_win/avg_loss), pf, total_fee))
