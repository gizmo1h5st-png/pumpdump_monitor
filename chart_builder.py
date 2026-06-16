import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mplfinance as mpf
import matplotlib.ticker as mticker
from datetime import datetime

os.makedirs("/tmp/snapshots", exist_ok=True)

def human_format(num, pos=None):
    if abs(num) < 1 and num != 0: return f"{num:g}"
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    return '%.1f%s' % (num, ['', 'k', 'M', 'B', 'T'][magnitude])

def klines_to_df(klines):
    try:
        if not klines or len(klines) < 10: return pd.DataFrame()
        raw = np.array(klines, dtype=object)
        df = pd.DataFrame(data={
            'Open': raw[:, 1].astype(float),
            'High': raw[:, 2].astype(float),
            'Low': raw[:, 3].astype(float),
            'Close': raw[:, 4].astype(float),
            'Volume': raw[:, 5].astype(float),
            'Turnover': raw[:, 6].astype(float) if raw.shape[1] > 6 else (raw[:, 5].astype(float) * raw[:, 4].astype(float))
        }, index=pd.to_datetime(raw[:, 0].astype(float), unit='ms'))
        df.index.name = 'Date'
        df = df.sort_index()
        
        df['SMA9'] = df['Volume'].rolling(window=9).mean().fillna(df['Volume'])
        diff = (df['High'] - df['Low']).replace(0, 1)
        df['Delta'] = (((df['Close'] - df['Low']) / diff) * df['Volume']) - (df['Volume'] / 2)
        df['CVD_C'] = df['Delta'].cumsum()
        df['CVD_O'] = df['CVD_C'].shift(1).fillna(df['CVD_C'])
        df['OI_C'] = df['Turnover']
        df['OI_O'] = df['OI_C'].shift(1).fillna(df['OI_C'])
        df['Liq_U'] = np.where(df['Close'] < df['Open'], df['Volume'] * 0.1, 0)
        df['Liq_D'] = np.where(df['Close'] > df['Open'], -df['Volume'] * 0.08, 0)
        return df.fillna(0)
    except Exception: return pd.DataFrame()

