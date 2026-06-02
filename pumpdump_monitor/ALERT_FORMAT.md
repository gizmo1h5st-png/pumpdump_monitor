# 📱 Формат алерта в Telegram

## Внешний вид сообщения

### Текст (HTML)

```
🟢 PUMP BTCUSDT

📈 Изменение: +5.12%
💰 Цена: 71245.50
⏰ Время: 14:32:15 UTC

🎯 Score: 6/10
📊 FVG: 2 | OB: 3 | VOL: 3.2x
⚡ Таймфрейм: 5m
```

- `<code>BTCUSDT</code>` — пара в моноширинном шрифте, копируется одним тапом в Telegram
- Цена и время тоже в `<code>` для удобства копирования

### Кнопки под сообщением

| Кнопка | URL |
|---|---|
| 📊 **TradingView** | `https://www.tradingview.com/chart/?symbol=BYBIT%3ABTCUSDT.P` |
| ⚡ **Bybit** | `https://www.bybit.com/trade/usdt/BTCUSDT` |

### Скриншот (PNG)

На графике отображаются:
- Японские свечи (5м)
- **Жёлтая стрелка** с процентом изменения (`+5.12%`)
- **FVG зоны** (lime/magenta прямоугольники)
- **OB зоны** (green/red прямоугольники)
- **Зона интереса** ±2% (серая подложка)
- **Левый верхний блок** — все переменные: `SCORE`, `DIR`, `CHG`, `FVG`, `OB`, `VOL`, `ATR`, `ZONE`
- **Правый верхний блок** — покупка/продажа лотов
- **Крупные лоты** — разметка прямо на свечах (`+142.5`, `-34.1`)

---

## Пример внешнего вида

```
┌─────────────────────────────────────┐
│  🟢 PUMP BTCUSDT                    │
│                                     │
│  📈 Изменение: +5.12%               │
│  💰 Цена: 71245.50                   │
│  ⏰ Время: 14:32:15 UTC             │
│                                     │
│  🎯 Score: 6/10                      │
│  📊 FVG: 2 | OB: 3 | VOL: 3.2x      │
│  ⚡ Таймфрейм: 5m                   │
│                                     │
│  [📊 TradingView]  [⚡ Bybit]      │
└─────────────────────────────────────┘
```

---

## Техническая реализация

### HTML-теги в caption

```python
parse_mode="HTML"

caption = (
    f"🟢 <b>{{direction}}</b> <code>{{sym}}</code>\n\n"
    f"📈 Изменение: <b>{{change:+.2f}}%</b>\n"
    f"💰 Цена: <code>{{price:,.2f}}</code>\n"
    ...
)
```

### InlineKeyboardMarkup

```python
keyboard = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📊 TradingView", url=f"https://www.tradingview.com/chart/?symbol=BYBIT%3A{{sym}}.P"),
        InlineKeyboardButton("⚡ Bybit", url=f"https://www.bybit.com/trade/usdt/{{sym}}")
    ]
])
```

### График — variables overlay

В `chart_builder.py` добавлен текстовый блок на самом графике:

```
SCORE: 6/10
DIR:   PUMP
CHG:   +5.12%
FVG:   2 zones
OB:    3 blocks
VOL:   3.2x SMA
ATR:   120.50
ZONE:  ±2.0%
```

Это позволяет видеть все переменные даже без чтения текста алерта.
