# -*- coding: utf-8 -*-
"""黑色系交互式报告 v2: 螺纹钢 基差+库存+盘面利润+正套测算+信号表"""
import akshare as ak
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")
from pyecharts import options as opts
from pyecharts.charts import Line, Bar, Scatter
from pyecharts.commons.utils import JsCode
import datetime
import os

OUT = r"./black_series/black_series_report.html"
SPOT_LOOKBACK = 180
FINANCING_RATE = 0.045
HOLD_DAYS = [30, 60]
PROCESS_FEE = 400
IRON_ORE_COEF = 1.6
COKE_COEF = 0.45

# ============ 数据 ============
print("拉取数据...")
def get_main(symbol, start="20250101"):
    df = ak.futures_main_sina(symbol=symbol, start_date=start,
                              end_date=datetime.date.today().strftime("%Y%m%d"))
    df["日期"] = pd.to_datetime(df["日期"])
    df["收盘价"] = pd.to_numeric(df["收盘价"], errors="coerce")
    return df.sort_values("日期").reset_index(drop=True)

fut = get_main("RB0")
i_fut = get_main("I0")
j_fut = get_main("J0")

trade_days = [d for d in pd.date_range(fut["日期"].iloc[-SPOT_LOOKBACK], fut["日期"].iloc[-1], freq="D")]
basis_rows = []
for d in trade_days:
    ds = d.strftime("%Y%m%d")
    try:
        df = ak.futures_spot_price(date=ds, vars_list=["RB"])
        if len(df):
            basis_rows.append(df.iloc[0])
    except Exception:
        pass
basis = pd.DataFrame(basis_rows)
basis["date"] = pd.to_datetime(basis["date"], format="%Y%m%d")
basis = basis.sort_values("date").reset_index(drop=True)
for c in ["dom_basis", "dom_basis_rate", "near_basis", "spot_price", "dominant_contract_price"]:
    basis[c] = pd.to_numeric(basis[c], errors="coerce")
basis = basis.dropna(subset=["dom_basis", "dom_basis_rate"])

inv = None
try:
    inv = ak.futures_inventory_em(symbol="螺纹钢")
    inv["日期"] = pd.to_datetime(inv["日期"])
    inv["库存"] = pd.to_numeric(inv["库存"], errors="coerce")
    inv = inv.sort_values("日期").reset_index(drop=True)
except Exception:
    pass

# ============ 指标计算 ============
last_price = fut["收盘价"].iloc[-1]
last_date = fut["日期"].iloc[-1].date()
last_basis = basis["dom_basis"].iloc[-1]
last_rate = basis["dom_basis_rate"].iloc[-1]
pct = (basis["dom_basis_rate"] < last_rate).mean() * 100
last_spot = basis["spot_price"].iloc[-1]
# 口径说明: 基差=期货-现货, 基差<0 即期货贴水(现货升水)
neg_basis_days = (basis["dom_basis"] < 0).mean() * 100
mean_basis = basis["dom_basis"].mean()

# 正套测算
arbs = {}
for days in HOLD_DAYS:
    financing = last_spot * FINANCING_RATE * days / 365
    row = {}
    for name, target in [("收敛至样本均值", mean_basis), ("收敛至平水", 0.0), ("升水20元", 20.0), ("升水50元", 50.0)]:
        # 正套盈亏 = 初始基差 - 目标基差(基差=期货-现货)
        net = (last_basis - target) - financing
        row[name] = net
    row["盈亏平衡基差"] = last_basis - financing
    arbs[days] = (financing, row)

# 盘面利润
profit_df = fut[["日期", "收盘价"]].merge(i_fut[["日期", "收盘价"]], on="日期", suffixes=("_rb", "_i"))
profit_df = profit_df.merge(j_fut[["日期", "收盘价"]], on="日期").rename(columns={"收盘价": "收盘价_j"})
profit_df["盘面利润"] = profit_df["收盘价_rb"] - IRON_ORE_COEF * profit_df["收盘价_i"] - COKE_COEF * profit_df["收盘价_j"] - PROCESS_FEE
profit_df = profit_df.dropna(subset=["盘面利润"])
last_profit = profit_df["盘面利润"].iloc[-1]

