"""
Transaction Cost Model - Indian F&O (for backtesting)
Brokerage, STT, exchange charges, SEBI fee, stamp duty, GST.
"""


def calculate_fno_charges(instrument_type, direction, premium, quantity,
                           underlying_lot, notional_value, brokerage_flat=20.0):
    turnover  = premium * quantity
    brokerage = brokerage_flat
    if instrument_type == "option":
        stt = (turnover * 0.000625) if direction == "sell" else 0.0
    else:
        stt = (notional_value * 0.0000125) if direction == "sell" else 0.0
    exchange_charge = turnover * 0.00053
    sebi_fee        = turnover * 0.000001
    if direction == "buy":
        stamp_duty = turnover * 0.00003 if instrument_type == "option" else notional_value * 0.00002
    else:
        stamp_duty = 0.0
    gst_base = brokerage + exchange_charge + sebi_fee
    gst      = gst_base * 0.18
    total    = brokerage + stt + exchange_charge + sebi_fee + stamp_duty + gst
    return {
        "brokerage": round(brokerage, 2), "stt": round(stt, 2),
        "exchange_charge": round(exchange_charge, 2),
        "sebi_fee": round(sebi_fee, 4), "stamp_duty": round(stamp_duty, 2),
        "gst": round(gst, 2), "total": round(total, 2), "turnover": round(turnover, 2),
    }


def round_trip_cost(instrument_type, entry_premium, exit_premium,
                    quantity, underlying_lot, spot_price, brokerage_flat=20.0):
    notional    = spot_price * quantity
    entry_costs = calculate_fno_charges(instrument_type, "buy",  entry_premium, quantity, underlying_lot, notional, brokerage_flat)
    exit_costs  = calculate_fno_charges(instrument_type, "sell", exit_premium,  quantity, underlying_lot, notional, brokerage_flat)
    total       = entry_costs["total"] + exit_costs["total"]
    gross_pnl   = (exit_premium - entry_premium) * quantity
    return {
        "entry_costs": entry_costs["total"], "exit_costs": exit_costs["total"],
        "total_charges": round(total, 2), "gross_pnl": round(gross_pnl, 2),
        "net_pnl": round(gross_pnl - total, 2),
        "breakeven_move": round(total / quantity, 4),
    }
