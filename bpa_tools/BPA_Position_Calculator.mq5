//+------------------------------------------------------------------+
//|                                     BPA_Position_Calculator.mq5 |
//|                                    Copyright 2026, Antigravity   |
//+------------------------------------------------------------------+
#property copyright   "Antigravity BPA Quant"
#property link        "https://antigravity"
#property version     "2.10"
#property description "BPA 极速仓位与量化雷达 v2.1 (精简极速版)"
#property indicator_chart_window
#property indicator_plots 0

//--- 枚举定义
enum ENUM_RISK_MODE
{
   RISK_FIXED_USD = 0,     // 固定金额 (美元 USD)
   RISK_PERCENT   = 1      // 账户净值百分比 (%)
};

enum ENUM_ROUND_MODE
{
   ROUND_NEAREST = 0,     // 四舍五入到最接近的手数
   ROUND_FLOOR   = 1      // 保守向下截断 (严格确保亏损不超标)
};

enum ENUM_SAMPLE_FILTER
{
   FILTER_NONE      = 0,  // 全样本基准
   FILTER_EMA_TREND = 1   // BPA 顺均线过滤 (推荐)
};

//--- 输入参数
input group "=== 核心风控设置 ==="
input ENUM_RISK_MODE    InpRiskMode      = RISK_FIXED_USD; // 风险计算方式
input double            InpFixedRiskUSD  = 2.0;            // 单笔固定亏损金额 ($)
input double            InpRiskPercent   = 1.5;            // 单笔净值风险比例 (%)
input double            InpTargetRR1     = 1.0;            // 目标一 (1R 短线)
input double            InpTargetRR2     = 2.0;            // 目标二 (2R 波段)
input bool              InpAutoLinkTP    = true;           // 拖动时自动联动调整 TP
input ENUM_ROUND_MODE   InpRoundMode     = ROUND_FLOOR;    // 手数取整模式

input group "=== 量化回测参数 ==="
input int                InpHistoryBars   = 2000;           // 回测历史 K 线根数 (深度扩充至2000根/约两周)
input ENUM_SAMPLE_FILTER InpSampleFilter  = FILTER_EMA_TREND;// 采样过滤模式
input int                InpMaxHoldBars   = 60;             // 最大推演 K 线根数 (60根=5小时)

input group "=== 波动率设置 ==="
input int               InpATRPeriod     = 14;             // ATR 周期
input double            InpATRMul        = 1.5;            // ATR 止损推荐倍率
input int               InpADRDays       = 5;              // ADR 计算天数

input group "=== 线条样式 ==="
input color             InpColorEntry    = clrDeepSkyBlue; // 进场线
input color             InpColorSL       = clrCrimson;     // 止损线
input color             InpColorTP1      = clrGold;        // 1R 止盈线
input color             InpColorTP2      = clrLimeGreen;   // 2R 止盈线
input int               InpLineWidth     = 2;              // 线条粗细

input group "=== 紧凑精简面板布局 ==="
input ENUM_BASE_CORNER  InpPanelCorner   = CORNER_LEFT_UPPER;// 面板位置
input int               InpPanelX        = 18;             // X 偏移
input int               InpPanelY        = 18;             // Y 偏移
input int               InpPanelWidth    = 410;            // 面板宽度 (紧凑不遮挡)
input int               InpPanelHeight   = 290;            // 面板高度 (精炼利落)

//--- 常量与句柄
#define PREFIX_OBJ "BPA_CALC_"
const string OBJ_LINE_ENTRY = PREFIX_OBJ + "ENTRY";
const string OBJ_LINE_SL    = PREFIX_OBJ + "SL";
const string OBJ_LINE_TP1   = PREFIX_OBJ + "TP1";
const string OBJ_LINE_TP2   = PREFIX_OBJ + "TP2";
const string OBJ_BG         = PREFIX_OBJ + "PANEL_BG";

int handleATR = INVALID_HANDLE;
int handleEMA = INVALID_HANDLE;

