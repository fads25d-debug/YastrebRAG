"""Server administrator CLI: python -m yastreb.manage add-user."""
import argparse
import getpass
import os
from pathlib import Path
from yastreb.accounts import Accounts, ROLES


def main():
    parser = argparse.ArgumentParser(description='Локальные пользователи «Ястреб»')
    parser.add_argument('command', choices=['add-user'])
    parser.add_argument('--email', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--role', choices=ROLES, required=True)
    args = parser.parse_args()
    password = getpass.getpass('Пароль (не менее 12 символов): ')
    if password != getpass.getpass('Повторите пароль: '):
        parser.error('Пароли не совпадают.')
    Accounts(Path(os.environ.get('YASTREB_DATA_DIR', 'data')) / 'accounts' / 'users.sqlite').create_user(
        args.email, args.name, args.role, password)
    print('Пользователь создан.')


if __name__ == '__main__':
    main()
