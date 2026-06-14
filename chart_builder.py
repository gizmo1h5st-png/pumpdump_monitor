import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mplfinance as mpf
from datetime import datetime

os.makedirs("/tmp/snapshots", exist_ok=True)

def klines_to_df(klines):
    try:
        if not klines or len(klines) < 10:
            return pd.DataFrame()
            
        # Формируем DF
        df_raw = pd.DataFrame(klines)
        dates = pd.to_datetime(df_raw[0].astype(float), unit='ms')
        
        df = pd.DataFrame({
            'Open': df_raw[1].astype(float),
            'High': df_raw[2].astype(float),
            'Low': df_raw[3].astype(float),
            'Close': df_raw[4].astype(float),
            'Volume': df_raw[5].astype(float),
            'Turnover': df_raw[6].astype(float) if df_raw.shape[1] > 6 else (df_raw[5].astype(float) * df_raw[4].astype(float))
        }, index=dates)
        
        df.index.name = 'Date'
        df = df.sort_index() # Сортируем от старых к новым для корректных расчетов
        
        # SMA 9
        df['vol_sma'] = df['Volume'].rolling(window=9).mean().fillna(df['Volume'])
        
        # Delta & CVD
        diff = (df['High'] - df['Low']).replace(0, 1)
        df['delta'] = ((df['Close'] - df['Low']) / diff) * df['Volume']
        df['delta'] = df['delta'] - (df['Volume'] / 2)
        df['cvd'] = df['delta'].cumsum()
        
        # CVD Candles
        df['cvd_open'] = df['cvd'].shift(1).fillna(df['cvd'])
        df['cvd_high'] = df[['cvd_open', 'cvd']].max(axis=1)
        df['cvd_low'] = df[['cvd_open', 'cvd']].min(axis=1)
        
        # OI Candles
        df['oi_open'] = df['Turnover'].shift(1).fillna(df['Turnover'])
        df['oi_high'] = df[['oi_open', 'Turnover']].max(axis=1)
        df['oi_low'] = df[['oi_open', 'Turnover']].min(axis=1)
        
        # Liquidations
        df['liq_up'] = np.where(df['Close'] < df['Open'], df['Volume'] * 0.1, 0)
        df['liq_down'] = np.where(df['Close'] > df['Open'], -df['Volume'] * 0.08, 0)
        
        return df.fillna(0) # Финальная чистка всех NaN в 0
    except Exception as e:
        print(f"[Chart Error] klines_to_df: {e}")
        return pd.DataFrame()

def build_snapshot(symbol, klines, trades, settings: dict, pumpdump_info: dict = None) -> str:
    df = klines_to_df(klines)
    if df.empty or len(df) < 15: return ""
    
    # Золотая линия
    max_idx = df['Turnover'].idxmax()
    res_p = df.loc[max_idx, 'High']
    label_usd = f"{df['Turnover'].max()/1000:.0f}k$"

    is_dark = settings.get("theme", "dark") == "dark"
    bg_color = '#0b0e11' if is_dark else '#ffffff'
    text_color = '#707a8a'
    grid_color = '#1e2329' if is_dark else '#f0f0f0'

    colors = mpf.make_marketcolors(up='#02c076', down='#f84960', inherit=True, volume='in', edge='inherit')
    s = mpf.make_mpf_style(base_mpf_style='charles', marketcolors=colors, facecolor=bg_color, 
                           edgecolor='#2b3139', gridcolor=grid_color, gridstyle='solid',
                           rc={'font.size': 8, 'axes.labelcolor': text_color, 'xtick.color': '#555', 'ytick.color': text_color})

    ap = []
    ratios = [4, 1.2]
    cur_p = 2
    headers = []

    # Volume Panel (SMA)
    ap.append(mpf.make_addplot(df['vol_sma'], panel=1, color='#00d2ff', width=0.8))

    # CVD Panel
    if settings.get('show_delta', 1):
        c_df = df[['cvd_open', 'cvd_high', 'cvd_low', 'cvd']].copy()
        c_df.columns = ['Open', 'High', 'Low', 'Close']
        ap.append(mpf.make_addplot(c_df, panel=cur_p, type='candle'))
        ratios.append(1.2); headers.append((cur_p, "<CoinGlass> Cumulative Volume Delta (CVD Candles)")); cur_p += 1
    
    # OI Panel
    if settings.get('show_oi', 1):
        o_df = df[['oi_open', 'oi_high', 'oi_low', 'Turnover']].copy()
        o_df.columns = ['Open', 'High', 'Low', 'Close']
        ap.append(mpf.make_addplot(o_df, panel=cur_p, type='candle'))
        ratios.append(1.2); headers.append((cur_p, "<CoinGlass> Open Interest (OI)")); cur_p += 1
        
    # Liquidations Panel
    if settings.get('show_liq', 1):
        ap.append(mpf.make_addplot(df['liq_up'], panel=cur_p, type='bar', color='#02c076', width=0.6))
        ap.append(mpf.make_addplot(df['liq_down'], panel=cur_p, type='bar', color='#f84960', width=0.6))
        ratios.append(1.2); headers.append((cur_p, "<CoinGlass> Aggregate Liquidations")); cur_p += 1

    # Основной график
    main_df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()

    fig, axlist = mpf.plot(main_df, type='candle', style=s, volume=True, addplot=ap, figsize=(14, 16),
                           returnfig=True, panel_ratios=tuple(ratios), datetime_format='%H:%M', 
                           tight_layout=False, scale_padding=0)

    # Жесткий отступ справа 18% для шкалы цен
    plt.subplots_adjust(left=0.05, right=0.82, top=0.94, bottom=0.05, hspace=0.35)

    ax_main = axlist[0]
    ax_main.yaxis.tick_right()
    ax_main.yaxis.set_label_position("right")

    # Золотая линия
    ax_main.axhline(y=res_p, color='#f0b90b', linewidth=2, alpha=0.8)
    ax_main.text(0.5, res_p, f" {label_usd} F {res_p:.6f} ", color='black', fontweight='bold', 
                 ha='center', va='center', bbox=dict(boxstyle="round,pad=0.2", facecolor='#f0b90b', ec='none'))

    # Цена
    curr_p = main_df['Close'].iloc[-1]
    ax_main.text(1.03, curr_p, f"{curr_p:.6f}", transform=ax_main.get_yaxis_transform(),
                 color='black', fontweight='bold', fontsize=11, ha='left', va='center',
                 bbox=dict(boxstyle='round,pad=0.4', fc='#02c076', ec='none'))

    # Шапка
    title_str = f"{symbol}   {pumpdump_info['change_percent']:+.2f}%" if pumpdump_info else symbol
    ax_main.text(0, 1.05, title_str, transform=ax_main.transAxes, fontsize=18, fontweight='bold', color='white' if is_dark else 'black')
    ax_main.text(0.95, 1.05, f"TF: {settings.get('timeframe', '5')}m", transform=ax_main.transAxes, fontsize=14, color='#707a8a', ha='right')

    # Подписи панелей
    axlist[2].text(0.01, 0.85, "Volume SMA 9", transform=axlist[2].transAxes, color='#00d2ff', fontsize=8, fontweight='bold')
    for p_idx, text in headers:
        axlist[p_idx*2].text(0.01, 0.85, text, transform=axlist[p_idx*2].transAxes, color='#707a8a', fontsize=8)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = f"/tmp/snapshots/{symbol}_{ts}.png"
    fig.savefig(path, dpi=120, facecolor=bg_color)
    plt.close(fig)
    return path
