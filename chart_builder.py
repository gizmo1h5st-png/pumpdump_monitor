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
    
    # Расчет SMA и Дельты
    df['vol_sma'] = df['volume'].rolling(window=9).mean()
    df['delta'] = ((df['close'] - df['low']) / (df['high'] - df['low']).replace(0, 1)) * df['volume']
    df['delta'] = df['delta'] - (df['volume'] / 2)
    df['cvd'] = df['delta'].cumsum()
    
    # Эмуляция OI
    df['oi_close'] = df['turnover'].rolling(window=3).mean().fillna(df['turnover'])
    
    # Ликвидации
    df['liq_long'] = np.where(df['close'] < df['open'], df['volume'] * 0.15 * (df['high'] - df['close'])/(df['high']-df['low']).replace(0,1), 0)
    df['liq_short'] = np.where(df['close'] > df['open'], -df['volume'] * 0.12 * (df['open'] - df['low'])/(df['high']-df['low']).replace(0,1), 0)
    
    return df

def calculate_reversal_score(df):
    """Кластерный анализ вероятности разворота (0-100%)"""
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    score = 15 # Базовая волатильность
    
    # 1. Дивергенция Дельты (Цена вверх, дельта вниз)
    if (last['close'] > last['open'] and last['delta'] < 0) or (last['close'] < last['open'] and last['delta'] > 0):
        score += 35
        
    # 2. Поглощение в тенях (Длинная верхняя тень на объеме при пампе)
    upper_shadow = last['high'] - max(last['close'], last['open'])
    body = abs(last['close'] - last['open'])
    if last['volume'] > last['vol_sma'] * 1.5 and upper_shadow > body:
        score += 30
        
    # 3. Истощение (Объем падает, цена еще идет по инерции)
    if last['volume'] < prev['volume'] * 0.7 and abs(last['close'] - prev['close']) > abs(prev['close'] - df.iloc[-3]['close']):
        score += 20

    return min(score, 99)

def build_snapshot(symbol, klines, trades, settings: dict, pumpdump_info: dict = None) -> str:
    if not klines or len(klines) < 20: return ""
    df = klines_to_df(klines)
    
    rev_probability = calculate_reversal_score(df)
    
    max_vol_idx = df['volume'].idxmax()
    res_price = df.loc[max_vol_idx, 'high']
    max_vol_usd = (df['volume'].max() * res_price) / 1000 

    # Темы
    is_dark = settings.get("theme", "dark") == "dark"
    bg_color = '#0b0e11' if is_dark else '#ffffff'
    text_color = '#888' if is_dark else '#333'
    grid_color = '#161a1e' if is_dark else '#f0f0f0'

    colors = mpf.make_marketcolors(up='#00ff41', down='#ff3131', inherit=True, volume='in', edge='inherit')
    s = mpf.make_mpf_style(base_mpf_style='charles', marketcolors=colors, facecolor=bg_color, 
                           edgecolor='#222', gridcolor=grid_color, gridstyle='solid',
                           rc={'font.size': 8, 'axes.labelcolor': text_color, 'xtick.color': '#555', 'ytick.color': '#888'})

    ap = []
    ratios = [4, 1]
    if settings.get('show_delta', 1):
        ap.append(mpf.make_addplot(df['delta'], panel=len(ap)+1, type='bar', color=['#00ff41' if x > 0 else '#ff3131' for x in df['delta']], width=0.8, ylabel='Delta'))
        ratios.append(1)
    if settings.get('show_oi', 1):
        ap.append(mpf.make_addplot(df['oi_close'], panel=len(ap)+1, type='line', color='#00ff41', width=1, ylabel='OI'))
        ratios.append(1)
    if settings.get('show_liq', 1):
        p_idx = len(ap)+1
        ap.append(mpf.make_addplot(df['cvd'], panel=p_idx, type='line', color='#ff00ff', width=1, ylabel='Liq'))
        ap.append(mpf.make_addplot(df['liq_long'], panel=p_idx, type='bar', color='#00ff41', width=0.7))
        ap.append(mpf.make_addplot(df['liq_short'], panel=p_idx, type='bar', color='#ff3131', width=0.7))
        ratios.append(1.5)

    fig, axlist = mpf.plot(df, type='candle', style=s, volume=True, addplot=ap, figsize=(12, 12),
                           returnfig=True, panel_ratios=tuple(ratios), datetime_format='%H:%M', tight_layout=True)

    ax_main = axlist[0]
    ax_main.yaxis.tick_right()
    ax_main.yaxis.set_label_position("right")
    
    # Золотая линия
    ax_main.axhline(y=res_price, color='#f0b90b', linewidth=2)
    ax_main.text(0.5, res_price, f" {max_vol_usd:.0f}k$ F {res_price:.6f} ", color='black', fontweight='bold', 
                 ha='center', bbox=dict(boxstyle="round", facecolor='#f0b90b'))

    # Метка цены
    current_price = df['close'].iloc[-1]
    ax_main.text(1.01, current_price, f"{current_price:.6f}", transform=ax_main.get_yaxis_transform(),
                 color='black' if not is_dark else 'white', fontweight='bold', bbox=dict(fc='#00ff41', ec='none'))

    # РАЗВОРОТНЫЙ ПАТТЕРН ТЕКСТ (внизу)
    plt.figtext(0.5, 0.01, f"РАЗВОРОТНЫЙ ПАТТЕРН - {rev_probability}%", ha="center", fontsize=14, 
                fontweight='bold', color='#f0b90b', bbox=dict(facecolor='#1e2329', alpha=0.8, edgecolor='#f0b90b', pad=5))

    # Сохранение
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = f"/tmp/snapshots/{symbol}_{ts}.png"
    fig.savefig(path, dpi=130, facecolor=bg_color)
    plt.close(fig)
    return path
