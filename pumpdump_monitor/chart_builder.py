"""
Графики: mplfinance + matplotlib overlays (FVG, OB, зона интереса, лоты, VARIABLES)
"""
import os
import io
import base64
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf
from matplotlib.patches import Rectangle
from datetime import datetime

os.makedirs("/tmp/snapshots", exist_ok=True)

def klines_to_df(klines):
    """Bybit kline: [time, open, high, low, close, volume, turnover]"""
    df = pd.DataFrame(klines, columns=["t","open","high","low","close","volume","turnover"])
    df = df.astype(float)
    df["date"] = pd.to_datetime(df["t"], unit="ms")
    df.set_index("date", inplace=True)
    df = df.iloc[::-1]
    return df

def calc_atr(df, period=14):
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1]) if len(df) >= period else 0.0

def find_fvg(df):
    zones = []
    for i in range(2, len(df)):
        if df["low"].iloc[i] > df["high"].iloc[i-2]:
            zones.append({"type":"bull","top":df["low"].iloc[i],"bot":df["high"].iloc[i-2],"i":i})
        elif df["high"].iloc[i] < df["low"].iloc[i-2]:
            zones.append({"type":"bear","top":df["low"].iloc[i-2],"bot":df["high"].iloc[i],"i":i})
    last_high, last_low = df["high"].iloc[-1], df["low"].iloc[-1]
    live = [z for z in zones if not (last_low <= z["top"] and last_high >= z["bot"])]
    return live

def find_obs(df, atr, mult=1.5):
    obs = []
    avg_vol = df["volume"].rolling(20).mean()
    for i in range(1, len(df)-1):
        body = abs(df["close"].iloc[i] - df["open"].iloc[i])
        if body >= atr * mult and df["volume"].iloc[i] > avg_vol.iloc[i] * 1.2:
            obs.append({
                "type": "bull" if df["close"].iloc[i] > df["open"].iloc[i] else "bear",
                "open": df["open"].iloc[i], "close": df["close"].iloc[i],
                "high": df["high"].iloc[i], "low": df["low"].iloc[i], "i": i
            })
    return obs

