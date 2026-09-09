# -*- coding: utf-8 -*-
"""
仓位计算器 (Position Sizer)

固定比例风险预算（Fixed-Fractional Risk）仓位管理工具：
单笔最大亏损 = 总资金 × 风险百分比，倒推每笔仓位价值，
并把双边手续费、合约最小步进、强平距离全部纳入计算。

核心公式：
    风险预算 = 总资金 × 风险%
    仓位价值 = 风险预算 / (止损% + 双边手续费%)
    保证金   = 仓位价值 / 杠杆
→ 打止损时：价格止损 + 手续费 = 风险预算（恰好等于计划亏损）

强平距离检查（新增）：
    强平距离% ≈ 1/杠杆 - 维持保证金率
    若 强平距离 < 止损距离 → 止损还没触发就先被强平，
    提示降低杠杆或收窄止损（隔离保证金简化估算，未计手续费）。

用法：python position_sizer.py
"""
import json

CONFIG_FILE = 'config.json'

CONTRACT_FEE_PCT = 0.036   # 合约单边手续费率(%)
ETF_FEE_PCT = 0.005      # ETF单边手续费率(万分之0.5)
ETF_FEE_MIN = 0.1        # ETF最低佣金(元)
FIXED_LEV = 10           # 合约固定杠杆
MAINTENANCE_RATE = 0.004  # 维持保证金率(默认0.4%)


def save_config(config):
    """保存配置到 JSON 文件。"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
        return True
    except IOError as e:
        print(f"无法写入配置文件: {e}")
        return False


def load_config():
    """读取配置；兼容旧版 total_capital 字段，自动迁移到 合约/ETF 双资金。"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        if 'contract_capital' not in cfg:
            old = cfg.get('total_capital', 0)
            cfg['contract_capital'] = old
            cfg['etf_capital'] = cfg.get('etf_capital', old)
            save_config(cfg)
        return cfg
    except (FileNotFoundError, json.JSONDecodeError, IOError):
        return None


def calc_contract(total_capital, risk_pct, stop_pct, leverage, fee_pct):
    """合约(带杠杆)：按风险预算反推仓位价值。
    手续费按双边计，打止损时总亏损 = 价格止损 + 手续费 = 风险预算。"""
    risk_decimal = risk_pct / 100.0
    stop_decimal = stop_pct / 100.0
    fee_total_pct = (fee_pct / 100.0) * 2
    total_risk_budget = total_capital * risk_decimal
    total_cost_rate = stop_decimal + fee_total_pct
    position_value = total_risk_budget / total_cost_rate
    margin = position_value / leverage
    stop_loss_amount = position_value * stop_decimal
    total_fee = position_value * fee_total_pct
    actual_total_loss = stop_loss_amount + total_fee
    margin_pct = (margin / total_capital) * 100
    return {
        "position_value": position_value,
        "margin": margin,
        "margin_pct": margin_pct,
        "stop_loss_amount": stop_loss_amount,
        "total_fee": total_fee,
        "actual_total_loss": actual_total_loss,
    }


def calc_etf(total_capital, risk_pct, stop_pct):
    """ETF(无杠杆)：同上，但手续费按"万0.5且单边最低0.1元"建模。
    资金量大时手续费随仓位线性变化；金额小时按最低佣金固定扣除。"""
    risk_decimal = risk_pct / 100.0
    stop_decimal = stop_pct / 100.0
    total_risk_budget = total_capital * risk_decimal
    fee_per_side_pct = ETF_FEE_PCT / 100.0
    fee_min = ETF_FEE_MIN

    # 先按比例费用估算，判断是否达到最低佣金门槛
    max_position_value = total_risk_budget / (stop_decimal + fee_per_side_pct * 2)
    if max_position_value * fee_per_side_pct >= fee_min:
        fee_total_pct = fee_per_side_pct * 2
        position_value = total_risk_budget / (stop_decimal + fee_total_pct)
        total_fee = position_value * fee_total_pct
    else:
        # 未达最低佣金：按固定金额扣费后反推仓位
        fee_total_amount = fee_min * 2
        position_value = (total_risk_budget - fee_total_amount) / stop_decimal
        total_fee = fee_total_amount

    if position_value < 0:
        position_value = 0
        total_fee = 0

    stop_loss_amount = position_value * stop_decimal
    actual_total_loss = stop_loss_amount + total_fee
    return {
        "position_value": position_value,
        "stop_loss_amount": stop_loss_amount,
        "total_fee": total_fee,
        "actual_total_loss": actual_total_loss,
    }