# 库存变化
if inv is not None and len(inv) >= 2:
    inv_30d = inv[inv["日期"] >= inv["日期"].max() - pd.Timedelta(days=30)]
    d_inv = inv_30d["库存"].iloc[-1] - inv_30d["库存"].iloc[0] if len(inv_30d) >= 2 else 0
    last_inv = inv["库存"].iloc[-1]
else:
    d_inv, last_inv = 0, 0

# 信号
sig_rows = []
sig_rows.append(("S1 基差修复观察", "✅ 触发" if (d_inv < 0 and pct < 30) else "⏸ 未触发",
                 f"去库({d_inv:+.0f}) + 基差率低分位({pct:.0f}%) → 现货走强预期,期货贴水有望修复,关注反套/锁价机会"))
sig_rows.append(("S2 收敛止盈", "✅ 触发" if pct > 70 else "⏸ 未触发",
                 f"基差率分位({pct:.0f}%)过高 → 基差修复接近完成,反套止盈/离场;正套观察(当前绝对基差小,收敛空间有限)"))
sig_rows.append(("S3 基差修复受阻", "✅ 触发" if (d_inv > 0 and pct < 30) else "⏸ 未触发",
                 "累库 + 期货深贴水 → 基本面偏弱,基差修复受阻风险"))
sig_rows.append(("S4 减产预期", "✅ 触发" if last_profit < 0 else "⏸ 未触发",
                 f"盘面利润 {last_profit:+.0f} 元/吨 → 钢厂亏损,减产预期升温,关注供应收缩"))
sig_rows.append(("S5 增产压力", "✅ 触发" if last_profit > 500 else "⏸ 未触发",
                 f"盘面利润 {last_profit:+.0f} 元/吨 → 钢厂高利润,增产动力强,关注供应压力"))

# ============ 图表 ============
line_price = (
    Line(init_opts=opts.InitOpts(width="1200px", height="420px"))
    .add_xaxis([str(d.date()) for d in fut["日期"]])
    .add_yaxis("期货主力收盘价(元/吨)", [round(float(v), 1) for v in fut["收盘价"]],
               is_smooth=True, symbol="none", color="#1f77b4")
    .set_global_opts(
        title_opts=opts.TitleOpts(title="螺纹钢期货主力收盘价(2025-2026)"),
        datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100), opts.DataZoomOpts(type_="inside"), opts.DataZoomOpts(type_="slider", orient="vertical", yaxis_index=0)],
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, interval=20, font_size=9)),
        yaxis_opts=opts.AxisOpts(name="元/吨", splitline_opts=opts.SplitLineOpts(is_show=True)),
        tooltip_opts=opts.TooltipOpts(trigger="axis"))
)

line_basis = (
    Bar(init_opts=opts.InitOpts(width="1200px", height="360px"))
    .add_xaxis([str(d.date()) for d in basis["date"]])
    .add_yaxis("基差(期货-现货,元/吨)", [round(float(v), 1) for v in basis["dom_basis"]],
               itemstyle_opts=opts.ItemStyleOpts(
                   color=JsCode("params => params.value >= 0 ? '#2ca02c' : '#d62728'")))
    .set_global_opts(
        title_opts=opts.TitleOpts(title="螺纹钢基差(期货-现货主力)"),
        datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100), opts.DataZoomOpts(type_="inside"), opts.DataZoomOpts(type_="slider", orient="vertical", yaxis_index=0)],
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, interval=10, font_size=9)),
        yaxis_opts=opts.AxisOpts(name="元/吨", splitline_opts=opts.SplitLineOpts(is_show=True)),
        tooltip_opts=opts.TooltipOpts(trigger="axis"))
)

