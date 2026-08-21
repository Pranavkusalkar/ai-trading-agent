"""
Candlestick Pattern Detector
Detects 15 patterns from OHLC data.
Returns list of active patterns with signal direction and strength.
"""
import numpy as np

def detect_patterns(opens, highs, lows, closes):
    """
    Detect candlestick patterns from OHLC lists.
    Returns list of dicts: {name, signal, strength, description}
    """
    if len(closes) < 3:
        return []

    o = np.array(opens,  dtype=float)
    h = np.array(highs,  dtype=float)
    l = np.array(lows,   dtype=float)
    c = np.array(closes, dtype=float)

    patterns = []

    def body(i):    return abs(c[i] - o[i])
    def range_(i):  return h[i] - l[i]
    def upper_wick(i): return h[i] - max(c[i], o[i])
    def lower_wick(i): return min(c[i], o[i]) - l[i]
    def bullish(i): return c[i] > o[i]
    def bearish(i): return c[i] < o[i]
    def avg_body(n=5): return np.mean([body(i) for i in range(-min(n,len(c)),0)])

    n = len(c)
    i = n - 1   # last candle index

    ab = avg_body()

    # ── Single candle ──────────────────────────────────────────────

    # Doji
    if body(i) <= range_(i) * 0.1 and range_(i) > 0:
        patterns.append({"name":"Doji","signal":"NEUTRAL","strength":60,
            "description":"Indecision — trend reversal possible"})

    # Hammer (bullish reversal)
    if (lower_wick(i) >= body(i)*2 and upper_wick(i) <= body(i)*0.3
            and range_(i) > 0):
        patterns.append({"name":"Hammer","signal":"BULLISH","strength":72,
            "description":"Strong bullish reversal at support"})

    # Shooting Star (bearish reversal)
    if (upper_wick(i) >= body(i)*2 and lower_wick(i) <= body(i)*0.3
            and range_(i) > 0):
        patterns.append({"name":"Shooting Star","signal":"BEARISH","strength":72,
            "description":"Bearish reversal at resistance"})

    # Marubozu bullish
    if (bullish(i) and body(i) >= range_(i)*0.9
            and body(i) > ab*1.5):
        patterns.append({"name":"Bullish Marubozu","signal":"BULLISH","strength":80,
            "description":"Strong buying pressure — momentum up"})

    # Marubozu bearish
    if (bearish(i) and body(i) >= range_(i)*0.9
            and body(i) > ab*1.5):
        patterns.append({"name":"Bearish Marubozu","signal":"BEARISH","strength":80,
            "description":"Strong selling pressure — momentum down"})

    # Spinning top
    if (body(i) <= range_(i)*0.3 and upper_wick(i) > body(i)
            and lower_wick(i) > body(i)):
        patterns.append({"name":"Spinning Top","signal":"NEUTRAL","strength":50,
            "description":"Market indecision — wait for confirmation"})

    # ── Two candle ─────────────────────────────────────────────────

    if n >= 2:
        # Bullish Engulfing
        if (bearish(i-1) and bullish(i)
                and o[i] <= c[i-1] and c[i] >= o[i-1]
                and body(i) > body(i-1)):
            patterns.append({"name":"Bullish Engulfing","signal":"BULLISH","strength":82,
                "description":"Bears overtaken by bulls — strong reversal"})

        # Bearish Engulfing
        if (bullish(i-1) and bearish(i)
                and o[i] >= c[i-1] and c[i] <= o[i-1]
                and body(i) > body(i-1)):
            patterns.append({"name":"Bearish Engulfing","signal":"BEARISH","strength":82,
                "description":"Bulls overtaken by bears — strong reversal"})

        # Tweezer Top
        if (abs(h[i] - h[i-1]) <= range_(i)*0.05
                and bullish(i-1) and bearish(i)):
            patterns.append({"name":"Tweezer Top","signal":"BEARISH","strength":68,
                "description":"Double rejection at high — bearish reversal"})

        # Tweezer Bottom
        if (abs(l[i] - l[i-1]) <= range_(i)*0.05
                and bearish(i-1) and bullish(i)):
            patterns.append({"name":"Tweezer Bottom","signal":"BULLISH","strength":68,
                "description":"Double support at low — bullish reversal"})

        # Piercing Line
        if (bearish(i-1) and bullish(i)
                and o[i] < l[i-1]
                and c[i] > (o[i-1]+c[i-1])/2):
            patterns.append({"name":"Piercing Line","signal":"BULLISH","strength":75,
                "description":"Bulls piercing prior bearish candle midpoint"})

        # Dark Cloud Cover
        if (bullish(i-1) and bearish(i)
                and o[i] > h[i-1]
                and c[i] < (o[i-1]+c[i-1])/2):
            patterns.append({"name":"Dark Cloud Cover","signal":"BEARISH","strength":75,
                "description":"Bears pushing below prior bullish midpoint"})

    # ── Three candle ────────────────────────────────────────────────

    if n >= 3:
        # Morning Star
        if (bearish(i-2) and body(i-1) < ab*0.5
                and bullish(i) and c[i] > (o[i-2]+c[i-2])/2):
            patterns.append({"name":"Morning Star","signal":"BULLISH","strength":88,
                "description":"Three-candle bullish reversal — high reliability"})

        # Evening Star
        if (bullish(i-2) and body(i-1) < ab*0.5
                and bearish(i) and c[i] < (o[i-2]+c[i-2])/2):
            patterns.append({"name":"Evening Star","signal":"BEARISH","strength":88,
                "description":"Three-candle bearish reversal — high reliability"})

        # Three White Soldiers
        if (all(bullish(j) for j in [i-2,i-1,i])
                and all(body(j) > ab*0.8 for j in [i-2,i-1,i])
                and c[i]>c[i-1]>c[i-2]):
            patterns.append({"name":"Three White Soldiers","signal":"BULLISH","strength":90,
                "description":"Three consecutive strong bull candles — powerful uptrend"})

        # Three Black Crows
        if (all(bearish(j) for j in [i-2,i-1,i])
                and all(body(j) > ab*0.8 for j in [i-2,i-1,i])
                and c[i]<c[i-1]<c[i-2]):
            patterns.append({"name":"Three Black Crows","signal":"BEARISH","strength":90,
                "description":"Three consecutive strong bear candles — powerful downtrend"})

    # Sort by strength
    return sorted(patterns, key=lambda x: x["strength"], reverse=True)