//--- 回测结果结构体
struct BacktestResult
{
   int    actualBars;      // 实际扫描的历史 K 线根数
   int    sampleCount;     // 样本数
   int    wins1R;          // 1R 成功
   int    wins2R;          // 2R 成功
   int    losses;          // 止损
   double winRate1R;       // 1R 实测胜率
   double winRate2R;       // 2R 实测胜率
   double ev1R;            // 1R 数学期望
   double ev2R;            // 2R 数学期望
   double avgMins1R;       // 1R 平均分钟
   double avgMins2R;       // 2R 平均分钟
   double theoProb1R;      // 漂移理论 1R
};

//+------------------------------------------------------------------+
//| 初始化函数                                                       |
//+------------------------------------------------------------------+
int OnInit()
{
   ChartSetInteger(0, CHART_FOREGROUND, false);

   handleATR = iATR(_Symbol, _Period, InpATRPeriod);
   handleEMA = iMA(_Symbol, _Period, 20, 0, MODE_EMA, PRICE_CLOSE);

   CleanAllObjects();
   CreateLines();
   CreateDashboard();
   RecalculateAndRender();
   ChartRedraw();
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| 去初始化函数                                                     |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(handleATR != INVALID_HANDLE) IndicatorRelease(handleATR);
   if(handleEMA != INVALID_HANDLE) IndicatorRelease(handleEMA);
   CleanAllObjects();
   ChartRedraw();
}

//+------------------------------------------------------------------+
//| 计算函数 (主循环)                                                |
//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{
   RecalculateAndRender();
   return(rates_total);
}

//+------------------------------------------------------------------+
//| 图表事件处理                                                     |
//+------------------------------------------------------------------+
void OnChartEvent(const int id,
                  const long &lparam,
                  const double &dparam,
                  const string &sparam)
{
   if(id == CHARTEVENT_OBJECT_DRAG)
   {
      if(sparam == OBJ_LINE_ENTRY || sparam == OBJ_LINE_SL)
      {
         if(InpAutoLinkTP)
         {
            double entry = ObjectGetDouble(0, OBJ_LINE_ENTRY, OBJPROP_PRICE);
            double sl    = ObjectGetDouble(0, OBJ_LINE_SL, OBJPROP_PRICE);
            double slDist = MathAbs(entry - sl);
            if(slDist > 0)
            {
               double tp1 = (entry >= sl) ? (entry + slDist * InpTargetRR1) : (entry - slDist * InpTargetRR1);
               double tp2 = (entry >= sl) ? (entry + slDist * InpTargetRR2) : (entry - slDist * InpTargetRR2);
               ObjectSetDouble(0, OBJ_LINE_TP1, OBJPROP_PRICE, tp1);
               ObjectSetDouble(0, OBJ_LINE_TP2, OBJPROP_PRICE, tp2);
            }
         }
         RecalculateAndRender();
         ChartRedraw();
      }
      else if(sparam == OBJ_LINE_TP1 || sparam == OBJ_LINE_TP2)
      {
         RecalculateAndRender();
         ChartRedraw();
      }
   }
   else if(id == CHARTEVENT_CHART_CHANGE)
   {
      RecalculateAndRender();
      ChartRedraw();
   }

   ObjectSetInteger(0, OBJ_LINE_ENTRY, OBJPROP_SELECTED, true);
   ObjectSetInteger(0, OBJ_LINE_SL, OBJPROP_SELECTED, true);
   ObjectSetInteger(0, OBJ_LINE_TP1, OBJPROP_SELECTED, true);
   ObjectSetInteger(0, OBJ_LINE_TP2, OBJPROP_SELECTED, true);
}

