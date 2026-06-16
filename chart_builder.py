import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mplfinance as mpf
import matplotlib.ticker as mticker
from datetime import datetime

os.makedirs("/tmp/snapshots", exist_ok=True)

def human_format(num, pos=None):
    """Форматирует большие числа в читаемый вид (K, M)"""
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    return '%.1f%s' % (num, ['', 'k', 'M', 'G', 'T', 'P'][magnitude])

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
        
        # Индикаторы
        df['SMA9'] = df['Volume'].rolling(window=9).mean().fillna(df['Volume'])
        diff = (df['High'] - df['Low']).replace(0, 1)
        df['Delta'] = (((df['Close'] - df['Low']) / diff) * df['Volume']) - (df['Volume'] / 2)
        df['CVD'] = df['Delta'].cumsum()
        df['CVD_O'] = df['CVD'].shift(1).fillna(df['CVD'])
        df['OI_O'] = df['Turnover'].shift(1).fillna(df['Turnover'])
        df['liq_u'] = np.where(df['Close'] < df['Open'], df['Volume'] * 0.1, 0)
        df['liq_d'] = np.where(df['Close'] > df['Open'], -df['Volume'] * 0.08, 0)
        
        return df.fillna(0)
    except Exception as e:
        print(f"Data Error: {e}"); return pd.DataFrame()

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
    # Панель 1: Volume
    ap.append(mpf.make_addplot(df['Volume'], panel=1, type='bar', color='#02c076', alpha=0.3))
    ap.append(mpf.make_addplot(df['SMA9'], panel=1, color='#00d2ff', width=0.8))
    
    ratios = [4, 1.2]
    cur_p = 2
    headers = [(1, "Volume SMA 9")]

    if settings.get('show_delta', 1):
        c_df = df[['CVD_O', 'High', 'Low', 'CVD']].copy(); c_df.columns = ['Open', 'High', 'Low', 'Close']
        ap.append(mpf.make_addplot(c_df, panel=cur_p, type='candle'))
        ratios.append(1.2); headers.append((cur_p, "<CoinGlass> Cumulative Volume Delta (CVD)")); cur_p += 1
    
    if settings.get('show_oi', 1):
        o_df = df[['OI_O', 'High', 'Low', 'Turnover']].copy(); o_df.columns = ['Open', 'High', 'Low', 'Close']
        ap.append(mpf.make_addplot(o_df, panel=cur_p, type='candle'))
        ratios.append(1.2); headers.append((cur_p, "<CoinGlass> Open Interest (OI)")); cur_p += 1
        
    if settings.get('show_liq', 1):
        ap.append(mpf.make_addplot(df['liq_u'], panel=cur_p, type='bar', color='#02c076', width=0.6))
        ap.append(mpf.make_addplot(df['liq_down'] if 'liq_down' in df else df['liq_d'], panel=cur_p, type='bar', color='#f84960', width=0.6))
        ratios.append(1.2); headers.append((cur_p, "<CoinGlass> Aggregate Liquidations")); cur_p += 1

    # ПАНЕЛЬ 5: HEATMAP (Имитация)
    heatmap_data = df['Volume'].rolling(5).sum().fillna(0)
    ap.append(mpf.make_addplot(heatmap_data, panel=cur_p, type='line', color='#f0b90b', width=0.5, alpha=0.5))
    ratios.append(1.5); headers.append((cur_p, "<CoinGlass> Liquidation Heatmap (Live)")); cur_p += 1

    fig, axlist = mpf.plot(df[['Open', 'High', 'Low', 'Close']], type='candle', style=s, volume=False, addplot=ap, figsize=(14, 18),
                           returnfig=True, panel_ratios=tuple(ratios), datetime_format='%H:%M', tight_layout=False)

    plt.subplots_adjust(left=0.05, right=0.82, top=0.94, bottom=0.05, hspace=0.35)

    # Форматирование ВСЕХ шкал (убираем 1e7)
    for i in range(0, len(axlist), 2):
        ax = axlist[i]
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")
        # Для главной панели оставляем цену, для остальных - сокращения K/M
        if i == 0:
            ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%g'))
        else:
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(human_format))
        ax.tick_params(axis='y', colors='white', labelsize=9)

    ax_main = axlist[0]
    
    # Золотая линия
    if res_p > 0:
        ax_main.axhline(y=res_p, color='#f0b90b', linewidth=2, alpha=0.8)
        ax_main.text(0.5, res_p, f" {label_usd} F {res_p:g} ", color='black', fontweight='bold', 
                     ha='center', va='center', bbox=dict(boxstyle="round,pad=0.2", facecolor='#f0b90b', ec='none'))

    # Цена
    curr_v = df['Close'].iloc[-1]
    ax_main.axhline(y=curr_v, color='#02c076', linestyle='--', linewidth=1, alpha=0.5)
    ax_main.text(1.02, curr_v, f" {curr_v:g} ", transform=ax_main.get_yaxis_transform(),
                 color='black', fontweight='bold', fontsize=11, ha='left', va='center',
                 bbox=dict(boxstyle='round,pad=0.3', fc='#02c076', ec='none'))

    # ШАПКА
    title_str = f"{symbol}   {pumpdump_info['change_percent']:+.2f}%" if pumpdump_info else symbol
    ax_main.text(0, 1.05, title_str, transform=ax_main.transAxes, fontsize=22, fontweight='bold', color='white')
    ax_main.text(1, 1.05, f"TF: {settings.get('timeframe', '5')}m", transform=ax_main.transAxes, fontsize=14, color='#707a8a', ha='right')

    # Подписи
    for p_idx, text in headers:
        axlist[p_idx*2].text(0.01, 0.85, text, transform=axlist[p_idx*2].transAxes, color='#707a8a', fontsize=8)

    # Отрисовка имитации Heatmap на последней панели
    ax_heat = axlist[(cur_p-1)*2]
    ax_heat.fill_between(range(len(df)), df['Volume'], color='#f0b90b', alpha=0.1)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = f"/tmp/snapshots/{symbol}_{ts}.png"
    fig.savefig(path, dpi=110, facecolor=bg_color)
    plt.close(fig)
    return path
