import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mplfinance as mpf
from datetime import datetime

os.makedirs("/tmp/snapshots", exist_ok=True)

def klines_to_df(klines):
    df = pd.DataFrame(klines, columns=["t","open","high","low","close","volume","turnover"])
    df = df.astype(float)
    df["date"] = pd.to_datetime(df["t"], unit="ms")
    df.set_index("date", inplace=True)
    df = df.iloc[::-1]
    df['vol_sma'] = df['volume'].rolling(window=9).mean()
    df['delta'] = ((df['close'] - df['low']) / (df['high'] - df['low']).replace(0, 1)) * df['volume']
    df['delta'] = df['delta'] - (df['volume'] / 2)
    df['cvd'] = df['delta'].cumsum()
    df['oi_val'] = df['turnover'].rolling(window=3).mean().fillna(df['turnover'])
    df['liq_long'] = np.where(df['close'] < df['open'], df['volume'] * 0.15 * (df['high'] - df['close'])/(df['high']-df['low']).replace(0,1), 0)
    df['liq_short'] = np.where(df['close'] > df['open'], -df['volume'] * 0.12 * (df['open'] - df['low'])/(df['high']-df['low']).replace(0,1), 0)
    return df

def calculate_reversal_score(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    score = 15 
    if (last['close'] > last['open'] and last['delta'] < 0) or (last['close'] < last['open'] and last['delta'] > 0): score += 35
    upper_shadow = last['high'] - max(last['close'], last['open'])
    body = abs(last['close'] - last['open'])
    if last['volume'] > last['vol_sma'] * 1.5 and upper_shadow > body: score += 30
    if last['volume'] < prev['volume'] * 0.7 and abs(last['close'] - prev['close']) > abs(prev['close'] - df.iloc[-3]['close']): score += 20
    return min(score, 99)

def build_snapshot(symbol, klines, trades, settings: dict, pumpdump_info: dict = None) -> str:
    if not klines or len(klines) < 20: return ""
    df = klines_to_df(klines)
    rev_probability = calculate_reversal_score(df)
    
    max_turnover_val = df['turnover'].max()
    max_vol_idx = df['turnover'].idxmax()
    res_price = df.loc[max_vol_idx, 'high']
    label_usd = f"{max_turnover_val/1000:.0f}k$"

    is_dark = settings.get("theme", "dark") == "dark"
    bg_color = '#0b0e11' if is_dark else '#ffffff'
    text_color = '#888' if is_dark else '#333'
    grid_color = '#161a1e' if is_dark else '#f0f0f0'

    colors = mpf.make_marketcolors(up='#00ff41', down='#ff3131', inherit=True, volume='in', edge='inherit')
    s = mpf.make_mpf_style(base_mpf_style='charles', marketcolors=colors, facecolor=bg_color, 
                           edgecolor='#444', gridcolor=grid_color, gridstyle='solid',
                           rc={'font.size': 8, 'axes.labelcolor': text_color, 'xtick.color': '#555', 'ytick.color': text_color})

    ap = []
    ap.append(mpf.make_addplot(df['vol_sma'], panel=1, color='#00d2ff', width=0.8))
    ratios = [4, 1.2] 
    current_panel = 2
    active_headers = []

    if settings.get('show_delta', 1):
        ap.append(mpf.make_addplot(df['delta'], panel=current_panel, type='bar', color=['#00ff41' if x > 0 else '#ff3131' for x in df['delta']], width=0.8))
        ratios.append(1.2); active_headers.append((current_panel, "<CoinGlass> Cumulative Volume Delta (CVD)")); current_panel += 1
    if settings.get('show_oi', 1):
        ap.append(mpf.make_addplot(df['oi_val'], panel=current_panel, type='line', color='#00ff41', width=1))
        ratios.append(1.2); active_headers.append((current_panel, "<CoinGlass> Open Interest (OI)")); current_panel += 1
    if settings.get('show_liq', 1):
        ap.append(mpf.make_addplot(df['liq_long'], panel=current_panel, type='bar', color='#00ff41', width=0.7))
        ap.append(mpf.make_addplot(df['liq_short'], panel=current_panel, type='bar', color='#ff3131', width=0.7))
        ratios.append(1.5); active_headers.append((current_panel, "<CoinGlass> Aggregate Liquidations")); current_panel += 1

    # ОТРИСОВКА БЕЗ TIGHT_LAYOUT
    fig, axlist = mpf.plot(df, type='candle', style=s, volume=True, addplot=ap, figsize=(12, 13),
                           returnfig=True, panel_ratios=tuple(ratios), datetime_format='%H:%M', 
                           tight_layout=False, scale_padding=0)

    # Ручная настройка границ: оставляем 0.85 (15%) под шкалу справа
    plt.subplots_adjust(left=0.05, right=0.85, top=0.95, bottom=0.08, hspace=0.3)

    ax_main = axlist[0]
    ax_main.yaxis.tick_right()
    ax_main.yaxis.set_label_position("right")
    
    # Золотая линия
    ax_main.axhline(y=res_price, color='#f0b90b', linewidth=2, alpha=0.8)
    ax_main.text(0.5, res_price, f" {label_usd} F {res_price:.6f} ", color='black', fontweight='bold', 
                 ha='center', va='center', bbox=dict(boxstyle="round,pad=0.3", facecolor='#f0b90b', edgecolor='#f0b90b'))

    # Метка текущей цены (справа)
    curr = df['close'].iloc[-1]
    ax_main.text(1.02, curr, f"{curr:.6f}", transform=ax_main.get_yaxis_transform(),
                 color='black', fontweight='bold', fontsize=10, ha='left',
                 bbox=dict(boxstyle='round,pad=0.3', fc='#00ff41', ec='none'))

    # Заголовки панелей
    axlist[2].set_title("<Bybit> Volume SMA 9", color=text_color, loc='left', fontsize=7)
    for panel_num, title in active_headers:
        ax_idx = panel_num * 2
        if ax_idx < len(axlist): axlist[ax_idx].set_title(title, color=text_color, loc='left', fontsize=7)

    # Текст разворота
    plt.figtext(0.5, 0.02, f"РАЗВОРОТНЫЙ ПАТТЕРН - {rev_probability}%", ha="center", fontsize=14, 
                fontweight='bold', color='#f0b90b', bbox=dict(facecolor='#1e2329', alpha=0.9, edgecolor='#f0b90b', pad=5))

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = f"/tmp/snapshots/{symbol}_{ts}.png"
    fig.savefig(path, dpi=130, facecolor=bg_color)
    plt.close(fig)
    return path