line_rate = (
    Line(init_opts=opts.InitOpts(width="1200px", height="340px"))
    .add_xaxis([str(d.date()) for d in basis["date"]])
    .add_yaxis("基差率(%)", [round(float(v) * 100, 2) for v in basis["dom_basis_rate"]],
               is_smooth=True, color="#9467bd", symbol="circle", symbol_size=5,
               markline_opts=opts.MarkLineOpts(data=[opts.MarkLineItem(y=0, name="平水线"),
                                                     opts.MarkLineItem(y=float(last_rate * 100), name=f"当前 {last_rate*100:+.2f}% ({pct:.0f}%分位)")]))
    .set_global_opts(
        title_opts=opts.TitleOpts(title=f"螺纹钢基差率走势(当前处于近{len(basis)}日{pct:.0f}%分位)"),
        datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100), opts.DataZoomOpts(type_="inside"), opts.DataZoomOpts(type_="slider", orient="vertical", yaxis_index=0)],
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, interval=10, font_size=9)),
        yaxis_opts=opts.AxisOpts(name="%", splitline_opts=opts.SplitLineOpts(is_show=True)),
        tooltip_opts=opts.TooltipOpts(trigger="axis"))
)

hist_basis = (
    Bar(init_opts=opts.InitOpts(width="1200px", height="340px"))
    .add_xaxis([f"{lo:.1f}~{hi:.1f}%" for lo, hi in
                zip(np.histogram(basis["dom_basis_rate"] * 100, bins=25)[1][:-1],
                    np.histogram(basis["dom_basis_rate"] * 100, bins=25)[1][1:])])
    .add_yaxis("天数", [int(v) for v in np.histogram(basis["dom_basis_rate"] * 100, bins=25)[0]],
               itemstyle_opts=opts.ItemStyleOpts(color="#9467bd"))
    .set_global_opts(
        title_opts=opts.TitleOpts(title=f"基差率分布(近{len(basis)}日,当前{last_rate*100:+.2f}% 处于{pct:.0f}%分位)"),
        datazoom_opts=[opts.DataZoomOpts(type_="inside"), opts.DataZoomOpts(type_="slider", orient="vertical", yaxis_index=0)],
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, font_size=9)),
        yaxis_opts=opts.AxisOpts(name="天数", splitline_opts=opts.SplitLineOpts(is_show=True)),
        tooltip_opts=opts.TooltipOpts(trigger="axis"))
)

line_profit = (
    Line(init_opts=opts.InitOpts(width="1200px", height="360px"))
    .add_xaxis([str(d.date()) for d in profit_df["日期"]])
    .add_yaxis("盘面利润(元/吨)", [round(float(v), 0) for v in profit_df["盘面利润"]],
               is_smooth=True, color="#ff7f0e", symbol="circle", symbol_size=4,
               markline_opts=opts.MarkLineOpts(data=[opts.MarkLineItem(y=0, name="盈亏线"),
                                                     opts.MarkLineItem(y=float(last_profit), name=f"当前 {last_profit:+.0f}")]))
    .set_global_opts(
        title_opts=opts.TitleOpts(title="螺纹钢盘面利润估算(螺纹-1.6×铁矿-0.45×焦炭-加工费)"),
        datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100), opts.DataZoomOpts(type_="inside"), opts.DataZoomOpts(type_="slider", orient="vertical", yaxis_index=0)],
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, interval=20, font_size=9)),
        yaxis_opts=opts.AxisOpts(name="元/吨", splitline_opts=opts.SplitLineOpts(is_show=True)),
        tooltip_opts=opts.TooltipOpts(trigger="axis"))
)

