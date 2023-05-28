import time
import datetime
import requests
import threading

from utils.metrics import MetricsManager
from utils.graceful_killer import install_graceful_killer

from config import Config
from logging import Logger
from typing import Dict, NamedTuple
from providers.provider import Provider
from binance.exceptions import BinanceAPIException
from wallet import Wallet, InsufficientFundsException
from asset import Asset, PositionNotOpenedException, PositionAlreadyOpenedException


class TradeResult(NamedTuple):
    pnl_ratio: float
    pnl_absolute: float

    def __str__(self):
        profit = round(self.pnl_absolute, 6)
        ratio = round(self.pnl_ratio * 100, 6)
        return f'Trade generated {profit} ({ratio}%)'


class Account:
    _BANNED_ASSETS = ['W', 'BTS', 'AION', 'YFII', 'JUV', 'MIR', 'TORN', 'BNB']

    def __init__(self, config: Config, logger: Logger, provider: Provider, metrics_manager: MetricsManager):
        self._config = config
        self._provider = provider
        self._logger = logger.getChild('account')

        self._assets: Dict[str, Asset] = {}
        self._wallet = Wallet(self._config, self._logger, self._provider, metrics_manager)

        self._metrics_manager = metrics_manager
        self._metrics = self._metrics_manager.init_csv_metrics('account.csv', 'Timestamp', 'OpenPositions',
                                                               'PnLRatio', 'PnLAbs')

        self._trader_event = threading.Event()
        self._trader_thread = threading.Thread(target=self.trade)
        install_graceful_killer(self._killer_cb)

    def _killer_cb(self, *args, **kwargs):
        self._trader_event.set()

    def _log_metric(self):
        result = self.generate_trade_results()
        self._metrics.record_metric(datetime.datetime.utcnow().isoformat(), self._count_open_positions(),
                                    result.pnl_ratio, result.pnl_absolute)

    def _init_trader_thread(self):
        self._logger.debug('Initializing account trader thread...')
        self._trader_thread.start()
        self._logger.debug('Trader thread is up & running')

    def _join_trader_thread(self):
        self._logger.debug('Stopping account trader thread...')
        self._trader_event.set()
        self._trader_thread.join()
        self._logger.debug('Trader thread joined')

    def _count_open_positions(self):
        return len([asset for asset in self._assets.values() if asset.has_open_position])

    def _fetch_asset_tickers(self):
        self._logger.debug('Fetching asset tickers')
        for ticker in self._provider.get_tickers():
            if ticker.asset in self._BANNED_ASSETS:
                continue
            if ticker.asset not in self._assets:
                self._assets[ticker.asset] = Asset(
                    self._config, self._logger, self._metrics_manager, ticker.asset)
            self._assets[ticker.asset].log_ticker(ticker)

    def _try_close_positions(self, force: bool = False):
        self._logger.debug('Trying to close positions')
        for symbol, asset in self._assets.items():
            if not asset.has_open_position:
                continue
            try:
                result = asset.try_liquidate_position(force)
                if result is None:
                    continue
                self._logger.info(
                    f'Closed position "{symbol}" (Reason: {result.liquidation_reason.value}, '
                    f'Profit: {round((result.pnl.ratio - 1) * 100, 7)}%)')
                self._wallet.record_sell(result)
                self._log_metric()
            except PositionNotOpenedException:
                self._logger.warning(f'There is no open position for {symbol}')
            except (AttributeError, BinanceAPIException) as e:
                self._logger.warning(f'Cannot close position for {symbol}: {e}')

    def _try_open_new_positions(self):
        self._logger.debug('Trying to open new positions')
        for symbol, asset in self._assets.items():
            if self._count_open_positions() >= self._config.trade.max_coins_to_trade:
                return
            if asset.has_open_position:
                continue
            try:
                budget = self._wallet.budget_for_acquisition(self._count_open_positions())
                position = asset.try_open_position(self._provider, self._metrics_manager, budget)
                if position is None:
                    continue
                self._wallet.record_acquisition(position)
                self._logger.info(f'Opened position for {symbol}')
                self._log_metric()
            except PositionAlreadyOpenedException:
                self._logger.warning(f'Tried to open position for {symbol} although there is already one opened')
            except (AttributeError, BinanceAPIException) as e:
                self._logger.warning(f'Cannot open position for {symbol}: {e}')

    def trade(self):
        try:
            while True:
                try:
                    try:
                        self._fetch_asset_tickers()
                    except RuntimeError as e:
                        self._logger.warning(f'Cannot fetch asset tickers, terminating: {e}')
                        return
                    self._try_close_positions()
                    self._try_open_new_positions()
                except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
                    self._logger.warning('Request API timeout, ignoring this iteration')
                except InsufficientFundsException as e:
                    self._logger.warning(e)
                    break
                self._logger.info(
                    f'Trader finished iterating, sleeping for {self._config.trade.update_interval_sec} seconds...')
                if self._trader_event.wait(self._config.trade.update_interval_sec):
                    break
        except KeyboardInterrupt:
            self._logger.debug('Caught keyboard interrupt in trade loop')
        self._logger.info('Out of trader loop')
        try:
            while self._count_open_positions() > 0:
                self._logger.debug(
                    f'There are still opened positions, waiting for them to be closed...')
                try:
                    self._fetch_asset_tickers()
                except RuntimeError as e:
                    self._logger.warning(f'Cannot fetch asset tickers, terminating: {e}')
                    return
                self._try_close_positions()
                time.sleep(self._config.trade.update_interval_sec)
        except InsufficientFundsException:
            pass
        except KeyboardInterrupt:
            self._logger.info('Caught keyboard interrupt while trying to close left-over positions')
        self._logger.info('CLosing left-over positions now')
        self._fetch_asset_tickers()
        self._try_close_positions(True)
        self._logger.info('Trader done :)')

    def generate_trade_results(self) -> TradeResult:
        pnl = self._wallet.pnl()
        return TradeResult(pnl.pnl_ratio, pnl.pnl_absolute)

    def close(self):
        for asset in self._assets.values():
            asset.close()
        self._wallet.close()

    def trade_detached(self):
        self._init_trader_thread()
        try:
            while not self._trader_event.wait(1):
                pass
        except KeyboardInterrupt:
            pass
        self._join_trader_thread()
