import json
import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class Config:
    class System:
        verbose_logs: bool = False
        file_logging: bool = False
        save_metrics: bool = False
        sessions_directory: str = ''

    class Binance:
        api_key: str = ''
        api_key_salt: str = ''
        secret_key: str = ''
        secret_key_salt: str = ''

    class Trade:
        ignites_to_trigger: int = 0
        stop_loss: float = 0
        take_profit: float = 0
        update_interval_sec: float = 0
        max_coins_to_trade: int = 0
        treasury_ratio: float = 0
        minimum_buy_price: float = 0
        dividend_from_profit: float = 0

        def __str__(self):
            return f'[TradeConfig] ignites_to_trigger={self.ignites_to_trigger}, stop_loss={self.stop_loss}, ' \
                   f'take_profit={self.take_profit}'

    def __init__(self, config_path: str):
        self.config_path = config_path
        with open(self.config_path, "r") as f:
            self._config_dict = json.load(f)
        self.system: Config.System = self.System()
        self._populate_config_section(Config.System)

        self.binance: Config.Binance = self.Binance()
        self._populate_config_section(Config.Binance)

        self.trade: Config.Trade = self.Trade()
        self._populate_config_section(Config.Trade)

        self._validate()

    def _validate(self):
        assert self.trade.treasury_ratio < 1, 'Treasury ratio must be less than 1'

    def _populate_config_section(self, cls: type):
        conf_key = cls.__name__.lower()
        conf_items = self._config_dict[conf_key]
        obj = cls()
        for k, v in conf_items.items():
            obj.__setattr__(k, v)
        self.__setattr__(conf_key, obj)

    def get_api_key(self, password: str) -> str:
        salt = base64.urlsafe_b64decode(self.binance.api_key_salt)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        fernet = Fernet(key)
        return fernet.decrypt(self.binance.api_key.encode()).decode()

    def get_secret_key(self, password: str) -> str:
        salt = base64.urlsafe_b64decode(self.binance.secret_key_salt)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        fernet = Fernet(key)
        return fernet.decrypt(self.binance.secret_key.encode()).decode()
