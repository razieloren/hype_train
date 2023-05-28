import os
import json
import logging
import datetime

from enum import Enum
from config import Config
from providers.provider import Provider
from utils.metrics import MetricsManager
from providers.models import Ticker, Order, ConversionRequest
from typing import NamedTuple, Union, Dict, Any, Callable, List


class LiquidationReason(Enum):
    Forced = 'FORCED'
    StopLoss = 'STOP_LOSS'
    TakeProfit = 'STOP_PROFIT'


class PositionResult(NamedTuple):
    origin: str
    buy_order: Order
    sell_order: Order
    liquidation_reason: LiquidationReason

    @property
    def pnl(self):
        return self.sell_order.pnl(self.buy_order)


class PositionResults:
    def __init__(self):
        self._results: List[PositionResult] = []

    @property
    def length(self):
        return len(self._results)

    def add_result(self, result: PositionResult):
        self._results.append(result)

    def total_pnl_absolute(self):
        total = 0
        for result in self._results:
            total += result.pnl.absolute
        return total


class Position:
    _POSITION_ID = 0

    class PositionAction(Enum):
        ActionOpen = 'OPEN'
        ActionClose = 'CLOSE'

    def __init__(self, config: Config, logger: logging.Logger, provider: Provider, metrics_manager: MetricsManager,
                 ticker: Ticker, budget: float):
        self._held_for = 0
        self._config = config
        self._base_ticker = ticker
        self._provider = provider

        self._position_id = Position._POSITION_ID
        Position._POSITION_ID += 1
        position_file_name = f'{self._position_id}_{self._base_ticker.asset}'
        self._metrics = metrics_manager.init_csv_metrics(
            os.path.join('positions', position_file_name + ".csv"),
            'Timestamp', 'Action', 'Extra', 'Asset-Origin', 'Origin-Asset')
        self._logger = logger.getChild(f'pos_{self._position_id}')

        self._buy_order = self._send_order_request(self._base_ticker, self._base_ticker.lots_to_buy,
                                                   self._provider.buy_order, Position.PositionAction.ActionOpen, budget)
        # This is re-calculated since we might have some left-overs from previous trades.
        self._quantity_owned = \
            self._provider.get_account_balance(self._buy_order.outcome, self._base_ticker.asset).amount

    @property
    def buy_order(self):
        return self._buy_order

    def _log_metric(self, action: PositionAction, ticker: Ticker, extra: Union[Dict[str, Any], None] = None):
        if extra is None:
            extra = {}
        self._metrics.record_metric(datetime.datetime.utcnow().isoformat(), str(action.value), json.dumps(extra),
                                    ticker.fmt_asset_to_origin(), ticker.fmt_origin_to_asset())

    def _send_order_request(self, ticker: Ticker, lots_fn: Callable[[float], ConversionRequest],
                            order_fn: Callable[[ConversionRequest], Order], action: PositionAction,
                            budget: float, extra: Union[Dict[str, Any], None] = None) -> Order:
        request = lots_fn(budget)
        order = order_fn(request)
        self._logger.info(order)
        metadata = {
            'order_price': order.price,
            'order_quantity': order.quantity,
            'order_outcome': order.outcome,
            'price_mismatch': order.price_mismatch(request.expected_price)
        }
        if extra is not None:
            metadata['extra'] = extra
        self._log_metric(action, ticker, metadata)
        return order

    def _potential_pnl_ratio(self, ticker: Ticker) -> float:
        sell_order = self._provider.sell_order(ticker.lots_to_sell(self._quantity_owned), simulation=True)
        return sell_order.pnl(self._buy_order).ratio

    def _liquidate(self, ticker: Ticker, liquidation_reason: LiquidationReason) -> Union[PositionResult, None]:
        sell_order = self._send_order_request(ticker, ticker.lots_to_sell, self._provider.sell_order,
                                              Position.PositionAction.ActionClose, self._quantity_owned,
                                              {'reason': liquidation_reason.value, 'held_for': self._held_for})
        return PositionResult(ticker.asset, self._buy_order, sell_order, liquidation_reason)

    def try_liquidate(self, ticker: Ticker, force: bool) -> Union[PositionResult, None]:
        self._held_for += 1
        profit_ratio = self._potential_pnl_ratio(ticker)
        self._logger.debug(f'Profit ratio: {round((profit_ratio - 1) * 100, 7)}% (Held for: {self._held_for})')
        if profit_ratio < self._config.trade.stop_loss:
            return self._liquidate(ticker, LiquidationReason.StopLoss)
        if profit_ratio >= self._config.trade.take_profit:
            return self._liquidate(ticker, LiquidationReason.TakeProfit)
        if force:
            return self._liquidate(ticker, LiquidationReason.Forced)
        return None

    def close(self):
        self._metrics.close()
