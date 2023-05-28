import os
import json
import logging
import datetime

from providers.models import Ticker
from providers.provider import Provider

from enum import Enum
from config import Config
from collections import deque
from utils.metrics import MetricsManager
from typing import Deque, Union, Dict, Any
from position import Position, PositionResult


class PositionAlreadyOpenedException(Exception):
    pass


class PositionNotOpenedException(Exception):
    pass


class Asset:
    class AssetAction(Enum):
        Ticker = 'TICKER'
        OpenPosition = 'OPEN'
        LiquidatePosition = 'LIQUIDATE'

    def __init__(self, config: Config, logger: logging.Logger, metrics_manager: MetricsManager, asset: str):
        self._asset = asset
        self._config = config
        self._logger = logger.getChild(asset)
        self._ticker_history: Deque[Ticker] = deque(maxlen=self._config.trade.ignites_to_trigger + 2)
        self._metrics = metrics_manager.init_csv_metrics(
            os.path.join('assets', self._asset + '.csv'), 'Timestamp', 'Action', 'Extra')
        self._position: Union[None, Position] = None

    @property
    def has_open_position(self) -> bool:
        return self._position is not None

    @property
    def invested(self) -> float:
        if self.has_open_position:
            return self._position.buy_order.price
        return 0

    def _log_metric(self, action: AssetAction, extra: Union[Dict[str, Any], None] = None):
        if extra is None:
            extra = {}
        self._metrics.record_metric(datetime.datetime.utcnow().isoformat(), str(action.value), json.dumps(extra))

    def log_ticker(self, ticker: Ticker):
        self._ticker_history.append(ticker)

    def _was_ignited(self) -> bool:
        if len(self._ticker_history) < self._config.trade.ignites_to_trigger + 1:
            return False
        for i in range(self._config.trade.ignites_to_trigger):
            if self._ticker_history[-1 - i].conversion_origin_asset < \
                    self._ticker_history[-2 - i].conversion_origin_asset:
                return False
        return self._ticker_history[-1].conversion_origin_asset / \
            self._ticker_history[-self._config.trade.ignites_to_trigger].conversion_origin_asset > 1

    def try_open_position(self, provider: Provider,
                          metrics_manager: MetricsManager, budget: float) -> Union[None, Position]:
        if self.has_open_position:
            raise PositionAlreadyOpenedException()
        if self._was_ignited():
            self._log_metric(self.AssetAction.OpenPosition, extra={
                "budget": '{0:.10f}'.format(budget)
            })
            self._position = Position(self._config, self._logger, provider,
                                      metrics_manager, self._ticker_history[-1], budget)
            return self._position
        return None

    def try_liquidate_position(self, force: bool) -> Union[None, PositionResult]:
        if not self.has_open_position:
            raise PositionNotOpenedException()
        result = self._position.try_liquidate(self._ticker_history[-1], force)
        if result is None:
            return None
        self._log_metric(self.AssetAction.LiquidatePosition)
        self._position.close()
        self._position = None
        return result

    def close(self):
        self._metrics.close()
