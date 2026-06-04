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
    return df.iloc[::-1]

def build_snapshot(symbol, klines, trades, settings: dict, pumpdump_info: dict = None) -> str:
    if not klines or len(klines) < 20:
        return ""

    df = klines_to_df(klines)
    
    # Расчет дельты
    df['delta'] = 0.0
    if trades:
        for t in trades:
            t_time = pd.to_datetime(float(t['time']), unit='ms')
            qty = float(t['size'])
            side = 1 if t['side'] == 'Buy' else -1
            idx = df.index.get_indexer([t_time], method='pad')[0]
            if idx != -1:
                df.iloc[idx, df.columns.get_loc('delta')] += (qty * side)

    # Золотая линия (сопротивление по объему)
    max_vol_idx = df['volume'].idxmax()
    resistance_price = df.loc[max_vol_idx, 'high']
    max_vol_usd = (df['volume'].max() * resistance_price) / 1000 

    # --- СТИЛЬ ---
    colors = mpf.make_marketcolors(up='#00ff41', down='#ff3131', inherit=True, volume='in', edge='inherit')
    s = mpf.make_mpf_style(
        base_mpf_style='charles', 
        marketcolors=colors, 
        facecolor='#0b0e11', 
        edgecolor='#444', 
        gridcolor='#222', 
        gridstyle='dotted', 
        rc={
            'font.size': 10, 
            'axes.labelcolor': 'white', 
            'xtick.color': '#888', 
            'ytick.color': '#888'
        }
    )

    # Панель дельты
    ap = [
        mpf.make_addplot(df['delta'], panel=2, type='bar', color=['#00ff41' if x > 0 else '#ff3131' for x in df['delta']], width=0.8)
    ]

    title_text = f"{symbol}  {pumpdump_info['change_percent'] if pumpdump_info else ''}%"
    
    # --- ОТРИСОВКА ---
    # Уменьшил отступы и упростил параметры, чтобы избежать ошибок размера
    fig, axlist = mpf.plot(
        df, type='candle', style=s,
        volume=True, addplot=ap,
        figsize=(12, 8), returnfig=True,
        panel_ratios=(4, 1, 1),
        datetime_format='%H:%M',
        xrotation=0,
        tight_layout=True # Возвращаем автоматическое выравнивание
    )

    ax_main = axlist[0]
    
    # Переносим шкалу направо (как на бирже)
    ax_main.yaxis.tick_right()
    ax_main.yaxis.set_label_position("right")
    
    # Золотая линия
    ax_main.axhline(y=resistance_price, color='#f0b90b', linestyle='-', linewidth=2, alpha=0.9)
    ax_main.text(0.5, resistance_price, f" {max_vol_usd:.0f}k$ F {resistance_price:.6f} ", 
                 color='black', fontsize=9, fontweight='bold', ha='center', va='center',
                 bbox=dict(boxstyle="round,pad=0.3", facecolor='#f0b90b', edgecolor='#f0b90b'))

    # Метка текущей цены
    current_price = df['close'].iloc[-1]
    ax_main.text(1.01, current_price, f"{current_price:.6f}", transform=ax_main.get_yaxis_transform(),
                 color='black', fontweight='bold', fontsize=10,
                 bbox=dict(boxstyle='round,pad=0.3', fc='#00ff41', ec='none'))

    # Инфо
    ax_main.text(0.02, 0.95, f"TF: {settings.get('timeframe', '5')}m", transform=ax_main.transAxes, color='gray')
    ax_main.set_title(title_text, color='white', loc='left', fontsize=14, fontweight='bold')

    # Сохранение с запасом под шкалу справа (через pad_inches)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = f"/tmp/snapshots/{symbol}_{ts}.png"
    fig.savefig(path, dpi=120, facecolor='#0b0e11', bbox_inches='tight', pad_inches=0.5)
    plt.close(fig)
    
    return path