def suggest_contract_options(total_capital, risk_pct, stop_pct,
                           contract_step=0, entry_price=0,
                           maintenance_rate=MAINTENANCE_RATE):
    """推荐合约仓位：固定杠杆，若提供合约步进与入场价则按最小步进搜索单位数。
    同时计算强平距离并预警：强平距离 < 止损距离 时，止损将先于强平失效。"""
    risk_decimal = risk_pct / 100.0
    stop_decimal = stop_pct / 100.0
    fee_total_pct = CONTRACT_FEE_PCT / 100.0 * 2
    total_risk_budget = total_capital * risk_decimal

    # 强平距离估算(隔离保证金,未计手续费): 价格反向走多少百分比会触发强平
    liquidation_dist = 1.0 / FIXED_LEV - maintenance_rate
    liq_warning = liquidation_dist < stop_decimal

    if contract_step > 0 and entry_price > 0:
        # 按合约最小步进搜索: 在风险预算内找最大可开单位数
        step_margin = contract_step * entry_price / FIXED_LEV
        best_diff = float('inf')
        best_margin = float('inf')
        best_units = None
        for units in range(1, 200):
            actual_margin = units * step_margin
            actual_position = actual_margin * FIXED_LEV
            actual_stop = actual_position * stop_decimal
            actual_fee = actual_position * fee_total_pct
            actual_loss = actual_stop + actual_fee
            if actual_loss <= total_risk_budget + 0.01:
                diff = total_risk_budget - actual_loss
            else:
                # 超预算时加大惩罚,优先保证不超预算
                diff = (actual_loss - total_risk_budget) * 10
            if diff < best_diff - 0.001 or (abs(diff - best_diff) < 0.001 and actual_margin < best_margin):
                best_diff = diff
                best_units = units
                best_margin = actual_margin

        units = best_units
        actual_margin = units * step_margin
        actual_position = actual_margin * FIXED_LEV
        actual_stop = actual_position * stop_decimal
        actual_fee = actual_position * fee_total_pct
        actual_loss = actual_stop + actual_fee
        over_budget = actual_loss > total_risk_budget + 0.01
        result = {
            "leverage": FIXED_LEV,
            "contract_units": units,
            "margin": actual_margin,
            "position_value": actual_position,
            "stop_loss_amount": actual_stop,
            "total_fee": actual_fee,
            "actual_total_loss": actual_loss,
            "over_budget": over_budget,
        }
    else:
        r = calc_contract(total_capital, risk_pct, stop_pct, FIXED_LEV, CONTRACT_FEE_PCT)
        result = {
            "leverage": FIXED_LEV,
            "margin": r['margin'],
            "position_value": r['position_value'],
            "stop_loss_amount": r['stop_loss_amount'],
            "total_fee": r['total_fee'],
            "actual_total_loss": r['actual_total_loss'],
        }
    result["liquidation_dist"] = liquidation_dist
    result["liq_warning"] = liq_warning
    return result


def setup():
    print("\n===== 首次设置 =====")
    try:
        contract_capital = float(input("合约总资金 (单位): ").strip())
        etf_capital = float(input("ETF总资金 (元): ").strip())
        risk = float(input("每笔最大亏损% (默认 1.5, 对应1%-2%风险纪律): ").strip() or "1.5")
        config = {
            "contract_capital": contract_capital,
            "etf_capital": etf_capital,
            "risk_percentage": risk,
        }
        save_config(config)
        print("配置已保存")
        return config
    except ValueError:
        print("输入无效，请重新运行。")
        return None


def input_float(prompt, default=None):
    """带异常保护的浮点输入。"""
    try:
        raw = input(prompt).strip()
        if not raw and default is not None:
            return default
        return float(raw)
    except ValueError:
        print("输入无效，请重新输入")
        return None


