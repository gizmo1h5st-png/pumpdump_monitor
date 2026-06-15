import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mplfinance as mpf
from datetime import datetime

os.makedirs("/tmp/snapshots", exist_ok=True)

def klines_to_df(klines):
    try:
        if not klines or not isinstance(klines, list) or len(klines) < 10:
            return pd.DataFrame()
            
        data = []
        for k in klines:
            if len(k) >= 6:
                data.append({
                    'Date': float(k[0]),
                    'Open': float(k[1]),
                    'High': float(k[2]),
                    'Low': float(k[3]),
                    'Close': float(k[4]),
                    'Volume': float(k[5]),
                    'Turnover': float(k[6]) if len(k) > 6 else float(k[5]) * float(k[4])
                })
        
        df = pd.DataFrame(data)
        if df.empty: return pd.DataFrame()

        df['Date'] = pd.to_datetime(df['Date'], unit='ms')
        df.set_index('Date', inplace=True)
        df.sort_index(inplace=True)

        if df['Close'].max() <= 0: return pd.DataFrame()

        # SMA9
        df['SMA9'] = df['Volume'].rolling(window=9).mean().fillna(df['Volume'])
        
        # Delta & CVD
        diff = (df['High'] - df['Low']).replace(0, 1)
        df['Delta'] = (((df['Close'] - df['Low']) / diff) * df['Volume']) - (df['Volume'] / 2)
        df['CVD_C'] = df['Delta'].cumsum()
        df['CVD_O'] = df['CVD_C'].shift(1).fillna(df['CVD_C'])
        
        # OI
        df['OI_C'] = df['Turnover']
        df['OI_O'] = df['OI_C'].shift(1).fillna(df['OI_C'])
        
        # Liquidations
        df['Liq_U'] = np.where(df['Close'] < df['Open'], df['Volume'] * 0.1, 0)
        df['Liq_D'] = np.where(df['Close'] > df['Open'], -df['Volume'] * 0.08, 0)
        
        return df.fillna(0)
    except Exception as e:
        print(f"[Chart Error] Data processing: {e}")
        return pd.DataFrame()

def build_snapshot(symbol, klines, trades, settings: dict, pumpdump_info: dict = None) -> str:
    df = klines_to_df(klines)
    if df.empty: return ""
    
    max_turn = df['Turnover'].max()
    res_p = df.loc[df['Turnover'].idxmax(), 'High']
    label_usd = f"{max_turn/1000:.0f}k$"

    bg_color = '#0b0e11'
    text_color = '#707a8a'
    grid_color = '#1e2329'

    colors = mpf.make_marketcolors(up='#02c076', down='#f84960', inherit=True, volume='in', edge='inherit')
    s = mpf.make_mpf_style(base_mpf_style='charles', marketcolors=colors, facecolor=bg_color, 
                           edgecolor='#2b3139', gridcolor=grid_color, gridstyle='solid',
                           rc={'font.size': 8, 'axes.labelcolor': text_color, 'xtick.color': '#555', 'ytick.color': text_color})

    ap = []
    ratios = [4, 1.2]
    cur_p = 2
    headers = [(1, "Volume SMA 9")]

    # Panel 1: Volume
    ap.append(mpf.make_addplot(df['Volume'], panel=1, type='bar', color='#02c076', alpha=0.3))
    ap.append(mpf.make_addplot(df['SMA9'], panel=1, color='#00d2ff', width=0.8))

    # Panel 2: CVD
    if settings.get('show_delta', 1):
        c_df = df[['CVD_O', 'High', 'Low', 'CVD_C']].copy(); c_df.columns = ['Open', 'High', 'Low', 'Close']
        ap.append(mpf.make_addplot(c_df, panel=cur_p, type='candle'))
        ratios.append(1.2); headers.append((cur_p, "<CoinGlass> Cumulative Volume Delta (CVD Candles)")); cur_p += 1
    
    # Panel 3: OI
    if settings.get('show_oi', 1):
        o_df = df[['OI_O', 'High', 'Low', 'OI_C']].copy(); o_df.columns = ['Open', 'High', 'Low', 'Close']
        ap.append(mpf.make_addplot(o_df, panel=cur_p, type='candle'))
        ratios.append(1.2); headers.append((cur_p, "<CoinGlass> Open Interest (OI)")); cur_p += 1
        
    # Panel 4: Liquidations
    if settings.get('show_liq', 1):
        ap.append(mpf.make_addplot(df['Liq_U'], panel=cur_p, type='bar', color='#02c076', width=0.6))
        ap.append(mpf.make_addplot(df['Liq_D'], panel=cur_p, type='bar', color='#f84960', width=0.6))
        ratios.append(1.2); headers.append((cur_p, "<CoinGlass> Aggregate Liquidations")); cur_p += 1

    fig, axlist = mpf.plot(df[['Open', 'High', 'Low', 'Close']], type='candle', style=s, volume=False, addplot=ap, figsize=(14, 16),
                           returnfig=True, panel_ratios=tuple(ratios), datetime_format='%H:%M', 
                           tight_layout=False, scale_padding=0)

    plt.subplots_adjust(left=0.05, right=0.80, top=0.94, bottom=0.05, hspace=0.35)

    ax_main = axlist[0]
    ax_main.yaxis.tick_right()
    ax_main.yaxis.set_label_position("right")

    if res_p > 0:
        ax_main.axhline(y=res_p, color='#f0b90b', linewidth=2, alpha=0.8)
        ax_main.text(0.5, res_p, f" {label_usd} F {res_p:.6f} ", color='black', fontweight='bold', 
                     ha='center', va='center', bbox=dict(boxstyle="round,pad=0.2", facecolor='#f0b90b', ec='none'))

    curr_v = df['Close'].iloc[-1]
    ax_main.text(1.02, curr_v, f"{curr_v:.6f}", transform=ax_main.get_yaxis_transform(),
                 color='black', fontweight='bold', fontsize=11, ha='left', va='center',
                 bbox=dict(boxstyle='round,pad=0.4', fc='#02c076', ec='none'))

    title_str = f"{symbol}   {pumpdump_info['change_percent']:+.2f}%" if pumpdump_info else symbol
    ax_main.text(0, 1.05, title_str, transform=ax_main.transAxes, fontsize=20, fontweight='bold', color='white')
    ax_main.text(0.98, 1.05, f"TF: {settings.get('timeframe', '5')}m", transform=ax_main.transAxes, fontsize=14, color='#707a8a', ha='right')

    for p_idx, text in headers:
        axlist[p_idx*2].text(0.01, 0.85, text, transform=axlist[p_idx*2].transAxes, color='#707a8a', fontsize=8)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = f"/tmp/snapshots/{symbol}_{ts}.png"
    fig.savefig(path, dpi=120, facecolor=bg_color)
    plt.close(fig)
    return path