//+------------------------------------------------------------------+
//| 创建水平线                                                       |
//+------------------------------------------------------------------+
void CreateLines()
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double cur = (ask > 0) ? ask : SymbolInfoDouble(_Symbol, SYMBOL_LAST);
   if(cur <= 0) cur = 1.0;

   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double pipSize = (_Digits == 3 || _Digits == 5) ? (10.0 * point) : point;
   if(pipSize <= 0) pipSize = 0.0001;

   double pEntry = cur;
   double pSL    = cur - 10.0 * pipSize;
   double pTP1   = cur + 10.0 * pipSize * InpTargetRR1;
   double pTP2   = cur + 10.0 * pipSize * InpTargetRR2;

   CreateHLine(OBJ_LINE_ENTRY, pEntry, InpColorEntry, InpLineWidth, STYLE_SOLID, "进场线 (单击拖动)");
   CreateHLine(OBJ_LINE_SL,    pSL,    InpColorSL,    InpLineWidth, STYLE_SOLID, "止损线 (单击拖动)");
   CreateHLine(OBJ_LINE_TP1,   pTP1,   InpColorTP1,   InpLineWidth, STYLE_DASH,  "1R 止盈线");
   CreateHLine(OBJ_LINE_TP2,   pTP2,   InpColorTP2,   InpLineWidth, STYLE_SOLID, "2R 止盈线");
}

void CreateHLine(string name, double price, color clr, int width, ENUM_LINE_STYLE style, string tooltip)
{
   ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, width);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTED, true);
   ObjectSetInteger(0, name, OBJPROP_BACK, false);
   ObjectSetString(0, name, OBJPROP_TOOLTIP, tooltip);
}

//+------------------------------------------------------------------+
//| 创建 HUD 悬浮面板 (精炼紧凑版)                                   |
//+------------------------------------------------------------------+
void CreateDashboard()
{
   ObjectCreate(0, OBJ_BG, OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, OBJ_BG, OBJPROP_CORNER, InpPanelCorner);
   ObjectSetInteger(0, OBJ_BG, OBJPROP_XDISTANCE, InpPanelX);
   ObjectSetInteger(0, OBJ_BG, OBJPROP_YDISTANCE, InpPanelY);
   ObjectSetInteger(0, OBJ_BG, OBJPROP_XSIZE, InpPanelWidth);
   ObjectSetInteger(0, OBJ_BG, OBJPROP_YSIZE, InpPanelHeight);
   ObjectSetInteger(0, OBJ_BG, OBJPROP_BGCOLOR, C'14,18,25');
   ObjectSetInteger(0, OBJ_BG, OBJPROP_BORDER_COLOR, C'55,68,88');
   ObjectSetInteger(0, OBJ_BG, OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(0, OBJ_BG, OBJPROP_BACK, false);
   ObjectSetInteger(0, OBJ_BG, OBJPROP_SELECTABLE, false);

   string labels[] = {
      "TITLE", "DIR_LOTS", "SL_VOL", "DIV_1",
      "BT_HD", "BT_1R", "BT_2R", "BT_EV",
      "DIV_2", "VERDICT", "DIV_3",
      "POS_INFO", "ACC_INFO"
   };

   for(int i = 0; i < ArraySize(labels); i++)
   {
      string name = PREFIX_OBJ + "TXT_" + labels[i];
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, InpPanelCorner);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_BACK, false);
      ObjectSetString(0, name, OBJPROP_TEXT, "");
   }
}

