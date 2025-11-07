"""Test script for aioamazondevices library."""

import asyncio
import getpass
import json
import logging
import mimetypes
import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import orjson
from aiohttp import ClientSession
from colorlog import ColoredFormatter

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import (
    AmazonError,
    CannotAuthenticate,
    CannotConnect,
    CannotRegisterDevice,
)
from aioamazondevices.structures import AmazonDevice, AmazonMusicSource

SAVE_PATH = "out"
HTML_EXTENSION = ".html"
BIN_EXTENSION = ".bin"
RAW_EXTENSION = ".raw"


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


async def save_to_file(
    raw_data: str | dict,
    url: str,
    content_type: str = "application/json",
) -> None:
    """Save response data to disk."""
    if not raw_data:
        return

    output_dir = Path(SAVE_PATH)
    output_dir.mkdir(parents=True, exist_ok=True)

    extension = mimetypes.guess_extension(content_type.split(";")[0]) or RAW_EXTENSION

    if url.startswith("http"):
        url_split = url.split("/")
        base_filename = f"{url_split[3]}-{url_split[4].split('?')[0]}"
    else:
        base_filename = url
    fullpath = Path(output_dir, base_filename + extension)

    data: str
    if isinstance(raw_data, dict):
        data = orjson.dumps(raw_data, option=orjson.OPT_INDENT_2).decode("utf-8")
    elif extension in [HTML_EXTENSION, BIN_EXTENSION]:
        data = raw_data
    else:
        data = orjson.dumps(
            orjson.loads(raw_data),
            option=orjson.OPT_INDENT_2,
        ).decode("utf-8")

    i = 2
    while fullpath.exists():
        filename = f"{base_filename}_{i!s}{extension}"
        fullpath = Path(output_dir, filename)
        i += 1

    print(f"Saving data to {fullpath}")

    with Path.open(fullpath, mode="w", encoding="utf-8") as file:
        file.write(data)
        file.write("\n")


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
    _, args = get_arguments()

    login_data_stored = read_from_file(args.login_data_file)

    if not login_data_stored and not args.password:
        print(f"You have to specify credentials for {args.email}")
        args.password = getpass.getpass("Password: ")

    client_session = ClientSession()

    api = AmazonEchoApi(
        client_session=client_session,
        login_email=args.email,
        login_password=args.password,
        login_data=login_data_stored,
        save_to_file=save_to_file,
    )

    try:
        try:
            if login_data_stored:
                login_data = await api.login_mode_stored_data()
            else:
                login_data = await api.login_mode_interactive(
                    args.otp_code or input("OTP Code: ")
                )
                await save_to_file(login_data, "login_data")
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

    await save_to_file(login_data, "output-login-data")

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

    await save_to_file(devices, "output-devices")

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

    for sensor in device_single.sensors:
        print(f"Sensor {device_single.sensors[sensor]}")

    for notification in device_single.notifications:
        print(f"Notification {device_single.notifications[notification]}")

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

    print("Sending message via 'Alexa.Date.Play' to:", device_single.account_name)
    await api.call_alexa_info_skill(device_single, "Alexa.Date.Play")

    await wait_action_complete(5)

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

    for notification in device_single.notifications:
        print(f"Notification {device_single.notifications[notification]}")

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
