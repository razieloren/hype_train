#!/usr/bin/env python3

import os
import base64
import argparse

from enum import Enum
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class Operation(Enum):
    Encrypt = 'encrypt'
    Decrypt = 'decrypt'
    AvailableOperations = [Encrypt, Decrypt]


def parse_args() -> argparse.Namespace:
    args = argparse.ArgumentParser(description='Managing Secrets')
    args.add_argument('-s', '--secret', help='Secret to operate on', required=True)
    args.add_argument('-a', '--salt', help='Secret salt, when needed', default=None)
    args.add_argument('-o', '--operation', choices=Operation.AvailableOperations.value, required=True)
    args.add_argument('-p', '--password', help='Password to use, when needed', default='test_password')
    return args.parse_args()


def main():
    args = parse_args()

    salt = os.urandom(16) if args.salt is None else base64.urlsafe_b64decode(args.salt.encode())
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
    key = base64.urlsafe_b64encode(kdf.derive(args.password.encode()))
    fernet = Fernet(key)
    if args.operation == Operation.Encrypt.value:
        token = fernet.encrypt(args.secret.encode())
        print(token, base64.urlsafe_b64encode(salt))
    elif args.operation == Operation.Decrypt.value:
        print(fernet.decrypt(args.secret.encode()))


if __name__ == '__main__':
    main()
