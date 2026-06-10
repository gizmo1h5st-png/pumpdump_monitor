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
    
    # 1. Volume SMA
    df['vol_sma'] = df['volume'].rolling(window=9).mean()
    
    # 2. CVD Candles (Cumulative Volume Delta)
    df['delta'] = ((df['close'] - df['low']) / (df['high'] - df['low']).replace(0, 1)) * df['volume']
    df['delta'] = df['delta'] - (df['volume'] / 2)
    df['cvd_close'] = df['delta'].cumsum()
    df['cvd_open'] = df['cvd_close'].shift(1).fillna(df['cvd_close'] * 0.99)
    df['cvd_high'] = df[['cvd_open', 'cvd_close']].max(axis=1)
    df['cvd_low'] = df[['cvd_open', 'cvd_close']].min(axis=1)
    
    # 3. OI Candles (Open Interest Emulation)
    df['oi_close'] = df['turnover']
    df['oi_open'] = df['oi_close'].shift(1).fillna(df['oi_close'] * 0.99)
    df['oi_high'] = df[['oi_open', 'oi_close']].max(axis=1)
    df['oi_low'] = df[['oi_open', 'oi_close']].min(axis=1)
    
    # 4. Liquidations
    df['liq_up'] = np.where(df['close'] < df['open'], df['volume'] * 0.1, 0)
    df['liq_down'] = np.where(df['close'] > df['open'], -df['volume'] * 0.08, 0)
    
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
    rev_prob = calculate_reversal_score(df)
    
    max_turnover = df['turnover'].max()
    res_price = df.loc[df['turnover'].idxmax(), 'high']
    label_usd = f"{max_turnover/1000:.0f}k$"

    is_dark = settings.get("theme", "dark") == "dark"
    bg_color = '#0b0e11' if is_dark else '#ffffff'
    text_color = '#707a8a' # Серый как на CoinGlass
    grid_color = '#1e2329' if is_dark else '#f0f0f0'

    colors = mpf.make_marketcolors(up='#02c076', down='#f84960', inherit=True, volume='in', edge='inherit')
    s = mpf.make_mpf_style(base_mpf_style='charles', marketcolors=colors, facecolor=bg_color, 
                           edgecolor='#2b3139', gridcolor=grid_color, gridstyle='solid',
                           rc={'font.size': 8, 'axes.labelcolor': text_color, 'xtick.color': '#555', 'ytick.color': text_color})

    ap = []
    ratios = [4, 1.2]
    cur_p = 2
    labels = []

    # SMA 9 на объеме
    ap.append(mpf.make_addplot(df['vol_sma'], panel=1, color='#00d2ff', width=0.8))

    # 2. CVD Candles
    if settings.get('show_delta', 1):
        # Эмулируем свечи через две линии (тело) и бары
        ap.append(mpf.make_addplot(df[['cvd_open', 'cvd_high', 'cvd_low', 'cvd_close']], panel=cur_p, type='candle', 
                                   up_color='#02c076', down_color='#f84960'))
        ratios.append(1.2); labels.append((cur_p, "<CoinGlass> Cumulative Volume Delta (CVD Candles) 0 open No Filter")); cur_p += 1
    
    # 3. OI Candles
    if settings.get('show_oi', 1):
        ap.append(mpf.make_addplot(df[['oi_open', 'oi_high', 'oi_low', 'oi_close']], panel=cur_p, type='candle', 
                                   up_color='#02c076', down_color='#f84960'))
        ratios.append(1.2); labels.append((cur_p, "<CoinGlass> Открытый интерес (Свечи) Coins open No Filter")); cur_p += 1
        
    # 4. Liquidations
    if settings.get('show_liq', 1):
        ap.append(mpf.make_addplot(df['liq_up'], panel=cur_p, type='bar', color='#02c076', width=0.6))
        ap.append(mpf.make_addplot(df['liq_down'], panel=cur_p, type='bar', color='#f84960', width=0.6))
        ratios.append(1.2); labels.append((cur_p, "<CoinGlass> Совокупные ликвидации Long No Filter")); cur_p += 1

    fig, axlist = mpf.plot(df, type='candle', style=s, volume=True, addplot=ap, figsize=(14, 16),
                           returnfig=True, panel_ratios=tuple(ratios), datetime_format='%H:%M', 
                           tight_layout=False, scale_padding=0)

    # Жесткая настройка границ для шкалы цен
    plt.subplots_adjust(left=0.05, right=0.88, top=0.94, bottom=0.08, hspace=0.3)

    ax_main = axlist[0]
    ax_main.yaxis.tick_right()
    ax_main.yaxis.set_label_position("right")

    # ЗОЛОТАЯ ЛИНИЯ
    ax_main.axhline(y=res_price, color='#f0b90b', linewidth=2, alpha=0.8)
    ax_main.text(0.5, res_price, f" {label_usd} F {res_price:.6f} ", color='black', fontweight='bold', 
                 ha='center', va='center', bbox=dict(boxstyle="round,pad=0.2", facecolor='#f0b90b', ec='none'))

    # ЦЕНА СПРАВА
    curr_price = df['close'].iloc[-1]
    ax_main.text(1.01, curr_price, f"{curr_price:.6f}", transform=ax_main.get_yaxis_transform(),
                 color='black', fontweight='bold', fontsize=10, ha='left', va='center',
                 bbox=dict(boxstyle='round,pad=0.3', fc='#02c076', ec='none'))

    # ВЕРХНИЙ ЗАГОЛОВОК
    title_str = f"{symbol}  {pumpdump_info['change_percent'] if pumpdump_info else ''}%"
    ax_main.text(0.01, 1.03, title_str, transform=ax_main.transAxes, fontsize=16, fontweight='bold', color='white' if is_dark else 'black')
    ax_main.text(0.99, 1.03, f"TF: {settings.get('timeframe', '5')}m", transform=ax_main.transAxes, fontsize=12, color='#707a8a', ha='right')

    # ВНУТРЕННИЕ ПОДПИСИ ПАНЕЛЕЙ
    axlist[2].set_title("Объем SMA 9", color='#02c076', loc='left', fontsize=8, pad=-10)
    for p_idx, text in labels:
        axlist[p_idx*2].set_title(text, color='#707a8a', loc='left', fontsize=8, pad=-10)

    # РАЗВОРОТНЫЙ ПАТТЕРН
    plt.figtext(0.5, 0.02, f"РАЗВОРОТНЫЙ ПАТТЕРН - {rev_prob}%", ha="center", fontsize=15, 
                fontweight='bold', color='#f0b90b', bbox=dict(facecolor='#1e2329', alpha=0.9, edgecolor='#f0b90b', pad=6))

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = f"/tmp/snapshots/{symbol}_{ts}.png"
    fig.savefig(path, dpi=120, facecolor=bg_color)
    plt.close(fig)
    return path
