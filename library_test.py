"""Test script for aioamazondevices library."""

import asyncio
import getpass
import json
import logging
import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import orjson
from aiohttp import ClientSession
from colorlog import ColoredFormatter

from aioamazondevices.api import AmazonDevice, AmazonEchoApi, AmazonMusicSource
from aioamazondevices.const import SAVE_PATH
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
        "--email",
        "-e",
        type=str,
        help="Set Amazon login e-mail",
    )
    parser.add_argument("--password", "-p", type=str, help="Set Amazon login password")
    parser.add_argument("--otp_code", "-o", type=str, help="Set Amazon OTP code")
    parser.add_argument(
        "--login_data_file",
        "-ld",
        type=str,
        default=f"{SAVE_PATH}/login-data.json",
        help="Login data file",
    )
    parser.add_argument(
        "--single_device_name",
        "-sdn",
        type=str,
        help="Single device name to send message via 'Alexa.Speak'",
    )
    parser.add_argument(
        "--cluster_device_name",
        "-cdn",
        type=str,
        help="Cluster device name to send message via 'AlexaAnnouncement'",
    )
    parser.add_argument(
        "--save_raw_data",
        "-s",
        action="store_true",
        help="Save HTML source on disk",
    )
    parser.add_argument(
        "--test",
        "-t",
        action="store_true",
        help="Execute test actions",
    )
    parser.add_argument(
        "--configfile",
        "-cf",
        type=str,
        help="Load options from JSON config file. \
        Command line options override those in the file.",
    )

    arguments_cli = parser.parse_args()
    args = vars(arguments_cli)
    # Re-parse the command line
    # taking the options in the optional JSON file as additional arguments to cli
    cfg_file = arguments_cli.configfile
    if cfg_file and Path(cfg_file).exists():
        with Path.open(cfg_file) as f:
            arguments_cfg = parser.parse_args(namespace=Namespace(**json.load(f)))
        args.update(vars(arguments_cfg))

    return parser, Namespace(**args)


def save_to_file(filename: str, data_dict: dict[str, Any]) -> None:
    """Save data to json file."""
    data_json = orjson.dumps(
        data_dict,
        option=orjson.OPT_INDENT_2,
    ).decode("utf-8")
    Path(filename).parent.mkdir(parents=True, exist_ok=True)
    with Path.open(Path(filename), mode="w", encoding="utf-8") as file:
        file.write(data_json)
        file.write("\n")


def read_from_file(data_file: str) -> dict[str, Any]:
    """Load stored login data from file."""
    if not data_file or not (file := Path(data_file)).exists():
        print(
            "Cannot find previous login data file: ",
            data_file,
        )
        return {}

    with Path.open(file, "rb") as f:
        return cast("dict[str, Any]", json.load(f))


def find_device(
    devices: dict[str, AmazonDevice],
    name: str | None,
    condition: Callable[[AmazonDevice], bool],
) -> AmazonDevice:
    """Extract device from list."""
    try:
        return next(
            dev
            for dev in devices.values()
            if ((dev.account_name == name) if name else condition(dev))
        )
    except StopIteration:
        print(f"Unable to find requested device {name}, use one of this devices :")
        for device in devices.values():
            if condition(device):
                print(f"\t{device.account_name}")
        sys.exit(0)


async def wait_action_complete(sleep: int = 4) -> None:
    """Wait for an action to complete."""
    print(f"Waiting for {sleep}s before next test")
    await asyncio.sleep(sleep)


async def main() -> None:
    """Run main."""
    parser, args = get_arguments()

    login_data_stored = read_from_file(args.login_data_file)

    if not login_data_stored and not args.password:
        print(f"You have to specify credentials for {args.email}")
        args.password = getpass.getpass("Password: ")

    client_session = ClientSession()

    api = AmazonEchoApi(
        client_session,
        args.email,
        args.password,
        login_data_stored,
    )

    if args.save_raw_data:
        api.save_raw_data()

    try:
        try:
            if login_data_stored:
                login_data = await api.login_mode_stored_data()
            else:
                login_data = await api.login_mode_interactive(
                    args.otp_code or input("OTP Code: ")
                )
        except CannotAuthenticate:
            print(f"Cannot authenticate with {args.email} credentials")
            raise
        except CannotConnect:
            print(f"Cannot connect to {api.domain} Amazon host")
            raise
        except CannotRegisterDevice:
            print(f"Cannot register device for {args.email}")
            raise
    except AmazonError:
        await client_session.close()
        sys.exit(2)

    print("Logged-in.")

    print("-" * 20)
    print("Login data:", login_data)
    print("-" * 20)

    save_to_file(f"{SAVE_PATH}/output-login-data.json", login_data)

    print("-" * 20)
    try:
        devices = await api.get_devices_data()
    except (CannotAuthenticate, CannotConnect, CannotRegisterDevice) as exc:
        print(exc)
        await client_session.close()
        sys.exit(3)

    print("Devices count  :", len(devices))
    print("Devices details:", devices)
    print("-" * 20)

    if not devices:
        print("!!! Warning: No devices found !!!")
        await client_session.close()
        sys.exit(0)

    save_to_file(f"{SAVE_PATH}/output-devices.json", devices)

    if not args.test:
        print("!!! No testing requested, exiting !!!")
        await client_session.close()
        sys.exit(0)

    device_single = find_device(
        devices, args.single_device_name, lambda d: len(d.device_cluster_members) == 1
    )
    if args.cluster_device_name:
        device_cluster = find_device(
            devices,
            args.cluster_device_name,
            lambda d: len(d.device_cluster_members) > 1,
        )
    else:
        device_cluster = device_single

    print("Selected devices:")
    print("- single : ", device_single)
    print("- cluster: ", device_cluster)

    if not await api.auth_check_status():
        print("!!! Error: Session not authenticated !!!")
        await client_session.close()
        sys.exit(4)
    print("Session authenticated!")

    print("Sending message via 'Alexa.Speak' to:", device_single.account_name)
    await api.call_alexa_speak(device_single, "Test Speak message from new library")

    await wait_action_complete()

    print("Sending message via 'AlexaAnnouncement' to:", device_cluster.account_name)
    await api.call_alexa_announcement(
        device_cluster, "Test Announcement message from new library"
    )

    await wait_action_complete()

    print("Sending sound via 'Alexa.Sound' to:", device_single.account_name)
    await api.call_alexa_sound(device_single, "amzn_sfx_doorbell_chime_01")

    await wait_action_complete()

    radio = "BBC one"
    source = AmazonMusicSource.Radio
    print(f"Playing {radio} from {source} on {device_single.account_name}")
    await api.call_alexa_music(device_single, radio, source)

    await wait_action_complete(15)

    music = "taylor swift"
    source = AmazonMusicSource.AmazonMusic
    print(f"Playing {music} from {source} on {device_single.account_name}")
    await api.call_alexa_music(device_single, music, source)

    await wait_action_complete(15)

    print(f"Text command on {device_single.account_name}")
    await api.call_alexa_text_command(device_single, "Set timer pasta 12 minute")

    await wait_action_complete(10)

    print("Launch 'MyTuner Radio' skill on ", device_cluster.account_name)
    await api.call_alexa_skill(
        device_cluster, "amzn1.ask.skill.94c477e7-61c0-43f5-b7d9-36d7498a4d04"
    )

    print("Closing session")
    await client_session.close()


def set_logging() -> None:
    """Set logging levels."""
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
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
