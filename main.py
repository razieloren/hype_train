#!/usr/bin/env python3

import os
import time
import logging
import getpass
import argparse
import datetime

from utils.logger import setup_logging
from utils.metrics import MetricsManager

from providers.provider import Provider
from providers.provider_mock import ProviderMock
from providers.provider_binance import ProviderBinance

from enum import Enum
from config import Config
from account import Account
from itertools import product
from binance.client import Client
from providers.consts import Asset


class Mode(Enum):
    ModeMock = 'mock'
    ModeOperational = 'operational'
    AvailableMods = [ModeMock, ModeOperational]


def parse_args() -> argparse.Namespace:
    args = argparse.ArgumentParser(description='HypeTrain Console')
    args.add_argument('-m', '--mode', help='Mode to run the console', choices=Mode.AvailableMods.value, required=True)
    args.add_argument('-c', '--config', help='Path to HypeTrain configuration file.', default='config/config.json')
    args.add_argument('-r', '--reference',
                      help=f'Reference historic data directory, relevant for {Mode.ModeMock.value} mode', default=None)
    args.add_argument('-t', '--test-all-configs', help='In Mock mode, test all configs, not only the one provided',
                      default=False, action='store_true')
    args.add_argument('-p', '--password', help='Master password for all encrypted secrets', default=None)
    return args.parse_args()


def test_all_configs(config: Config, logger: logging.Logger, metrics_manager: MetricsManager, reference_folder: str):
    ignites_to_trigger = [4, 5]
    stop_loss = [0.9, 0.91]
    take_profit = [1.005, 1.007, 1.009]

    configs_tested = 0
    best_profit = -99999
    start_time = time.time()
    for params in product(ignites_to_trigger, stop_loss, take_profit):
        print(datetime.datetime.now().isoformat(), 'Testing:', params, end='', flush=True)
        config.trade.ignites_to_trigger = params[0]
        config.trade.stop_loss = params[1]
        config.trade.take_profit = params[2]

        provider = ProviderMock(Asset.Bitcoin, reference_folder)
        account = Account(config, logger, provider, metrics_manager)
        account.trade()
        account.close()
        result = account.generate_trade_results()
        provider.close()
        profit = result.pnl_absolute
        print(f' -> {profit}')
        if profit > best_profit:
            best_profit = profit
            fmt_str = f'New best config found [{result}] {config.trade}'
            print(fmt_str)
        configs_tested += 1
        if configs_tested % 10 == 0:
            print(f'Tested {configs_tested} so far, average time per config: '
                  f'{((time.time() - start_time) / configs_tested)} sec')
    total_time = time.time() - start_time
    print(f'Finished {configs_tested} configs in {total_time} sec (avg: {total_time / configs_tested} sec)')


def create_provider(args: argparse.Namespace, config: Config) -> Provider:
    if args.mode == Mode.ModeMock.value:
        return ProviderMock(Asset.Bitcoin, args.reference)
    password = args.password
    if password is None:
        password = getpass.getpass('Secrets Password: ')
    api_key = config.get_api_key(password)
    secret_key = config.get_secret_key(password)
    if args.mode == Mode.ModeOperational.value:
        return ProviderBinance(Asset.Bitcoin, Client(api_key, secret_key))
    raise RuntimeError(f'Invalid mode: "{args.mode}"')


def main():
    args = parse_args()
    assert args.mode in Mode.AvailableMods.value, f'Invalid mode: {args.mode}'
    assert args.mode != Mode.ModeMock.value or args.reference is not None, 'Reference must be set for running a mock'

    config = Config(args.config)

    # Setup environment directories.
    session_dir = os.path.realpath(os.path.join(config.system.sessions_directory,
                                                datetime.datetime.utcnow().strftime(f"%Y%m%d_%H%M%S_%f_{args.mode}")))
    logs_dir = os.path.join(session_dir, 'logs')
    metrics_dir = os.path.join(session_dir, 'metrics')
    metrics_manager = MetricsManager(metrics_dir, not config.system.save_metrics)
    logger = setup_logging('hype', logs_dir, verbose_logs=config.system.verbose_logs,
                           file_logging=config.system.file_logging)
    logger.info(f'Mode: {args.mode}')
    if args.mode == Mode.ModeMock.value and args.test_all_configs:
        test_all_configs(config, logger, metrics_manager, args.reference)
        return
    provider = create_provider(args, config)
    account = Account(config, logger, provider, metrics_manager)
    if args.mode == Mode.ModeOperational.value:
        account.trade_detached()
    else:
        account.trade()
    account.close()
    print(account.generate_trade_results())


if __name__ == '__main__':
    main()