//+------------------------------------------------------------------+
//| 历史真实现场回测与漂移计算引擎                                   |
//+------------------------------------------------------------------+
BacktestResult RunEmpiricalBacktest(bool isBuy, double slDist, double tp1Dist, double tp2Dist, double pipScale)
{
   BacktestResult res;
   ZeroMemory(res);
   res.theoProb1R = 50.0;

   if(slDist <= 0 || tp1Dist <= 0 || tp2Dist <= 0) return res;

   int scanBars = MathMax(2000, InpHistoryBars);
   int fetchBars = scanBars + InpMaxHoldBars + 50;
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(_Symbol, _Period, 0, fetchBars, rates);
   if(copied < (InpMaxHoldBars + 50)) return res;

   double emaBuf[];
   ArraySetAsSeries(emaBuf, true);
   bool hasEMA = false;
   if(handleEMA != INVALID_HANDLE)
   {
      if(CopyBuffer(handleEMA, 0, 0, copied, emaBuf) > 0) hasEMA = true;
   }

   int periodMinutes = PeriodSeconds(_Period) / 60;
   if(periodMinutes <= 0) periodMinutes = 5;

   int total1RBars = 0;
   int total2RBars = 0;

   int startIndex = MathMin(copied - InpMaxHoldBars - 1, scanBars);
   res.actualBars = startIndex;
   for(int i = startIndex; i >= 1; i--)
   {
      if(InpSampleFilter == FILTER_EMA_TREND && hasEMA && i < ArraySize(emaBuf))
      {
         if(isBuy && rates[i].close < emaBuf[i]) continue;
         if(!isBuy && rates[i].close > emaBuf[i]) continue;
      }

      double simEntry = rates[i].close;
      double simSL  = isBuy ? (simEntry - slDist)  : (simEntry + slDist);
      double simTP1 = isBuy ? (simEntry + tp1Dist) : (simEntry - tp1Dist);
      double simTP2 = isBuy ? (simEntry + tp2Dist) : (simEntry - tp2Dist);

      bool hitSL = false;
      bool hitTP1 = false;
      bool hitTP2 = false;
      int barsTo1R = 0;
      int barsTo2R = 0;

      for(int j = i - 1; j >= MathMax(0, i - InpMaxHoldBars); j--)
      {
         int step = i - j;
         if(isBuy)
         {
            if(rates[j].low <= simSL) { hitSL = true; break; }
            if(!hitTP1 && rates[j].high >= simTP1) { hitTP1 = true; barsTo1R = step; }
            if(!hitTP2 && rates[j].high >= simTP2) { hitTP2 = true; barsTo2R = step; break; }
         }
         else
         {
            if(rates[j].high >= simSL) { hitSL = true; break; }
            if(!hitTP1 && rates[j].low <= simTP1) { hitTP1 = true; barsTo1R = step; }
            if(!hitTP2 && rates[j].low <= simTP2) { hitTP2 = true; barsTo2R = step; break; }
         }
      }

      if(hitSL || hitTP1 || hitTP2)
      {
         res.sampleCount++;
         if(hitSL && !hitTP1) res.losses++;
         if(hitTP1) { res.wins1R++; total1RBars += barsTo1R; }
         if(hitTP2) { res.wins2R++; total2RBars += barsTo2R; }
      }
   }

   if(res.sampleCount > 0)
   {
      res.winRate1R = ((double)res.wins1R / (double)res.sampleCount) * 100.0;
      res.winRate2R = ((double)res.wins2R / (double)res.sampleCount) * 100.0;

      double p1 = res.winRate1R / 100.0;
      res.ev1R = p1 * (tp1Dist / slDist) - (1.0 - p1) * 1.0;

      double p2 = res.winRate2R / 100.0;
      res.ev2R = p2 * (tp2Dist / slDist) - (1.0 - p2) * 1.0;

      if(res.wins1R > 0) res.avgMins1R = ((double)total1RBars / (double)res.wins1R) * periodMinutes;
      if(res.wins2R > 0) res.avgMins2R = ((double)total2RBars / (double)res.wins2R) * periodMinutes;
   }

   // 漂移理论概率计算
   int statBars = MathMin(50, copied - 1);
   double sumDelta = 0.0;
   for(int k = 0; k < statBars; k++) sumDelta += (rates[k].close - rates[k+1].close) / pipScale;
   double mu = sumDelta / (double)statBars;
   double sumSq = 0.0;
   for(int k = 0; k < statBars; k++) sumSq += MathPow(((rates[k].close - rates[k+1].close) / pipScale) - mu, 2.0);
   double var = (statBars > 1) ? (sumSq / (double)(statBars - 1)) : 1.0;
   if(var < 0.001) var = 0.001;

   double v = isBuy ? mu : -mu;
   double gamma = (2.0 * v) / var;
   double slPips  = slDist / pipScale;
   double tp1Pips = tp1Dist / pipScale;
   if(MathAbs(gamma) < 0.0001)
      res.theoProb1R = 50.0;
   else
   {
      double e_sl = MathExp(-MathMin(20.0, MathMax(-20.0, gamma * slPips)));
      double e_tot = MathExp(-MathMin(20.0, MathMax(-20.0, gamma * (tp1Pips + slPips))));
      if(MathAbs(1.0 - e_tot) > 0.0001) res.theoProb1R = ((1.0 - e_sl) / (1.0 - e_tot)) * 100.0;
   }
   res.theoProb1R = MathMin(90.0, MathMax(10.0, res.theoProb1R));

   return res;
}

