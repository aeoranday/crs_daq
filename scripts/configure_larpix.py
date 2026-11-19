import argparse
import json
import logging
import os
import sys
from typing import Any
import warnings

import larpix
import larpix.io

from crs_daq.base import config_loader, enforce_parallel, pacman, utility
from crs_daq.runenv import runenv as RUN

warnings.filterwarnings("ignore")

logger: logging.Logger = logging.getLogger(__name__)

_default_verbose: bool = False


def main(
    verbose: bool,  # FIXME AEO: Unused variable.
    asic_config: str,
    config_subdir: str,
    pacman_config: str,
    no_unmask_last: bool = False,
    pid_logged: bool = False,
) -> None:

    unmask_last: bool = not no_unmask_last
    pacman_configs: dict[str, Any] = {}
    with open(pacman_config, "r") as f:
        pacman_configs = json.load(f)

    controller: larpix.Controller = larpix.Controller()
    controller.io = larpix.io.PACMAN_IO(
        relaxed=True, config_filepath=pacman_config, asic_version=3
    )

    # list of network keys in order from root chip, for parallel configuration enforcement
    all_network_keys: list[list[larpix.Key]] = []

    for io_group_ip_pair in pacman_configs["io_group"]:
        io_group: int = io_group_ip_pair[0]

        CONFIG: str | None = None
        if asic_config is None:
            print("Loading current config...")
            CONFIG = utility.get_from_json(RUN.config["asic_config_paths_file_"], io_group)
        else:
            CONFIG = asic_config
            if config_subdir is not None:
                CONFIG = "{}/{}".format(asic_config, config_subdir)
            utility.update_json(RUN.config["asic_config_paths_file_"], io_group, CONFIG)

        network_config_file: dict[str, Any] | Any | None = utility.get_from_json(
            RUN.config["network_config_paths_file_"], io_group
        )
        if type(network_config_file) is not str:
            raise RuntimeError(
                f"Unexpected type for `network_config_file`. Got {type(network_config_file)}; expected str."
            )
        all_network_keys += enforce_parallel.get_chips_by_io_group_io_channel(
            network_config_file
        )
        config_loader.load_config_from_directory(controller, CONFIG)

        # make the network keys io channel agnostic
        remove: list[larpix.Key] = []
        for i in range(len(all_network_keys)):
            for j in range(len(all_network_keys[i])):
                if all_network_keys[i][j] not in controller.chips:

                    found: bool = False
                    chip: larpix.Key = all_network_keys[i][j]
                    tile: int = utility.io_channel_to_tile(chip.io_channel)
                    io_channels: list[int] = [1 + 4 * (tile - 1) + n for n in range(4)]

                    for io_channel in io_channels:
                        chip_key: larpix.Key = larpix.Key(
                            chip.io_group, io_channel, chip.chip_id
                        )
                        if chip_key in controller.chips:
                            all_network_keys[i][j] = chip_key
                            found = True
                            break

                    if not found:
                        remove.append(chip)

        for chip in remove:

            for i in range(len(all_network_keys)):
                if chip in all_network_keys[i]:
                    all_network_keys[i].remove(chip)

    # ensure UARTs are enable on pacman to receive configuration packets
    for io_group_ip_pair in pacman_configs["io_group"]:
        io_group = io_group_ip_pair[0]
        pacman.enable_pacman_uart_from_io_channel(
            controller.io,
            io_group,
            list(set([chip.io_channel for chip in controller.chips])),
        )
        # logger.info('starting configuration enforce: io_group={}'.format(io_group))

    pos: int = 0
    tag: str = "configuring..."
    if pid_logged:
        pid: int = os.getpid()
        tag = utility.get_from_process_log(pid)
        if tag is None:
            raise RuntimeError(f"Could not find the PID = {pid} in the log file.")
        pos = enforce_parallel.tag_to_config_map[tag]

    logger.info(
        "started configuring: io_groups={}, {}/{}".format(
            pacman_configs["io_group"], str(asic_config), str(config_subdir)
        )
    )
    # enforce all configurations in parallel (one chip per io channel per cycle)
    ok, diff, unconfigured = enforce_parallel.enforce_parallel(
        controller,
        all_network_keys,
        unmask_last=unmask_last,
        pbar_desc=tag,
        pbar_position=pos,
    )
    if not ok:
        raise RuntimeError(diff)

    if pid_logged:
        print("\n{} configured successfully".format(tag))
    logger.info(
        "completed configuring: io_groups={}".format(pacman_configs["io_group"])
    )
    return


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--asic_config",
        default=None,
        type=str,
        help="""ASIC config to load and enforce""",
    )
    parser.add_argument(
        "--config_subdir",
        default=None,
        type=str,
        help="""Subdirectory in larger config dir. Ignroed if asic_config not specified""",
    )
    parser.add_argument(
        "--pacman_config",
        default="configs/io/pacman.json",
        type=str,
        help="""Config specifying PACMANs""",
    )
    parser.add_argument("--pid_logged", action="store_true", default=False)
    parser.add_argument("--no_unmask_last", action="store_true", default=False)
    parser.add_argument(
        "--verbose", "-v", action="store_true", default=_default_verbose
    )
    args = parser.parse_args()
    main(**vars(args))