def build_snapshot(symbol, klines, trades, settings: dict, pumpdump_info: dict = None) -> str:
    """
    Строит PNG и возвращает путь.
    pumpdump_info: {direction, change_percent, score, fvg_count, ob_count, vol_mult}
    """
    if not klines or len(klines) < 20:
        return ""

    df = klines_to_df(klines)
    atr = calc_atr(df)
    last_close = float(df["close"].iloc[-1])
    zone_pct = settings.get("zone_pct", 2.0) / 100.0

    # FVG / OB
    fvg_zones = find_fvg(df)
    ob_zones = find_obs(df, atr, settings.get("ob_mult", 1.5))

    # Главный график
    title = f"{symbol}  @  {last_close:,.2f}"
    if pumpdump_info:
        title += f"  |  {pumpdump_info['direction']}  {pumpdump_info['change_percent']:+.2f}%"

    fig, axes = mpf.plot(df, type="candle", style="binance", returnfig=True,
                         title=title,
                         ylabel="Price (USDT)", volume=True,
                         figsize=(12, 8), tight_layout=True,
                         mav=(9, 21))

    ax = axes[0]
    ax_vol = axes[2] if len(axes) > 2 else None

    # Зона интереса ±%
    ax.axhspan(last_close*(1-zone_pct), last_close*(1+zone_pct), color="gray", alpha=0.06)

    # FVG зоны
    for z in fvg_zones:
        color = "lime" if z["type"]=="bull" else "magenta"
        x_idx = z["i"]
        rect = Rectangle((x_idx-0.4, z["bot"]), 0.8, z["top"]-z["bot"],
                         facecolor=color, alpha=0.22, edgecolor=color, linewidth=1.5)
        ax.add_patch(rect)

    # OB прямоугольники
    for ob in ob_zones:
        color = "green" if ob["type"]=="bull" else "red"
        x_idx = ob["i"]
        rect = Rectangle((x_idx-0.45, ob["low"]), 0.9, ob["high"]-ob["low"],
                         facecolor=color, alpha=0.18, edgecolor=color, linewidth=2)
        ax.add_patch(rect)

    # Крупные лоты (разметка)
    if trades:
        thr = settings.get("lot_threshold", 10.0)
        for idx, t in enumerate(trades[-20:]):  # последние 20 сделок
            qty = float(t.get("size", 0))
            if qty >= thr:
                side = t.get("side", "Buy")
                price = float(t.get("price", 0))
                x_pos = len(df) - 20 + idx
                color = "#00ff00" if side == "Buy" else "#ff3333"
                sign = "+" if side == "Buy" else "-"
                ax.annotate(f"{sign}{qty:.1f}", xy=(x_pos, price), color=color, fontsize=7, fontweight="bold")

    # === VARIABLES OVERLAY (все показатели на графике) ===
    if pumpdump_info:
        # Фоновый прямоугольник для читаемости
        info_text = (
            f"SCORE: {pumpdump_info.get('score', 'N/A')}/10\n"
            f"DIR:   {pumpdump_info['direction']}\n"
            f"CHG:   {pumpdump_info['change_percent']:+.2f}%\n"
            f"FVG:   {pumpdump_info.get('fvg_count', len(fvg_zones))} zones\n"
            f"OB:    {pumpdump_info.get('ob_count', len(ob_zones))} blocks\n"
            f"VOL:   {pumpdump_info.get('vol_mult', 0):.1f}x SMA\n"
            f"ATR:   {atr:.2f}\n"
            f"ZONE:  ±{settings.get('zone_pct', 2.0)}%"
        )
        # Размещаем в левом верхнем углу
        ax.text(0.02, 0.98, info_text,
                transform=ax.transAxes,
                fontsize=9, color="white", family="monospace",
                verticalalignment="top", horizontalalignment="left",
                bbox=dict(boxstyle="round,pad=0.4", facecolor="#1e2329", edgecolor="#f0b90b", alpha=0.95, linewidth=1.5))

    # Покупка/продажа лотов (правый верхний угол)
    buy_lots = 0.0
    sell_lots = 0.0
    if trades:
        for t in trades:
            qty = float(t.get("size", 0))
            side = t.get("side", "Buy")
            if side == "Buy":
                buy_lots += qty
            else:
                sell_lots += qty
    ax.text(0.98, 0.98, f"Покупка: {buy_lots:.1f} лотов  |  Продажа: {sell_lots:.1f} лотов",
            transform=ax.transAxes, fontsize=9, color="white",
            ha="right", va="top",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="#1e2329", edgecolor="#f0b90b", linewidth=1.2, alpha=0.95))

    # Водяной знак
    ax.text(0.5, 0.02, f"{symbol} | Pump&Dump Monitor | {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            transform=ax.transAxes, fontsize=9, color="gray", alpha=0.6, ha="center")

    # Стрелка + подпись если PUMP/DUMP
    if pumpdump_info:
        start_i = max(0, len(df) - 8)
        end_i = len(df) - 1
        start_price = float(df["close"].iloc[start_i])
        end_price = last_close
        ax.annotate("", xy=(end_i, end_price), xytext=(start_i, start_price),
                    arrowprops=dict(arrowstyle="->", color="#f0b90b", lw=2.5))
        mid_price = (start_price + end_price) / 2
        mid_i = (start_i + end_i) / 2
        ax.text(mid_i, mid_price, f"{pumpdump_info['change_percent']:+.2f}%",
                color="#f0b90b", fontsize=14, fontweight="bold", ha="center",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="#0b0e11", edgecolor="#f0b90b", alpha=0.9))

    # Сохранение
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = f"/tmp/snapshots/{symbol.replace('/', '_')}_{ts}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="#0b0e11")
    plt.close(fig)
    return path
