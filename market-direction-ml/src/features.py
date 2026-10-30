import numpy as np
import pandas as pd


def make_features(bars):
    c, o, h, l, v = [bars[k].astype(float) for k in ("close", "open", "high", "low", "volume")]
    f = pd.DataFrame(index=bars.index)
    ret = c.pct_change(fill_method=None)
    for n in (1, 3, 5, 10):
        f[f"return_{n}"] = c.pct_change(n, fill_method=None)
    spread = (h - l).replace(0, np.nan)
    f["open_close"] = c.div(o).sub(1)
    f["high_low"] = (h - l).div(c)
    f["body"] = (c - o).div(spread).fillna(0)
    f["upper_shadow"] = (h - pd.concat([o, c], axis=1).max(axis=1)).div(spread).fillna(0)
    f["lower_shadow"] = (pd.concat([o, c], axis=1).min(axis=1) - l).div(spread).fillna(0)
    for n in (5, 10, 20, 50):
        sma = c.rolling(n).mean()
        ema = c.ewm(span=n, adjust=False, min_periods=n).mean()
        f[f"sma_distance_{n}"] = c.div(sma).sub(1)
        f[f"ema_distance_{n}"] = c.div(ema).sub(1)
        f[f"sma_slope_{n}"] = sma.pct_change(3, fill_method=None)
    macd = c.ewm(span=12, adjust=False, min_periods=12).mean() - c.ewm(span=26, adjust=False, min_periods=26).mean()
    signal = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    f["macd"] = macd.div(c)
    f["macd_signal"] = signal.div(c)
    f["macd_histogram"] = (macd - signal).div(c)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    f["atr"] = atr.div(c)
    f["volatility"] = ret.rolling(20).std()
    f["bollinger_width"] = 4 * c.rolling(20).std().div(c.rolling(20).mean())
    gain = c.diff().clip(lower=0).rolling(14).mean()
    loss = -c.diff().clip(upper=0).rolling(14).mean()
    f["rsi"] = (100 - 100 / (1 + gain.div(loss.replace(0, np.nan)))).where(loss.ne(0), 100).where((gain + loss).ne(0), 50) / 100
    f["roc"] = c.pct_change(10, fill_method=None)
    lo, hi = l.rolling(14).min(), h.rolling(14).max()
    f["stochastic_k"] = (c - lo).div((hi - lo).replace(0, np.nan)).fillna(.5)
    f["stochastic_d"] = f["stochastic_k"].rolling(3).mean()
    mean_v = v.rolling(20).mean()
    f["volume_mean"] = mean_v
    f["relative_volume"] = v.div(mean_v.replace(0, np.nan)).fillna(0)
    f["volume_change"] = (v - v.shift()).div(v.shift().replace(0, np.nan)).fillna(0)
    f["price_volume_corr"] = ret.rolling(20).corr(v).fillna(0)
    f["trend_strength"] = (c.ewm(span=10, adjust=False).mean() - c.ewm(span=20, adjust=False).mean()).abs().div(atr.replace(0, np.nan)).fillna(0)
    f["volatility_quantile"] = f["volatility"].rolling(20).rank(pct=True)
    # Only retained bars contribute; a trade day's last close is unavailable before 16:00.
    trade_date = bars.available_at.dt.normalize() + pd.to_timedelta(bars.available_at.dt.hour.ge(19).astype(int), unit="D")
    daily = pd.DataFrame({"day": trade_date, "close": c}).groupby("day").close.last()
    history = pd.DataFrame({"daily_available_at": daily.index + pd.Timedelta(hours=16), "day_return": daily.pct_change(fill_method=None).values})
    joined = pd.merge_asof(bars[["available_at"]], history, left_on="available_at", right_on="daily_available_at")
    f["day_return_known"] = joined.day_return.notna().astype(float).values
    f["day_return"] = joined.day_return.fillna(0).values
    return f.replace([np.inf, -np.inf], np.nan)