//+------------------------------------------------------------------+
//| 核心计算并更新极简渲染                                           |
//+------------------------------------------------------------------+
void RecalculateAndRender()
{
   double entry = ObjectGetDouble(0, OBJ_LINE_ENTRY, OBJPROP_PRICE);
   double sl    = ObjectGetDouble(0, OBJ_LINE_SL, OBJPROP_PRICE);
   double tp1   = ObjectGetDouble(0, OBJ_LINE_TP1, OBJPROP_PRICE);
   double tp2   = ObjectGetDouble(0, OBJ_LINE_TP2, OBJPROP_PRICE);

   if(entry <= 0 || sl <= 0) return;

   bool isBuy = (entry >= sl);
   double slDist  = MathAbs(entry - sl);
   double tp1Dist = MathAbs(tp1 - entry);
   double tp2Dist = MathAbs(tp2 - entry);

   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double pipScale = (_Digits == 3 || _Digits == 5) ? (10.0 * point) : point;
   if(pipScale <= 0) pipScale = 0.0001;

   double slPips  = slDist / pipScale;
   double tp1Pips = tp1Dist / pipScale;
   double tp2Pips = tp2Dist / pipScale;

   // 1. 获取 ATR 波动率
   double atrPips = 0.0;
   if(handleATR != INVALID_HANDLE)
   {
      double atrBuf[1];
      if(CopyBuffer(handleATR, 0, 0, 1, atrBuf) > 0) atrPips = atrBuf[0] / pipScale;
   }
   double slToATR = (atrPips > 0) ? (slPips / atrPips) : 1.0;

   // 2. 获取 ADR 日均波幅
   MqlRates dailyRates[];
   ArraySetAsSeries(dailyRates, true);
   double todayRangePips = 0.0, adrPips = 0.0;
   if(CopyRates(_Symbol, PERIOD_D1, 0, InpADRDays + 1, dailyRates) >= (InpADRDays + 1))
   {
      todayRangePips = (dailyRates[0].high - dailyRates[0].low) / pipScale;
      double sumRange = 0.0;
      for(int i = 1; i <= InpADRDays; i++) sumRange += (dailyRates[i].high - dailyRates[i].low) / pipScale;
      adrPips = sumRange / (double)InpADRDays;
   }
   if(adrPips <= 0) adrPips = 60.0;
   double remainingRangePips = MathMax(0.0, adrPips - todayRangePips);
   double adrUsagePct = (adrPips > 0) ? (todayRangePips / adrPips * 100.0) : 0.0;

   // 3. 运行实测回测
   BacktestResult bt = RunEmpiricalBacktest(isBuy, slDist, tp1Dist, tp2Dist, pipScale);

   // 4. 量化裁决 (短小精悍)
   string verdictStr = "";
   color verdictClr = C'80,230,120';
   if(bt.winRate2R >= 48.0 && remainingRangePips >= tp2Pips)
   {
      verdictStr = StringFormat(">> 裁决: [2R实测%.0f%% · 充沛死拿] (剩空间%.1f点>2R)", bt.winRate2R, remainingRangePips);
      verdictClr = C'50,235,110';
   }
   else if(bt.winRate2R < 40.0 || bt.winRate1R < 55.0)
   {
      verdictStr = StringFormat(">> 裁决: [低期望架构 · 禁死拿2R] (实测2R胜率仅%.0f%%)", bt.winRate2R);
      verdictClr = clrOrangeRed;
   }
   else
   {
      verdictStr = StringFormat(">> 裁决: [1R平半推保本] (1R实测%.0f%%，打到1R锁一半)", bt.winRate1R);
      verdictClr = C'245,195,65';
   }

   // 5. 风控与手数
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity <= 0) equity = AccountInfoDouble(ACCOUNT_BALANCE);
   if(equity <= 0) equity = 140.0;

   double targetRiskUSD = InpFixedRiskUSD;
   if(InpRiskMode == RISK_PERCENT) targetRiskUSD = equity * (InpRiskPercent / 100.0);

   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tickSize <= 0) tickSize = point;
   if(tickValue <= 0) tickValue = 1.0;

   double lossPerLot = (slDist / tickSize) * tickValue;
   double rawLots = (lossPerLot > 0) ? (targetRiskUSD / lossPerLot) : 0.0;

   double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(lotStep <= 0) lotStep = 0.01;
   if(minLot <= 0) minLot = 0.01;
   if(maxLot <= 0) maxLot = 100.0;

   double finalLots = (InpRoundMode == ROUND_FLOOR) ? (MathFloor(rawLots / lotStep) * lotStep) : (MathRound(rawLots / lotStep) * lotStep);
   if(finalLots < minLot) finalLots = minLot;
   if(finalLots > maxLot) finalLots = maxLot;

   double actualRiskUSD = finalLots * lossPerLot;
   double reward1USD    = (slDist > 0) ? (actualRiskUSD * (tp1Dist / slDist)) : 0;
   double reward2USD    = (slDist > 0) ? (actualRiskUSD * (tp2Dist / slDist)) : 0;

   double spreadPts  = (double)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   double spreadPips = (_Digits == 3 || _Digits == 5) ? (spreadPts / 10.0) : spreadPts;

   // 6. 持仓统计
   int totalPositions = PositionsTotal();
   double totalVolume = 0.0, totalPnl = 0.0;
   int buyCount = 0, sellCount = 0;
   bool hasNoSL = false;

   for(int p = 0; p < totalPositions; p++)
   {
      ulong ticket = PositionGetTicket(p);
      if(ticket > 0 && PositionGetString(POSITION_SYMBOL) == _Symbol)
      {
         totalVolume += PositionGetDouble(POSITION_VOLUME);
         totalPnl    += PositionGetDouble(POSITION_PROFIT);
         long posType = PositionGetInteger(POSITION_TYPE);
         if(posType == POSITION_TYPE_BUY) buyCount++;
         else if(posType == POSITION_TYPE_SELL) sellCount++;
         if(PositionGetDouble(POSITION_SL) <= 0) hasNoSL = true;
      }
   }

   // 7. 紧凑精炼渲染 (每行字数严格控制在面板内，绝不超宽溢出)
   int baseX = InpPanelX + 14;
   int baseY = InpPanelY + 10;

   SetLabelText("TITLE", "[ BPA 极速仓位与量化雷达 ]", baseX, baseY, C'160,175,195', 10, true);

   string typeStr = isBuy ? "【做多 BUY】" : "【做空 SELL】";
   string lotStr  = StringFormat("开仓: %.2f 手 (风控 $%.2f)", finalLots, targetRiskUSD);
   color typeClr  = isBuy ? C'80,230,120' : C'255,100,100';
   SetLabelText("DIR_LOTS", StringFormat("%s  %s", typeStr, lotStr), baseX, baseY + 22, typeClr, 11, true);

   string slVolStr = StringFormat("止损: %.1f点 (-$%.2f) | ATR: %.1f点 | 剩ADR: %.1f点", 
                                  slPips, actualRiskUSD, atrPips, remainingRangePips);
   SetLabelText("SL_VOL", slVolStr, baseX, baseY + 44, C'220,180,120', 9, false);

   SetLabelText("DIV_1", "----------------------------------------------------", baseX, baseY + 62, C'55,68,88', 8, false);

   // 实测核心数据 (干净纯粹，无废话)
   int displayBars = (bt.actualBars > 0) ? bt.actualBars : MathMax(2000, InpHistoryBars);
   string btHdStr = StringFormat("【历史 %d 根 K 线实测 · 样本: %d 次】", displayBars, bt.sampleCount);
   SetLabelText("BT_HD", btHdStr, baseX, baseY + 76, C'100,210,255', 9, true);

   string bt1RStr = StringFormat("· 1R (%.1f点): 胜率 %.1f%% (%d胜) | 均耗 %.0f分", 
                                 tp1Pips, bt.winRate1R, bt.wins1R, bt.avgMins1R);
   SetLabelText("BT_1R", bt1RStr, baseX, baseY + 96, C'245,195,65', 9, false);

   string bt2RStr = StringFormat("· 2R (%.1f点): 胜率 %.1f%% (%d胜) | 均耗 %.0f分", 
                                 tp2Pips, bt.winRate2R, bt.wins2R, bt.avgMins2R);
   color bt2Clr = (bt.winRate2R >= 48.0) ? C'80,230,120' : C'200,200,200';
   SetLabelText("BT_2R", bt2RStr, baseX, baseY + 116, bt2Clr, 9, false);

   // 修正：分别展示 1R 与 2R 的真实期望，严谨区分正负期望并展示漂移
   string evTag1R = (bt.ev1R >= 0) ? "正" : "负";
   string evTag2R = (bt.ev2R >= 0) ? "正" : "负";
   string btEVStr = StringFormat("· 期望: 1R(%+.2fR%s) 2R(%+.2fR%s) | 漂移:%.0f%%", 
                                 bt.ev1R, evTag1R, bt.ev2R, evTag2R, bt.theoProb1R);
   color evClr = C'80,230,120';
   if(bt.ev1R > 0 && bt.ev2R < 0) evClr = C'245,195,65'; // 1R正期望但2R负期望，用醒目黄色预警
   else if(bt.ev1R <= 0)          evClr = clrOrangeRed;   // 整体负期望用红色警告
   SetLabelText("BT_EV", btEVStr, baseX, baseY + 136, evClr, 9, true);

   SetLabelText("DIV_2", "----------------------------------------------------", baseX, baseY + 154, C'55,68,88', 8, false);

   SetLabelText("VERDICT", verdictStr, baseX, baseY + 168, verdictClr, 10, true);

   SetLabelText("DIV_3", "----------------------------------------------------", baseX, baseY + 188, C'55,68,88', 8, false);

   // 持仓与账户合并精简
   if(totalVolume > 0)
   {
      string pType = (sellCount > 0) ? "做空" : "做多";
      string pSign = (totalPnl >= 0) ? "+" : "";
      string posStr = StringFormat("持仓: %.2f手 %s | 浮盈: %s$%.2f", totalVolume, pType, pSign, totalPnl);
      if(hasNoSL) posStr += " [未设止损!]";
      SetLabelText("POS_INFO", posStr, baseX, baseY + 202, hasNoSL ? clrOrangeRed : (totalPnl >= 0 ? C'50,235,110' : C'255,100,100'), 10, true);
   }
   else
   {
      SetLabelText("POS_INFO", "持仓: 空仓观望中 (等待 5分钟 A+ 架构)", baseX, baseY + 202, C'160,175,195', 9, false);
   }

   string accStr = StringFormat("净值: $%.2f | 点差: %.1f | 1R:+$%.2f | 2R:+$%.2f", 
                                equity, spreadPips, reward1USD, reward2USD);
   SetLabelText("ACC_INFO", accStr, baseX, baseY + 224, C'140,150,165', 9, false);
}

//+------------------------------------------------------------------+
//| 文本渲染辅助函数                                                 |
//+------------------------------------------------------------------+
void SetLabelText(string key, string text, int x, int y, color clr, int fontSize, bool isBold)
{
   string name = PREFIX_OBJ + "TXT_" + key;
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, InpPanelCorner);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_BACK, false);
   }

   if(StringLen(text) == 0)
   {
      ObjectSetInteger(0, name, OBJPROP_TIMEFRAMES, OBJ_NO_PERIODS);
      return;
   }
   else
   {
      ObjectSetInteger(0, name, OBJPROP_TIMEFRAMES, OBJ_ALL_PERIODS);
   }

   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetString(0, name, OBJPROP_FONT, isBold ? "Microsoft YaHei Bold" : "Microsoft YaHei");
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, fontSize);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
}

//+------------------------------------------------------------------+
//| 清理所有对象                                                     |
//+------------------------------------------------------------------+
void CleanAllObjects()
{
   ObjectsDeleteAll(0, PREFIX_OBJ);
}
