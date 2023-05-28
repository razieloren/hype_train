import datetime

from binance.client import Client
from typing import Generator, Any, Union, Dict, Callable, List

from .provider import Provider
from .consts import Asset, OrderSide, BINANCE_COMMISSION
from .models import AccountBalance, Ticker, ExchangeParams, ConversionRequest, Order, OrderFill


def _market_order(request: ConversionRequest, order_fn: Callable, side: OrderSide):
    symbol = f'{request.asset}{request.origin}'
    order = order_fn(symbol=symbol, quantity=request.asset_lots)
    order_id = order['orderId']
    client_order_id = order['clientOrderId']
    work_time = datetime.datetime.fromtimestamp(order['workingTime'] / 1000)
    transaction_time = datetime.datetime.fromtimestamp(order['transactTime'] / 1000)

    api_fills = order['fills']
    fills: List[OrderFill] = []
    for fill in api_fills:
        commission = float(fill['commission'])
        # Sometimes, we got special offers for commissions, so we don't need to pay them from our resources :)
        if side == OrderSide.SideBuy and fill['commissionAsset'].lower() != request.asset.lower():
            commission = 0
        elif side == OrderSide.SideSell and fill['commissionAsset'].lower() != request.origin.lower():
            commission = 0
        fills.append(OrderFill(fill['tradeId'], float(fill['price']), float(fill['qty']), commission))
    return Order(request.asset, request.origin, side, order_id, client_order_id, work_time, transaction_time, fills)


class ProviderBinance(Provider):
    """
    ProviderBinance is used to trade real coins with Binance online exchange, using their public API.
    """
    def __init__(self, origin_asset: Asset, client: Client):
        super().__init__(origin_asset)
        self._client = client

    def get_account_balance(self, override_balance: Union[float, None] = None,
                            asset: Union[str, None] = None) -> AccountBalance:
        # override_balance is ignored in binance provider.
        if asset is not None:
            base_balance = self._client.get_asset_balance(asset=asset)
        else:
            base_balance = self._client.get_asset_balance(asset=str(self._origin_asset.value))
        return AccountBalance(float(base_balance['free']))

    def get_tickers(self) -> Generator[Ticker, Any, Any]:
        # Server time is in milliseconds.
        server_time = datetime.datetime.fromtimestamp(self._client.get_server_time()['serverTime'] / 1000)
        tickers = self._client.get_ticker()
        exchange_symbols = self._client.get_exchange_info()['symbols']
        for ticker in tickers:
            symbol = ticker['symbol']
            if not symbol.endswith(self._origin_asset.value):
                continue
            exchange_dict: Union[Dict[str, Any], None] = None
            for exchange_symbol in exchange_symbols:
                if exchange_symbol['symbol'] == symbol:
                    exchange_dict = exchange_symbol
                    break
            if exchange_dict is None:
                # No exchange data for this symbol.
                continue

            def get_filter_param(param_name: str, order: Callable, *filter_types: str) -> Union[float, None]:
                values = []
                for f in exchange_dict['filters']:
                    if f['filterType'] in filter_types:
                        values.append(float(f[param_name]))
                if len(values) == 0:
                    raise AttributeError(f'No {param_name} in any of the filters of the exchange')
                return order(values)

            asset = symbol[:-len(self._origin_asset.value)]
            volume = float(ticker['volume'])
            asset_to_origin = float(ticker['lastPrice'])
            if asset_to_origin == 0:
                continue
            origin_to_asset = 1 / asset_to_origin if asset_to_origin > 0 else 0

            yield Ticker(asset, str(self._origin_asset.value), origin_to_asset, asset_to_origin, server_time,
                         ExchangeParams(
                             get_filter_param('minQty', max, 'LOT_SIZE', 'MARKET_LOT_SIZE'),
                             get_filter_param('maxQty', min, 'LOT_SIZE', 'MARKET_LOT_SIZE'),
                             get_filter_param('stepSize', max, 'LOT_SIZE', 'MARKET_LOT_SIZE'),
                             get_filter_param('minNotional', max, 'MIN_NOTIONAL')
                         ))

    def buy_order(self, request: ConversionRequest, simulation: bool = False) -> Order:
        if simulation:
            return Provider.simulated_market_order(request, OrderSide.SideBuy, BINANCE_COMMISSION)
        return _market_order(request, self._client.order_market_buy, OrderSide.SideBuy)

    def sell_order(self, request: ConversionRequest, simulation: bool = False) -> Order:
        if simulation:
            return Provider.simulated_market_order(request, OrderSide.SideSell, BINANCE_COMMISSION)
        return _market_order(request, self._client.order_market_sell, OrderSide.SideSell)

    def close(self):
        pass
