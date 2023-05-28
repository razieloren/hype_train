import random
import datetime

from typing import Generator, Any, Union

from .consts import Asset, OrderSide
from .models import AccountBalance, Ticker, ConversionRequest, Order, OrderFill


class Provider:
    def __init__(self, origin_asset: Asset):
        self._origin_asset = origin_asset

    @property
    def asset(self) -> str:
        return str(self._origin_asset.value)

    @staticmethod
    def simulated_market_order(request: ConversionRequest, side: OrderSide, commission: float):
        now = datetime.datetime.utcnow()
        commission = request.asset_lots * commission if side == OrderSide.SideBuy else \
            request.expected_price * commission
        fills = [OrderFill(0, request.expected_price, request.asset_lots, commission)]
        return Order(request.asset, request.origin, side, 0, '0', now, now, fills)

    def get_account_balance(self, override_balance: Union[float, None] = None,
                            asset: Union[str, None] = None) -> AccountBalance:
        raise NotImplementedError('get_account_balance')

    def get_tickers(self) -> Generator[Ticker, Any, Any]:
        raise NotImplementedError('get_tickers')

    def buy_order(self, request: ConversionRequest, simulation: bool = False) -> Order:
        raise NotImplementedError('buy_order')

    def sell_order(self, request: ConversionRequest, simulation: bool = False) -> Order:
        raise NotImplementedError('sell_order')

    def close(self):
        raise NotImplementedError('close')
