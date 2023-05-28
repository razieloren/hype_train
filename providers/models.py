import datetime

from typing import NamedTuple, List
from binance.helpers import round_step_size

from .consts import OrderSide


class AccountBalance(NamedTuple):
    amount: float


class ExchangeParams(NamedTuple):
    min_qty: float
    max_qty: float
    qty_step_size: float
    min_price: float

    def adjusted_lots(self, lots: float) -> float:
        rounded_lots = round_step_size(lots, self.qty_step_size)
        if rounded_lots < self.min_qty:
            raise AttributeError(f'Lots amount too low, original={lots}, adjusted={rounded_lots}')
        return min(self.max_qty, rounded_lots)


class ConversionRequest(NamedTuple):
    asset: str
    origin: str
    asset_lots: float
    side: OrderSide
    expected_price: float


class Ticker(NamedTuple):
    # COIN
    asset: str
    # ORIGIN, most of the time: BTC
    origin: str
    # How much ORIGIN we need in order to buy 1 ASSET
    conversion_origin_asset: float
    # How much ASSET we need in order to buy 1 ORIGIN
    conversion_asset_origin: float
    server_time: datetime.datetime
    exchange_params: ExchangeParams

    def __str__(self):
        iso_time = self.server_time.isoformat()
        return f'[Ticker | {iso_time}] 1{self.asset} = {self.fmt_asset_to_origin()}{self.origin}'

    def fmt_origin_to_asset(self):
        return '{0:.8f}'.format(self.conversion_origin_asset)

    def fmt_asset_to_origin(self):
        return '{0:.8f}'.format(self.conversion_asset_origin)

    def lots_to_buy(self, max_origin_amount: float) -> ConversionRequest:
        """
        :param max_origin_amount: Max ORIGIN to buy COIN with.
        :return: Lots (Quantity) of target coin that we are able to buy.
        """
        lots = max_origin_amount * self.conversion_origin_asset
        lots = self.exchange_params.adjusted_lots(lots)
        price = lots / self.conversion_origin_asset
        if price < self.exchange_params.min_price:
            raise AttributeError(f'Buy order expected price is too low: {price}{self.origin}, '
                                 f'origin lots to buy with: {lots}{self.asset}')
        return ConversionRequest(self.asset, self.origin, lots, OrderSide.SideBuy, self.conversion_asset_origin)

    def lots_to_sell(self, max_asset_amount: float) -> ConversionRequest:
        """
        :param max_asset_amount: Max COIN to sell for ORIGIN.
        :return: Lots (Quantity) of COIN we are able to sale for ORIGIN.
        """
        lots = self.exchange_params.adjusted_lots(max_asset_amount)
        price = lots * self.conversion_asset_origin
        if price < self.exchange_params.min_price:
            raise AttributeError(f'Sell order expected price is too low: {price}{self.origin}, '
                                 f'origin lots to get: {lots}{self.asset}')
        return ConversionRequest(
            self.asset, self.origin, lots, OrderSide.SideSell, self.conversion_asset_origin)


class OrderFill(NamedTuple):
    trade_id: int
    price: float
    quantity: float
    commission: float

    @property
    def total_price(self) -> float:
        # BUY - Amount of ORIGIN this costs, SELL - Amount of ORIGIN we got.
        return self.price * self.quantity

    @property
    def buy_outcome(self) -> float:
        # We got ASSET, so commission is in ASSET.
        return self.quantity - self.commission

    @property
    def sell_outcome(self) -> float:
        # We got ORIGIN, so commission is in ORIGIN.
        return self.total_price - self.commission


class OrderPnL(NamedTuple):
    ratio: float
    absolute: float


class Order(NamedTuple):
    asset: str
    origin: str
    side: OrderSide
    order_id: int
    client_order_id: str
    work_time: datetime.datetime
    transaction_time: datetime.datetime
    fills: List[OrderFill]

    def __str__(self):
        # BUY: Bought OUTCOME ASSET for PRICE ORIGIN.
        # SELL: Sold QUANTITY ASSET for OUTCOME ORIGIN.
        iso_time = self.transaction_time.isoformat()
        if self.side == OrderSide.SideSell:
            return f'[Trade | {iso_time}] Sold {self.quantity}{self.asset} for {self.outcome}{self.origin}'
        return f'[Trade | {iso_time}] Bought {self.outcome}{self.asset} for {self.price}{self.origin}'

    @property
    def outcome(self) -> float:
        # BUY - Amount of ASSET we got. SELL - Amount of ORIGIN we got.
        outcome = 0
        if self.side == OrderSide.SideSell:
            for fill in self.fills:
                outcome += fill.sell_outcome
        else:
            for fill in self.fills:
                outcome += fill.buy_outcome
        return outcome

    @property
    def price(self) -> float:
        price = 0
        for fill in self.fills:
            price += fill.total_price
        return price

    @property
    def quantity(self) -> float:
        quantity = 0
        for fill in self.fills:
            quantity += fill.quantity
        return quantity

    def pnl(self, buy_order) -> OrderPnL:
        if not isinstance(buy_order, Order) or buy_order.side == OrderSide.SideSell:
            raise RuntimeError('Can only calculate PnL for BUY Order')
        if self.side == OrderSide.SideBuy:
            raise RuntimeError('This must be a SELL order')
        # What we got in ORIGIN divided by what we paid in ORIGIN.
        return OrderPnL(self.outcome / buy_order.price, self.outcome - buy_order.price)

    def price_mismatch(self, expected_price) -> float:
        prices = [fill.price for fill in self.fills]
        # Expected price divided by the average of real prices.
        return expected_price / (sum(prices) / len(prices))
