import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mplfinance as mpf
from datetime import datetime

os.makedirs("/tmp/snapshots", exist_ok=True)

def klines_to_df(klines):
    # Bybit kline: [time, open, high, low, close, volume, turnover]
    df = pd.DataFrame(klines, columns=["t","open","high","low","close","volume","turnover"])
    df = df.astype(float)
    df["date"] = pd.to_datetime(df["t"], unit="ms")
    df.set_index("date", inplace=True)
    return df.iloc[::-1]

def build_snapshot(symbol, klines, trades, settings: dict, pumpdump_info: dict = None) -> str:
    if not klines or len(klines) < 20:
        return ""

    df = klines_to_df(klines)
    
    # Расчет дельты объема
    df['delta'] = 0.0
    if trades:
        for t in trades:
            t_time = pd.to_datetime(float(t['time']), unit='ms')
            qty = float(t['size'])
            side = 1 if t['side'] == 'Buy' else -1
            idx = df.index.get_indexer([t_time], method='pad')[0]
            if idx != -1:
                df.iloc[idx, df.columns.get_loc('delta')] += (qty * side)

    # Поиск самого ликвидного уровня (золотая линия)
    max_vol_idx = df['volume'].idxmax()
    resistance_price = df.loc[max_vol_idx, 'high']
    max_vol_usd = (df['volume'].max() * resistance_price) / 1000 

    # --- НАСТРОЙКА СТИЛЯ ---
    colors = mpf.make_marketcolors(up='#00ff41', down='#ff3131', inherit=True, volume='in', edge='inherit')
    
    # Увеличиваем шрифты и настраиваем видимость шкалы
    s = mpf.make_mpf_style(
        base_mpf_style='charles', 
        marketcolors=colors, 
        facecolor='#0b0e11', 
        edgecolor='#444', 
        gridcolor='#222', 
        gridstyle='dotted', 
        rc={
            'font.size': 9, 
            'axes.labelcolor': 'white', 
            'xtick.color': '#888', 
            'ytick.color': '#00ff41', # Цена будет ярко-зеленой для контраста
            'axes.edgecolor': '#444'
        }
    )

    # Доп. график дельты
    delta_plot = mpf.make_addplot(df['delta'], panel=2, type='bar', color=['#00ff41' if x > 0 else '#ff3131' for x in df['delta']], width=0.8)

    title_text = f"{symbol}  {pumpdump_info['change_percent'] if pumpdump_info else ''}%"
    
    # --- ОТРИСОВКА ---
    # Добавляем параметр scale_padding для предотвращения обрезки шкалы
    fig, axlist = mpf.plot(
        df, type='candle', style=s,
        volume=True, addplot=[delta_plot],
        figsize=(12, 7), returnfig=True,
        panel_ratios=(4, 1.2, 1.2),
        datetime_format='%H:%M',
        xrotation=0,
        tight_layout=False, # Отключаем, чтобы контролировать поля вручную
        scale_padding={'left': 1, 'top': 5, 'right': 10, 'bottom': 1},
        show_nontrading=False
    )

    ax_main = axlist[0]
    
    # Настройка правой шкалы цен
    ax_main.yaxis.tick_right()
    ax_main.yaxis.set_label_position("right")
    
    # Золотая линия
    ax_main.axhline(y=resistance_price, color='#f0b90b', linestyle='-', linewidth=2, alpha=0.9)
    ax_main.text(0.5, resistance_price, f" {max_vol_usd:.0f}k$ F {resistance_price:.6f} ", 
                 color='black', fontsize=9, fontweight='bold', ha='center', va='center',
                 bbox=dict(boxstyle="round,pad=0.3", facecolor='#f0b90b', edgecolor='#f0b90b'))

    # Метка текущей цены на шкале
    current_price = df['close'].iloc[-1]
    ax_main.annotate(f"{current_price:.6f}", xy=(1, current_price), xycoords=('axes fraction', 'data'),
                     xytext=(10, 0), textcoords='offset points', color='black', fontweight='bold',
                     bbox=dict(boxstyle='round,pad=0.3', fc='#00ff41', ec='none'))

    # Названия
    ax_main.text(0.02, 0.95, f"TF: {settings.get('timeframe', '5')}m", transform=ax_main.transAxes, color='gray', fontsize=10)
    ax_main.set_title(title_text, color='white', loc='left', fontsize=14, fontweight='bold', pad=15)

    # Ручная настройка полей, чтобы шкала справа не обрезалась
    plt.subplots_adjust(right=0.88, left=0.05, top=0.9, bottom=0.1)

    # Сохранение с высоким DPI и сохранением пропорций
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = f"/tmp/snapshots/{symbol}_{ts}.png"
    fig.savefig(path, dpi=140, facecolor='#0b0e11', bbox_inches=None)
    plt.close(fig)
    
    return path