def build_snapshot(symbol, klines, trades, settings: dict, pumpdump_info: dict = None) -> str:
    df = klines_to_df(klines)
    if df.empty: return ""
    
    max_turn = df['Turnover'].max()
    res_p = df.loc[df['Turnover'].idxmax(), 'High']
    label_usd = f"{max_turn/1000:.0f}k$"

    bg_color = '#0b0e11'
    text_color = '#cccccc'
    colors = mpf.make_marketcolors(up='#02c076', down='#f84960', inherit=True, volume='in', edge='inherit')
    s = mpf.make_mpf_style(base_mpf_style='charles', marketcolors=colors, facecolor=bg_color, 
                           edgecolor='#2b3139', gridcolor='#1e2329', gridstyle='solid',
                           rc={'font.size': 9, 'axes.labelcolor': text_color, 'xtick.color': '#555', 'ytick.color': text_color})

    ap = []
    ratios = [4]
    cur_p = 1
    headers = []

    ap.append(mpf.make_addplot(df['Volume'], panel=cur_p, type='bar', color='#02c076', alpha=0.3))
    if settings.get('show_sma', 1):
        ap.append(mpf.make_addplot(df['SMA9'], panel=cur_p, color='#00d2ff', width=1))
    ratios.append(1.2); headers.append((cur_p, "Volume SMA 9")); cur_p += 1

    if settings.get('show_delta', 1):
        c_df = df[['CVD_O', 'High', 'Low', 'CVD_C']].copy(); c_df.columns = ['Open', 'High', 'Low', 'Close']
        ap.append(mpf.make_addplot(c_df, panel=cur_p, type='candle'))
        ratios.append(1.2); headers.append((cur_p, "<CoinGlass> Cumulative Volume Delta (CVD)")); cur_p += 1
    
    if settings.get('show_oi', 1):
        o_df = df[['OI_O', 'High', 'Low', 'OI_C']].copy(); o_df.columns = ['Open', 'High', 'Low', 'Close']
        ap.append(mpf.make_addplot(o_df, panel=cur_p, type='candle'))
        ratios.append(1.2); headers.append((cur_p, "<CoinGlass> Open Interest (OI)")); cur_p += 1
        
    if settings.get('show_liq', 1):
        ap.append(mpf.make_addplot(df['Liq_U'], panel=cur_p, type='bar', color='#02c076', width=0.6))
        ap.append(mpf.make_addplot(df['Liq_D'], panel=cur_p, type='bar', color='#f84960', width=0.6))
        ratios.append(1.2); headers.append((cur_p, "<CoinGlass> Aggregate Liquidations")); cur_p += 1

    fig, axlist = mpf.plot(df[['Open', 'High', 'Low', 'Close']], type='candle', style=s, volume=False, addplot=ap, figsize=(15, 8 + cur_p*2),
                           returnfig=True, panel_ratios=tuple(ratios), datetime_format='%H:%M', tight_layout=False)

    plt.subplots_adjust(left=0.05, right=0.82, top=0.94, bottom=0.05, hspace=0.35)

    ax_main = axlist[0]
    
    # --- УЛУЧШЕННЫЙ HEATMAP С МЕТКАМИ ---
    if settings.get('show_heatmap', 1):
        p_min, p_max = df['Low'].min(), df['High'].max()
        bins = 100
        price_bins = np.linspace(p_min, p_max, bins)
        density = np.zeros((bins-1, len(df)))
        
        # Горизонтальный профиль (накопление ликвидности по уровням)
        profile = np.zeros(bins-1)
        
        for i in range(len(df)):
            h, l, v = df['High'].iloc[i], df['Low'].iloc[i], df['Volume'].iloc[i]
            mask = (price_bins[:-1] >= l) & (price_bins[1:] <= h)
            density[mask, i] = v
            profile[mask] += v
            
        # Рисуем карту с повышенной яркостью
        ax_main.imshow(density, interpolation='spline36', origin='lower', aspect='auto',
                       extent=[0, len(df)-1, p_min, p_max], cmap='magma', alpha=0.3, zorder=0)
        
        # Находим ТОП-3 уровня ликвидности для меток
        top_indices = np.argsort(profile)[-3:]
        for idx in top_indices:
            level_price = (price_bins[idx] + price_bins[idx+1]) / 2
            level_vol = profile[idx] * level_price
            # Рисуем слабую горизонтальную линию на уровне
            ax_main.axhline(y=level_price, color='#f0b90b', alpha=0.1, linewidth=0.5, linestyle=':')
            # Добавляем текстовую метку объема ликвидности
            ax_main.text(len(df)*0.1, level_price, f"{human_format(level_vol)}$", 
                         color='#f0b90b', fontsize=7, alpha=0.6, fontweight='bold', va='bottom')

    for i in range(0, len(axlist), 2):
        ax = axlist[i]
        ax.yaxis.tick_right(); ax.yaxis.set_label_position("right")
        if i == 0: ax.yaxis.set_major_formatter(mticker.ScalarFormatter(useOffset=False))
        else: ax.yaxis.set_major_formatter(mticker.FuncFormatter(human_format))
        ax.tick_params(axis='y', colors='white', labelsize=10, labelright=True)

    if res_p > 0:
        ax_main.axhline(y=res_p, color='#f0b90b', linewidth=2, alpha=0.7, zorder=10)
        ax_main.text(0.5, res_p, f" {label_usd} F {res_p:g} ", color='black', fontweight='bold', 
                     ha='center', va='center', bbox=dict(boxstyle="round,pad=0.2", facecolor='#f0b90b', ec='none'), zorder=11)

    curr_v = df['Close'].iloc[-1]
    ax_main.axhline(y=curr_v, color='#02c076', linestyle='--', linewidth=1.5, alpha=0.6, zorder=14)
    ax_main.annotate(f" {curr_v:g} ", xy=(1, curr_v), xycoords=('axes fraction', 'data'),
                     xytext=(10, 0), textcoords='offset points', color='black', fontweight='bold', 
                     fontsize=12, va='center', ha='left', bbox=dict(boxstyle='round,pad=0.3', fc='#02c076', ec='none'), zorder=15)

    title_str = f"{symbol}   {pumpdump_info['change_percent']:+.2f}%" if pumpdump_info else symbol
    ax_main.text(0, 1.05, title_str, transform=ax_main.transAxes, fontsize=20, fontweight='bold', color='white')
    ax_main.text(0.95, 1.05, f"TF: {settings.get('timeframe', '5')}m", transform=ax_main.transAxes, fontsize=14, color='#707a8a', ha='right')

    for p_idx, text in headers:
        axlist[p_idx*2].text(0.01, 0.85, text, transform=axlist[p_idx*2].transAxes, color='#707a8a', fontsize=8)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = f"/tmp/snapshots/{symbol}_{ts}.png"
    fig.savefig(path, dpi=120, facecolor=bg_color)
    plt.close(fig)
    return path