def main():
    print("=" * 55)
    print("  仓位计算器")
    print("=" * 55)

    config = load_config()
    if config is None:
        config = setup()
        if config is None:
            return

    print("\n选择交易类型:")
    print("  [1] 合约（带杠杆）")
    print("  [2] ETF（无杠杆，万0.5）")
    mode = input("请输入 (1/2): ").strip()
    while mode not in ("1", "2"):
        mode = input("请选择 1 或 2: ").strip()
    mode_name = "合约" if mode == "1" else "ETF"

    while True:
        c = config
        capital = c['contract_capital'] if mode == "1" else c['etf_capital']
        max_loss = capital * c['risk_percentage'] / 100
        print(f"\n--- [{mode_name}] 资金: {capital:.2f} | "
              f"每笔最多亏: {c['risk_percentage']}% = {max_loss:.2f} ---")
        print("  [c] 计算仓位  [config] 重设参数  [m] 改资金  [s] 切换模式  [q] 退出")
        cmd = input("请输入: ").strip().lower()

        if cmd == 'q':
            print("再见")
            break

        elif cmd == 'config':
            config = setup()
            if config is None:
                return

        elif cmd == 'm':
            label = "合约" if mode == "1" else "ETF"
            val = input_float(f"新{label}资金: ")
            if val is None:
                continue
            if mode == "1":
                config['contract_capital'] = val
            else:
                config['etf_capital'] = val
            save_config(config)
            continue

        elif cmd == 's':
            mode = "2" if mode == "1" else "1"
            mode_name = "合约" if mode == "1" else "ETF"
            continue

        elif cmd == 'c':
            contract_step = 0
            price = 0
            if mode == "1":
                cs_input = input("合约步进 (如0.01), 回车跳过: ").strip()
                if cs_input:
                    step_val = input_float("合约步进: ")
                    if step_val is None:
                        continue
                    contract_step = step_val
                    price_val = input_float("当前入场价: ")
                    if price_val is None:
                        continue
                    price = price_val

            print("\n价格止损% = 从入场价到止损价的价格变动百分比")
            print("  例如：入场 100，止损 98 → 价格止损 = 2%")
            stop_pct = input_float("价格止损% (如 2.0): ")
            if stop_pct is None:
                continue

            print()
            print("=" * 55)

            if mode == "1":
                r = suggest_contract_options(
                    config['contract_capital'], config['risk_percentage'], stop_pct, contract_step, price
                )
                print(f"  杠杆: {r['leverage']}x")
                if "contract_units" in r:
                    print(f"    (开 {r['contract_units']} 单位 = 保证金 {r['margin']:.2f} 单位)")
                    if r.get('over_budget'):
                        print(f"    ⚠️ 最小1单位也超预算，建议降低止损或增加资金")
                print(f"    合约价值:    {r['position_value']:.2f} 单位")
                print(f"    保证金:      {r['margin']:.2f} 单位  ({r['margin']/config['contract_capital']*100:.1f}%)")
                print(f"    强平距离:    {r['liquidation_dist']*100:.1f}%")
                print(f"    ─── 打止损时的亏损 ───")
                print(f"    价格止损:    {r['stop_loss_amount']:.2f} 单位")
                print(f"    手续费:      {r['total_fee']:.3f} 单位")
                print(f"    总亏损:      {r['actual_total_loss']:.2f} 单位", end="")
                if r.get('over_budget'):
                    budget_val = config['contract_capital'] * config['risk_percentage'] / 100
                    print(f"  ❌ 超预算 {budget_val:.2f} 单位 ({config['risk_percentage']}%)")
                else:
                    print(f"  (预算 {config['risk_percentage']}%)")
                if r.get('liq_warning'):
                    print(f"    ⚠️ 强平距离({r['liquidation_dist']*100:.1f}%) < 止损距离({stop_pct}%)"
                          f" → 止损触发前可能先被强平，建议降低杠杆或收窄止损")
            else:
                etf = calc_etf(config['etf_capital'], config['risk_percentage'], stop_pct)
                print(f"  买入金额:      {etf['position_value']:.2f} 元")
                print(f"  占用资金:      {etf['position_value']:.2f} 元  ({etf['position_value']/config['etf_capital']*100:.1f}%)")
                print(f"  ─── 打止损时的亏损 ───")
                print(f"  价格止损:      {etf['stop_loss_amount']:.2f} 元")
                print(f"  手续费:        {etf['total_fee']:.2f} 元")
                print(f"  总亏损:        {etf['actual_total_loss']:.2f} 元  (预算 {config['risk_percentage']}%)")
            print("=" * 55)

        else:
            print("未知指令")

    save_config(config)


if __name__ == "__main__":
    main()
