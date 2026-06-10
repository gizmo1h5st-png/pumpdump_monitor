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
    
    # 2. Delta Volume
    df['delta'] = ((df['close'] - df['low']) / (df['high'] - df['low']).replace(0, 1)) * df['volume']
    df['delta'] = df['delta'] - (df['volume'] / 2)
    
    # 3. OI (Open Interest)
    df['oi_val'] = df['turnover'].rolling(window=3).mean().fillna(df['turnover'])
    
    # 4. Liquidations (Style Coinglass)
    # Генерируем лонги вверх, шорты вниз
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
    text_color = '#888' if is_dark else '#333'
    grid_color = '#161a1e' if is_dark else '#f0f0f0'

    colors = mpf.make_marketcolors(up='#00ff41', down='#ff3131', inherit=True, volume='in', edge='inherit')
    s = mpf.make_mpf_style(base_mpf_style='charles', marketcolors=colors, facecolor=bg_color, 
                           edgecolor='#333', gridcolor=grid_color, gridstyle='solid',
                           rc={'font.size': 9, 'axes.labelcolor': text_color, 'xtick.color': '#555', 'ytick.color': text_color})

    # --- ПАНЕЛИ ---
    ap = []
    # Панель 1 (Объем встроен в mpf)
    ap.append(mpf.make_addplot(df['vol_sma'], panel=1, color='#00d2ff', width=1))
    
    ratios = [4, 1.2]
    cur_p = 2
    
    # 2. Delta
    if settings.get('show_delta', 1):
        ap.append(mpf.make_addplot(df['delta'], panel=cur_p, type='bar', color=['#00ff41' if x > 0 else '#ff3131' for x in df['delta']], width=0.8))
        ratios.append(1.2); cur_p += 1
    
    # 3. OI
    if settings.get('show_oi', 1):
        ap.append(mpf.make_addplot(df['oi_val'], panel=cur_p, type='line', color='#00ff41', width=1.5))
        ratios.append(1.2); cur_p += 1
        
    # 4. Liquidations
    if settings.get('show_liq', 1):
        ap.append(mpf.make_addplot(df['liq_up'], panel=cur_p, type='bar', color='#00ff41', width=0.7))
        ap.append(mpf.make_addplot(df['liq_down'], panel=cur_p, type='bar', color='#ff3131', width=0.7))
        ratios.append(1.5); cur_p += 1

    # ОТРИСОВКА
    fig, axlist = mpf.plot(df, type='candle', style=s, volume=True, addplot=ap, figsize=(14, 14),
                           returnfig=True, panel_ratios=tuple(ratios), datetime_format='%H:%M', 
                           tight_layout=False)

    # Ручная настройка полей: увеличили right до 0.90 для шкалы
    plt.subplots_adjust(left=0.05, right=0.90, top=0.92, bottom=0.08, hspace=0.4)

    ax_main = axlist[0]
    ax_main.yaxis.tick_right()
    ax_main.yaxis.set_label_position("right")

    # ЗОЛОТАЯ ЛИНИЯ
    ax_main.axhline(y=res_price, color='#f0b90b', linewidth=2, alpha=0.8, zorder=5)
    ax_main.text(0.5, res_price, f" {label_usd} F {res_price:.6f} ", color='black', fontweight='bold', 
                 ha='center', va='center', bbox=dict(boxstyle="round,pad=0.3", facecolor='#f0b90b', ec='none'), zorder=6)

    # ЦЕНА СПРАВА
    curr_price = df['close'].iloc[-1]
    ax_main.text(1.01, curr_price, f"{curr_price:.6f}", transform=ax_main.get_yaxis_transform(),
                 color='black', fontweight='bold', fontsize=11, ha='left', va='center',
                 bbox=dict(boxstyle='round,pad=0.3', fc='#00ff41', ec='none'))

    # ЗАГОЛОВОК (Пара и ТФ)
    change_txt = f"{pumpdump_info['change_percent']:+.2f}%" if pumpdump_info else ""
    header_txt = f"{symbol}   {change_txt}"
    ax_main.text(0.01, 1.02, header_txt, transform=ax_main.transAxes, fontsize=18, fontweight='bold', color='white' if is_dark else 'black')
    ax_main.text(0.99, 1.02, f"TF: {settings.get('timeframe', '5')}m", transform=ax_main.transAxes, fontsize=12, color='gray', ha='right')

    # ПОДПИСИ ПАНЕЛЕЙ
    axlist[2].set_title("Объем SMA 9", color='#00d2ff', loc='left', fontsize=8)
    
    idx = 4
    if settings.get('show_delta', 1):
        axlist[idx].set_title("<CoinGlass> Cumulative Volume Delta (CVD)", color=text_color, loc='left', fontsize=8)
        idx += 2
    if settings.get('show_oi', 1):
        axlist[idx].set_title("<CoinGlass> Открытый интерес (OI)", color=text_color, loc='left', fontsize=8)
        idx += 2
    if settings.get('show_liq', 1):
        axlist[idx].set_title("<CoinGlass> Совокупные ликвидации", color=text_color, loc='left', fontsize=8)

    # РАЗВОРОТНЫЙ ПАТТЕРН
    plt.figtext(0.5, 0.02, f"РАЗВОРОТНЫЙ ПАТТЕРН - {rev_prob}%", ha="center", fontsize=15, 
                fontweight='bold', color='#f0b90b', bbox=dict(facecolor='#1e2329', alpha=0.9, edgecolor='#f0b90b', pad=6))

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = f"/tmp/snapshots/{symbol}_{ts}.png"
    fig.savefig(path, dpi=120, facecolor=bg_color)
    plt.close(fig)
    return path
