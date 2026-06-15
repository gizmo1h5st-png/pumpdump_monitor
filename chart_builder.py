import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mplfinance as mpf
import matplotlib.ticker as mticker
from datetime import datetime

os.makedirs("/tmp/snapshots", exist_ok=True)

def klines_to_df(klines):
    try:
        if not klines or len(klines) < 10: return pd.DataFrame()
        raw = pd.DataFrame(klines)
        df = pd.DataFrame(index=pd.to_datetime(raw[0].astype(float), unit='ms'))
        df['Open'] = raw[1].astype(float); df['High'] = raw[2].astype(float)
        df['Low'] = raw[3].astype(float); df['Close'] = raw[4].astype(float)
        df['Volume'] = raw[5].astype(float)
        df['Turnover'] = raw[6].astype(float) if raw.shape[1] > 6 else (df['Volume'] * df['Close'])
        df = df.sort_index()
        if df['Close'].max() <= 0: return pd.DataFrame()
        
        df['SMA9'] = df['Volume'].rolling(window=9).mean().fillna(df['Volume'])
        diff = (df['High'] - df['Low']).replace(0, 1)
        df['Delta'] = (((df['Close'] - df['Low']) / diff) * df['Volume']) - (df['Volume'] / 2)
        df['CVD'] = df['Delta'].cumsum()
        df['CVD_O'] = df['CVD'].shift(1).fillna(df['CVD'])
        df['OI_O'] = df['Turnover'].shift(1).fillna(df['Turnover'])
        df['liq_u'] = np.where(df['Close'] < df['Open'], df['Volume'] * 0.1, 0)
        df['liq_d'] = np.where(df['Close'] > df['Open'], -df['Volume'] * 0.08, 0)
        return df.fillna(0)
    except Exception: return pd.DataFrame()

def build_snapshot(symbol, klines, trades, settings: dict, pumpdump_info: dict = None) -> str:
    df = klines_to_df(klines)
    if df.empty: return ""
    
    max_idx = df['Turnover'].idxmax(); res_p = df.loc[max_idx, 'High']
    label_usd = f"{df['Turnover'].max()/1000:.0f}k$"

    is_dark = settings.get("theme", "dark") == "dark"
    bg_color = '#0b0e11'
    text_color = '#cccccc' # Сделали ярче

    colors = mpf.make_marketcolors(up='#02c076', down='#f84960', inherit=True, volume='in', edge='inherit')
    s = mpf.make_mpf_style(base_mpf_style='charles', marketcolors=colors, facecolor=bg_color, 
                           edgecolor='#2b3139', gridcolor='#1e2329', gridstyle='solid',
                           rc={'font.size': 9, 'axes.labelcolor': text_color, 'xtick.color': '#888', 'ytick.color': '#ffffff'})

    ap = []
    ap.append(mpf.make_addplot(df['Volume'], panel=1, type='bar', color='#02c076', alpha=0.3))
    ap.append(mpf.make_addplot(df['SMA9'], panel=1, color='#00d2ff', width=1))
    
    ratios = [4, 1.2]; cur_p = 2; headers = [(1, "Volume SMA 9")]

    if settings.get('show_delta', 1):
        c_df = df[['CVD_O', 'High', 'Low', 'CVD']].copy(); c_df.columns = ['Open', 'High', 'Low', 'Close']
        ap.append(mpf.make_addplot(c_df, panel=cur_p, type='candle'))
        ratios.append(1.2); headers.append((cur_p, "<CoinGlass> Cumulative Volume Delta (CVD Candles)")); cur_p += 1
    
    if settings.get('show_oi', 1):
        o_df = df[['OI_O', 'High', 'Low', 'Turnover']].copy(); o_df.columns = ['Open', 'High', 'Low', 'Close']
        ap.append(mpf.make_addplot(o_df, panel=cur_p, type='candle'))
        ratios.append(1.2); headers.append((cur_p, "<CoinGlass> Open Interest (OI)")); cur_p += 1
        
    if settings.get('show_liq', 1):
        ap.append(mpf.make_addplot(df['liq_u'], panel=cur_p, type='bar', color='#02c076', width=0.6))
        ap.append(mpf.make_addplot(df['liq_d'], panel=cur_p, type='bar', color='#f84960', width=0.6))
        ratios.append(1.2); headers.append((cur_p, "<CoinGlass> Aggregate Liquidations")); cur_p += 1

    fig, axlist = mpf.plot(df[['Open', 'High', 'Low', 'Close']], type='candle', style=s, volume=False, addplot=ap, figsize=(15, 16),
                           returnfig=True, panel_ratios=tuple(ratios), datetime_format='%H:%M', tight_layout=False)

    # Жесткая настройка отступов: 22% под цену (right=0.78)
    plt.subplots_adjust(left=0.05, right=0.78, top=0.94, bottom=0.05, hspace=0.35)

    # Настройка ВСЕХ шкал цен (оси в axlist: 0, 2, 4, 6...)
    for i in range(0, len(axlist), 2):
        ax = axlist[i]
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")
        ax.yaxis.set_major_formatter(mticker.ScalarFormatter(useOffset=False))
        ax.tick_params(axis='y', colors='white', labelsize=10) # Делаем цифры белыми и крупными

    ax_main = axlist[0]
    
    # Золотая линия
    if res_p > 0:
        ax_main.axhline(y=res_p, color='#f0b90b', linewidth=2, alpha=0.8, zorder=10)
        ax_main.text(0.5, res_p, f" {label_usd} F {res_p:.6f} ", color='black', fontweight='bold', 
                     ha='center', va='center', bbox=dict(boxstyle="round,pad=0.2", facecolor='#f0b90b', ec='none'), zorder=11)

    # Метка текущей цены - ГЛАВНЫЙ ФИКС
    curr_v = df['Close'].iloc[-1]
    ax_main.text(1.02, curr_v, f" {curr_v:.6f} ", transform=ax_main.get_yaxis_transform(),
                 color='black', fontweight='bold', fontsize=12, ha='left', va='center',
                 bbox=dict(boxstyle='round,pad=0.3', fc='#02c076', ec='none'), zorder=15)

    # Шапка
    title_str = f"{symbol}   {pumpdump_info['change_percent']:+.2f}%" if pumpdump_info else symbol
    ax_main.text(0, 1.05, title_str, transform=ax_main.transAxes, fontsize=20, fontweight='bold', color='white')
    ax_main.text(0.98, 1.05, f"TF: {settings.get('timeframe', '5')}m", transform=ax_main.transAxes, fontsize=14, color='#707a8a', ha='right')

    # Подписи
    for p_idx, text in headers:
        axlist[p_idx*2].text(0.01, 0.85, text, transform=axlist[p_idx*2].transAxes, color='#707a8a', fontsize=8)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = f"/tmp/snapshots/{symbol}_{ts}.png"
    fig.savefig(path, dpi=120, facecolor=bg_color)
    plt.close(fig)
    return path
