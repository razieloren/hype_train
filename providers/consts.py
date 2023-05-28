from enum import Enum


class Asset(Enum):
    Bitcoin = 'BTC'


class OrderSide(Enum):
    SideBuy = 'BUY'
    SideSell = 'SELL'


BINANCE_COMMISSION = 0.001
