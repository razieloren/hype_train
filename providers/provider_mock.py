import os
import csv
import datetime

from typing import Generator, Any, Dict, Union, List

from .provider import Provider
from .consts import Asset, OrderSide, BINANCE_COMMISSION
from .models import AccountBalance, Ticker, ExchangeParams, Order, ConversionRequest


class ProviderMock(Provider):
    """
    ProviderMock uses historic data to simulate potential outcomes, relevant for back-testing new strategies.
    """
    def __init__(self, origin_asset: Asset, reference_folder: str):
        super().__init__(origin_asset)
        self._files: List[Any] = []
        self._tickers: Dict[str, Any] = {}
        self._reference_folder = os.path.realpath(reference_folder)
        for asset_file_name in os.listdir(self._reference_folder):
            asset = asset_file_name.split('.')[0]
            full_path = os.path.join(self._reference_folder, asset_file_name)
            fd = open(full_path, 'r')
            self._files.append(fd)
            csv_file = csv.reader(fd)
            next(csv_file)
            self._tickers[asset] = csv_file

    def get_account_balance(self, override_balance: Union[float, None] = None,
                            asset: Union[str, None] = None) -> AccountBalance:
        if override_balance is not None:
            return AccountBalance(override_balance)
        if asset is not None:
            # No leftovers for specific asset
            return AccountBalance(0)
        return AccountBalance(1)

    def get_tickers(self) -> Generator[Ticker, Any, Any]:
        # Server time is in milliseconds.
        for asset, csv_file in self._tickers.items():
            vals = next(csv_file)
            if len(vals) == 4:
                server_time_iso, asset_to_origin, origin_to_asset, volume = vals
            else:
                server_time_iso, asset_to_origin, origin_to_asset = vals
                volume = 1
            yield Ticker(
                asset, str(self._origin_asset.value), float(origin_to_asset), float(asset_to_origin),
                datetime.datetime.fromisoformat(server_time_iso), ExchangeParams(
                    0.001,
                    999999999,
                    0.001,
                    0.0001
                ))

    def buy_order(self, request: ConversionRequest, simulation: bool = False) -> Order:
        return Provider.simulated_market_order(
            request, OrderSide.SideBuy, BINANCE_COMMISSION)

    def sell_order(self, request: ConversionRequest, simulation: bool = False) -> Order:
        return Provider.simulated_market_order(
            request, OrderSide.SideSell, BINANCE_COMMISSION)

    def close(self):
        for fd in self._files:
            fd.close()
