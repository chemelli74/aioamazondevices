"""Test script for aioamazondevices library."""

import asyncio
import json
import logging
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from colorlog import ColoredFormatter

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import (
    AmazonError,
    CannotAuthenticate,
    CannotConnect,
    CannotRegisterDevice,
)


def get_arguments() -> tuple[ArgumentParser, Namespace]:
    """Get parsed passed in arguments."""
    parser = ArgumentParser(description="aioamazondevices library test")
    parser.add_argument(
        "--country",
        "-c",
        type=str,
        default="it",
        help="Set Amazon login country",
    )
    parser.add_argument(
        "--email",
        "-e",
        type=str,
        help="Set Amazon login e-mail",
    )
    parser.add_argument("--password", "-p", type=str, help="Set Amazon login password")
    parser.add_argument("--otp_code", "-o", type=str, help="Set Amazon OTP code")
    parser.add_argument(
        "--save_raw_data",
        "-s",
        type=str,
        default="False",
        help="Save HTML source on disk",
    )
    parser.add_argument(
        "--configfile",
        "-cf",
        type=str,
        help="Load options from JSON config file. \
        Command line options override those in the file.",
    )

    arguments = parser.parse_args()
    # Re-parse the command line
    # taking the options in the optional JSON file as a basis
    if arguments.configfile and Path(arguments.configfile).exists():
        with Path.open(arguments.configfile) as f:
            arguments = parser.parse_args(namespace=Namespace(**json.load(f)))

    return parser, arguments


async def main() -> None:
    """Run main."""
    parser, args = get_arguments()

    if not args.password:
        print("You have to specify a password")
        parser.print_help()
        sys.exit(1)

    api = AmazonEchoApi(
        args.country,
        args.email,
        args.password,
        args.save_raw_data.lower() in ("yes", "true", "1"),
    )

    try:
        try:
            login_data = await api.login(args.otp_code or input("OTP Code: "))
        except CannotAuthenticate:
            print(f"Cannot authenticate with {args.email} credentials")
            raise
        except CannotConnect:
            print(f"Cannot authenticate to {args.country} Amazon host")
            raise
        except CannotRegisterDevice:
            print(f"Cannot register device for {args.email}")
            raise
    except AmazonError:
        await api.close()
        sys.exit(1)

    print("Logged-in.")

    print("-" * 20)
    print("Login data:", login_data)
    print("-" * 20)

    print("-" * 20)
    devices = await api.get_devices_data()
    print("Devices:", devices)
    print("-" * 20)

    await api.close()


def set_logging() -> None:
    """Set logging levels."""
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("charset_normalizer").setLevel(logging.WARNING)
    fmt = (
        "%(asctime)s.%(msecs)03d %(levelname)s (%(threadName)s) [%(name)s] %(message)s"
    )
    colorfmt = f"%(log_color)s{fmt}%(reset)s"
    logging.getLogger().handlers[0].setFormatter(
        ColoredFormatter(
            colorfmt,
            datefmt="%Y-%m-%d %H:%M:%S",
            reset=True,
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red",
            },
        ),
    )


if __name__ == "__main__":
    set_logging()
    asyncio.run(main())
