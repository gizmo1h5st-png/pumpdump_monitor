import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mplfinance as mpf
from datetime import datetime

os.makedirs("/tmp/snapshots", exist_ok=True)

def klines_to_df(klines):
    # Bybit: [t, open, high, low, close, volume, turnover]
    df = pd.DataFrame(klines, columns=["Date","Open","High","Low","Close","Volume","Turnover"])
    df = df.astype(float)
    df["Date"] = pd.to_datetime(df["Date"], unit="ms")
    df.set_index("Date", inplace=True)
    df = df.iloc[::-1]
    
    # 1. Volume SMA 9
    df['vol_sma'] = df['Volume'].rolling(window=9).mean()
    
    # 2. CVD (Cumulative Volume Delta)
    df['delta'] = ((df['Close'] - df['Low']) / (df['High'] - df['Low']).replace(0, 1)) * df['Volume']
    df['delta'] = df['delta'] - (df['Volume'] / 2)
    df['cvd_close'] = df['delta'].cumsum()
    df['cvd_open'] = df['cvd_close'].shift(1).fillna(df['cvd_close'] * 0.99)
    df['cvd_high'] = df[['cvd_open', 'cvd_close']].max(axis=1)
    df['cvd_low'] = df[['cvd_open', 'cvd_close']].min(axis=1)
    
    # 3. OI (Open Interest Emulation)
    df['oi_close'] = df['Turnover']
    df['oi_open'] = df['oi_close'].shift(1).fillna(df['oi_close'] * 0.99)
    df['oi_high'] = df[['oi_open', 'oi_close']].max(axis=1)
    df['oi_low'] = df[['oi_open', 'oi_close']].min(axis=1)
    
    # 4. Liquidations
    df['liq_up'] = np.where(df['Close'] < df['Open'], df['Volume'] * 0.1, 0)
    df['liq_down'] = np.where(df['Close'] > df['Open'], -df['Volume'] * 0.08, 0)
    
    return df

def build_snapshot(symbol, klines, trades, settings: dict, pumpdump_info: dict = None) -> str:
    if not klines or len(klines) < 20: return ""
    df = klines_to_df(klines)
    
    # Расчет "Золотой линии"
    max_turnover = df['Turnover'].max()
    res_price = df.loc[df['Turnover'].idxmax(), 'High']
    label_usd = f"{max_turnover/1000:.0f}k$"

    is_dark = settings.get("theme", "dark") == "dark"
    bg_color = '#0b0e11' if is_dark else '#ffffff'
    text_color = '#707a8a'
    grid_color = '#1e2329' if is_dark else '#f0f0f0'

    # Настройка цветов
    colors = mpf.make_marketcolors(up='#02c076', down='#f84960', inherit=True, volume='in', edge='inherit')
    s = mpf.make_mpf_style(base_mpf_style='charles', marketcolors=colors, facecolor=bg_color, 
                           edgecolor='#2b3139', gridcolor=grid_color, gridstyle='solid',
                           rc={'font.size': 8, 'axes.labelcolor': text_color, 'xtick.color': '#555', 'ytick.color': text_color})

    ap = []
    ratios = [4, 1.2]
    cur_p = 2
    headers = []

    # SMA 9 на объеме
    ap.append(mpf.make_addplot(df['vol_sma'], panel=1, color='#00d2ff', width=0.8))

    # 2. CVD Candles
    if settings.get('show_delta', 1):
        cvd_df = df[['cvd_open', 'cvd_high', 'cvd_low', 'cvd_close']].copy()
        cvd_df.columns = ['Open', 'High', 'Low', 'Close']
        ap.append(mpf.make_addplot(cvd_df, panel=cur_p, type='candle'))
        ratios.append(1.2); headers.append((cur_p, "<CoinGlass> Cumulative Volume Delta (CVD Candles) 0 open No Filter")); cur_p += 1
    
    # 3. OI Candles
    if settings.get('show_oi', 1):
        oi_df = df[['oi_open', 'oi_high', 'oi_low', 'oi_close']].copy()
        oi_df.columns = ['Open', 'High', 'Low', 'Close']
        ap.append(mpf.make_addplot(oi_df, panel=cur_p, type='candle'))
        ratios.append(1.2); headers.append((cur_p, "<CoinGlass> Открытый интерес (Свечи) Coins open No Filter")); cur_p += 1
        
    # 4. Liquidations
    if settings.get('show_liq', 1):
        ap.append(mpf.make_addplot(df['liq_up'], panel=cur_p, type='bar', color='#02c076', width=0.6))
        ap.append(mpf.make_addplot(df['liq_down'], panel=cur_p, type='bar', color='#f84960', width=0.6))
        ratios.append(1.2); headers.append((cur_p, "<CoinGlass> Совокупные ликвидации Long No Filter")); cur_p += 1

    fig, axlist = mpf.plot(df, type='candle', style=s, volume=True, addplot=ap, figsize=(14, 16),
                           returnfig=True, panel_ratios=tuple(ratios), datetime_format='%H:%M', 
                           tight_layout=False, scale_padding=0)

    # Фиксируем отступ справа
    plt.subplots_adjust(left=0.05, right=0.82, top=0.94, bottom=0.05, hspace=0.35)

    ax_main = axlist[0]
    ax_main.yaxis.tick_right()
    ax_main.yaxis.set_label_position("right")

    # ЗОЛОТАЯ ЛИНИЯ
    ax_main.axhline(y=res_price, color='#f0b90b', linewidth=2, alpha=0.8)
    ax_main.text(0.5, res_price, f" {label_usd} F {res_price:.6f} ", color='black', fontweight='bold', 
                 ha='center', va='center', bbox=dict(boxstyle="round,pad=0.2", facecolor='#f0b90b', ec='none'))

    # ЦЕНА СПРАВА
    curr_price = df['Close'].iloc[-1]
    ax_main.text(1.03, curr_price, f"{curr_price:.6f}", transform=ax_main.get_yaxis_transform(),
                 color='black', fontweight='bold', fontsize=11, ha='left', va='center',
                 bbox=dict(boxstyle='round,pad=0.4', fc='#02c076', ec='none'))

    # ШАПКА
    title_str = f"{symbol}   {pumpdump_info['change_percent']:+.2f}%" if pumpdump_info else symbol
    ax_main.text(0, 1.05, title_str, transform=ax_main.transAxes, fontsize=18, fontweight='bold', color='white' if is_dark else 'black')
    ax_main.text(1, 1.05, f"TF: {settings.get('timeframe', '5')}m", transform=ax_main.transAxes, fontsize=14, color='#707a8a', ha='right')

    # ПОДПИСИ
    axlist[2].text(0.01, 0.85, "Объем SMA 9", transform=axlist[2].transAxes, color='#00d2ff', fontsize=8, fontweight='bold')
    for p_idx, text in headers:
        axlist[p_idx*2].text(0.01, 0.85, text, transform=axlist[p_idx*2].transAxes, color='#707a8a', fontsize=8)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = f"/tmp/snapshots/{symbol}_{ts}.png"
    fig.savefig(path, dpi=120, facecolor=bg_color)
    plt.close(fig)
    return path
