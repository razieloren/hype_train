import datetime

from enum import Enum
from config import Config
from logging import Logger
from typing import NamedTuple
from providers.provider import Provider
from utils.metrics import MetricsManager
from position import Position, PositionResult, PositionResults


class InsufficientFundsException(Exception):
    pass


class WalletResult(NamedTuple):
    pnl_ratio: float
    pnl_absolute: float


class Wallet:
    class Action(Enum):
        ActionBuy = 'BUY'
        ActionSell = 'SELL'
        ActionInitial = 'INITIAL'

    def __init__(self, config: Config, logger: Logger, provider: Provider, metrics_manager: MetricsManager):
        self._config = config
        self._provider = provider
        self._logger = logger.getChild('wallet')
        self._metrics = metrics_manager.init_csv_metrics('wallet.csv', 'Timestamp', 'AfterAction', 'Savings',
                                                         'Capital')
        self._profit_metrics = metrics_manager.init_csv_metrics('profits.csv', 'Timestamp', 'Origin', 'Target',
                                                                'TargetProfit')
        self._dividend_metrics = metrics_manager.init_csv_metrics('dividends.csv', 'Timestamp', 'Dividend')

        self._position_results = PositionResults()
        self._initial_balance = self._provider.get_account_balance().amount
        self._capital = self._initial_balance * self._config.trade.treasury_ratio
        self._savings = self._initial_balance - self._capital
        self._log_wallet_metric(self.Action.ActionInitial)
        self._logger.info(f'Wallet initialized, protected balance: {self._savings}{self._provider.asset}, '
                          f'treasury: {self._capital}{self._provider.asset}')

    def _log_wallet_metric(self, action: Action):
        self._metrics.record_metric(datetime.datetime.utcnow().isoformat(),
                                    action.value, self._savings, self._capital)

    def _log_profit_metric(self, origin: str, profit: float):
        self._profit_metrics.record_metric(
            datetime.datetime.utcnow().isoformat(), origin, self._provider.asset, '{0:.10f}'.format(profit))

    def _log_dividend_metric(self, dividend: float):
        fmt_div = '{0:.10f}'.format(dividend)
        self._logger.debug(f'Profitable sell, Protecting {fmt_div}{self._provider.asset}')
        self._dividend_metrics.record_metric(
            datetime.datetime.utcnow().isoformat(), fmt_div)

    def pnl(self) -> WalletResult:
        pnl_abs = self._position_results.total_pnl_absolute()
        return WalletResult(
            pnl_abs / self._initial_balance,
            pnl_abs
        )

    def record_sell(self, result: PositionResult):
        """
        Updates wallet status according to a position result.
        If the position was profitable, a dividend will be taken to the savings.
        :param result: The result of the position we'd like to update the wallet with.
        """
        dividend = 0
        self._position_results.add_result(result)
        self._log_profit_metric(result.origin, result.pnl.absolute)
        if result.pnl.ratio > 1:
            dividend = result.pnl.absolute * self._config.trade.dividend_from_profit
        if dividend > 0:
            self._log_dividend_metric(dividend)
        new_balance = self._provider.get_account_balance(self._capital + self._savings + result.sell_order.outcome).amount
        self._savings += dividend
        self._capital = new_balance - self._savings
        self._log_wallet_metric(self.Action.ActionSell)
        if self._capital <= 0:
            raise InsufficientFundsException('No more funds available to trade with')

    def record_acquisition(self, position: Position):
        self._capital -= position.buy_order.price
        self._log_wallet_metric(self.Action.ActionBuy)

    def budget_for_acquisition(self, active_positions: int = 0) -> float:
        """
        Given amount of opened positions, return the available budget for a position to buy.
        :param active_positions: Number of currently opened positions.
        :return: Budget for next position.
        """
        if active_positions >= self._config.trade.max_coins_to_trade:
            raise AttributeError('Too many open positions, cannot allocate budget')
        budget = self._capital / (self._config.trade.max_coins_to_trade - active_positions)
        budget = max(budget, self._config.trade.minimum_buy_price)
        if budget > self._capital:
            raise InsufficientFundsException(f'Allocate budget: {budget} > {self._capital}')
        return budget

    def close(self):
        self._metrics.close()