charts = [line_price, line_basis, line_rate, hist_basis, line_profit]
if inv is not None:
    line_inv = (
        Line(init_opts=opts.InitOpts(width="1200px", height="340px"))
        .add_xaxis([str(d.date()) for d in inv["日期"]])
        .add_yaxis("库存", [round(float(v), 0) for v in inv["库存"]],
                   is_smooth=True, color="#d62728", symbol="circle", symbol_size=5)
        .set_global_opts(
            title_opts=opts.TitleOpts(title="螺纹钢库存走势"),
            datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100), opts.DataZoomOpts(type_="inside"), opts.DataZoomOpts(type_="slider", orient="vertical", yaxis_index=0)],
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, interval=6, font_size=9)),
            yaxis_opts=opts.AxisOpts(name="库存", splitline_opts=opts.SplitLineOpts(is_show=True)),
            tooltip_opts=opts.TooltipOpts(trigger="axis"))
    )
    charts.insert(4, line_inv)
    merged = pd.merge(fut[["日期", "收盘价"]], inv[["日期", "库存"]], on="日期", how="inner")
    if len(merged) > 10:
        corr = merged["收盘价"].corr(merged["库存"])
        scat = (
            Scatter(init_opts=opts.InitOpts(width="1200px", height="380px"))
            .add_xaxis([str(round(float(v), 0)) for v in merged["库存"]])
            .add_yaxis("收盘价(元/吨)",
                       [[round(float(x), 0), round(float(y), 1)] for x, y in zip(merged["库存"], merged["收盘价"])],
                       symbol_size=8, color="#1f77b4")
            .set_global_opts(
                title_opts=opts.TitleOpts(title=f"螺纹钢价格与库存相关性 (r={corr:.2f})"),
                datazoom_opts=[opts.DataZoomOpts(type_="inside"), opts.DataZoomOpts(type_="slider", orient="vertical", yaxis_index=0)],
                xaxis_opts=opts.AxisOpts(name="库存", type_="value", splitline_opts=opts.SplitLineOpts(is_show=True)),
                yaxis_opts=opts.AxisOpts(name="收盘价(元/吨)", splitline_opts=opts.SplitLineOpts(is_show=True)),
                tooltip_opts=opts.TooltipOpts(trigger="item"))
        )
        charts.append(scat)
        if corr >= 0.5:
            rel_desc = ("中等偏强正相关——库存高时价格通常也偏高,反映贸易商\"涨价补库、跌价去库\"的库存行为,"
                        "库存可作为价格方向的辅助参考")
        elif corr >= 0.2:
            rel_desc = "弱正相关——库存与价格存在一定同向关系,仅作辅助参考"
        elif corr <= -0.2:
            rel_desc = "负相关——库存与价格反向,累库伴随价格走弱,关注累库的供应压力"
        else:
            rel_desc = ("近乎无相关——价格与库存表观脱钩,单看库存难以推断价格方向,"
                        "需结合基差/盘面利润等维度交叉验证")
        charts.append(("<div style='padding:6px 4px 14px;font-size:12px;color:#888;'>"
                       f"读图说明：每个点=某天的(库存,价格)配对；r={corr:.2f}为{rel_desc}"
                       "（相关≠因果,且为水平值相关,仅作参考）。</div>"))

# ============ HTML ============
arb_html = ""
for days, (financing, row) in arbs.items():
    arb_html += f"""<p><b>持有 {days} 天(资金成本 {financing:.1f} 元/吨,年化{FINANCING_RATE*100:.1f}%):</b>
    收敛至平水净收益 {row['收敛至平水']:+.1f} 元/吨 | 升水20元 {row['升水20元']:+.1f} | 升水50元 {row['升水50元']:+.1f} |
    盈亏平衡基差 {row['盈亏平衡基差']:+.1f} 元/吨</p>"""

sig_html = "".join(
    f"<tr><td>{n}</td><td>{s}</td><td>{d}</td></tr>" for n, s, d in sig_rows)

