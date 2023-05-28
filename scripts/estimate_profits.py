#!/usr/bin/env python3

import csv
import argparse


def parse_args() -> argparse.Namespace:
    args = argparse.ArgumentParser(description='Managing Secrets')
    args.add_argument('-p', '--profits', help='Path to profits CSV', required=True)
    args.add_argument('-d', '--dividend', help='Amount of dividend taken per positive profit', type=float, default=0.15)
    return args.parse_args()


def main():
    args = parse_args()
    with open(args.profits, 'r') as profits_file:
        c = csv.reader(profits_file)
        next(c)
        total = 0
        dividend = 0
        for _, _, _, profit in c:
            profit = float(profit)
            temp_div = profit * args.dividend
            if temp_div > 0:
                dividend += temp_div
            total += profit - temp_div
        print('Total profit:', total)
        print('Dividend taken:', dividend)




if __name__ == '__main__':
    main()