html_head = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>黑色系研究报告: 螺纹钢</title>
<style>
body {{ font-family: "Microsoft YaHei", sans-serif; background: #f7f8fa; margin: 0; padding: 20px; }}
.container {{ max-width: 1240px; margin: 0 auto; }}
h1 {{ text-align: center; color: #222; }}
.sub {{ text-align: center; color: #888; margin-bottom: 24px; }}
.cards {{ display: flex; flex-wrap: wrap; gap: 14px; justify-content: center; margin-bottom: 28px; }}
.card {{ background: #fff; border-radius: 10px; padding: 16px 22px; min-width: 160px; text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
.card .num {{ font-size: 20px; font-weight: bold; color: #222; }}
.card .lbl {{ font-size: 12px; color: #888; margin-top: 4px; }}
.chart {{ background: #fff; border-radius: 10px; padding: 12px 8px; margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
.conclusion {{ background: #fff; border-radius: 10px; padding: 18px 22px; box-shadow: 0 1px 4px rgba(0,0,0,.08); line-height: 1.9; font-size: 14px; }}
table {{ border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 13px; }}
td, th {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
th {{ background: #f0f2f5; }}
</style></head>
<body><div class="container">
<h1>黑色系商品研究: 螺纹钢基差·库存·盘面利润</h1>
<div class="sub">数据截至 {last_date} &nbsp;|&nbsp; 数据源: akshare(期货/现货/库存)</div>
<div class="cards">
  <div class="card"><div class="num">{last_price}</div><div class="lbl">期货主力 (元/吨)</div></div>
  <div class="card"><div class="num">{last_basis:+.0f}</div><div class="lbl">最新基差 (元/吨)</div></div>
  <div class="card"><div class="num">{last_rate*100:+.2f}%</div><div class="lbl">最新基差率</div></div>
  <div class="card"><div class="num">{pct:.0f}%</div><div class="lbl">基差率历史分位(近{len(basis)}日)</div></div>
  <div class="card"><div class="num">{last_profit:+.0f}</div><div class="lbl">盘面利润 (元/吨)</div></div>
  <div class="card"><div class="num">{last_inv:,.0f}</div><div class="lbl">库存 ({d_inv:+.0f}/30日)</div></div>
</div>
"""

charts_html = "".join(c if isinstance(c, str) else f'<div class="chart">{c.render_embed()}</div>' for c in charts)

html_foot = f"""<div class="conclusion">
<h2>正套损益测算(买入现货+卖出期货)</h2>
{arb_html}
<p><b>结论</b>: 当前基差 {last_basis:+.0f} 元/吨,基差率 {last_rate*100:+.2f}% 处于近{len(basis)}日的 {pct:.0f}% 分位。正套盈亏=初始基差-目标基差-资金成本,盈亏平衡基差为 {arbs[30][1]['盈亏平衡基差']:+.1f} 元/吨(30天)。按"收敛至样本均值"情景(近{len(basis)}日均值 {mean_basis:+.0f} 元/吨)测算净收益空间更大,但依赖基差向均值回归的假设;按保守的"收敛至平水"情景,30天净收益约 {arbs[30][1]['收敛至平水']:+.1f} 元/吨,仅薄利。注意:测算仅计资金成本,未计仓储/增值税/交割费用,实际净收益更低;基差取自主力连续合约,换月存在跳变,结果为近似口径。</p>

<h2>跟踪信号触发状态</h2>
<table>
<tr><th>信号</th><th>状态</th><th>逻辑</th></tr>
{sig_html}
</table>

<h2>研究结论</h2>
<p><b>1. 基差结构</b>: 基差率 {last_rate*100:+.2f}% 处于近{len(basis)}日 {pct:.0f}% 分位(近{len(basis)}日 {neg_basis_days:.0f}% 时间为期货贴水/现货升水),当前{('期货贴水、现货升水' if last_basis < 0 else '期货升水、现货贴水')},基差相对年内低点已有{('明显' if abs(last_basis) < 30 else '大幅')}修复。</p>
<p><b>2. 库存周期</b>: 最新库存 {last_inv:,.0f},近30日{'累库' if d_inv > 0 else '去库'} {d_inv:+.0f},{('累库压制现货' if d_inv > 0 else '去库支撑现货')},该信号需与基差方向交叉验证。</p>
<p><b>3. 盘面利润</b>: {last_profit:+.0f} 元/吨,{('处于偏高水平,钢厂增产动力强(S5触发)' if last_profit > 500 else '处于盈亏线附近' if last_profit < 100 else '处于中性区间')},供应端压力需跟踪。</p>
<p><b>4. 操作含义</b>: 以"基差分位 + 库存拐点 + 盘面利润"三维信号表为日常监控工具,任一维度变化触发复核——结论是动态的,框架是常驻的。</p>
</div>
</div></body></html>"""

html = html_head + charts_html + html_foot
with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print("报告已生成:", OUT)
