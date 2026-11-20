#!/usr/bin/env python3
"""
Network the LArPix chips from the given controller and PACMAN configurations.
"""
import json
import logging
import os
import warnings
from pathlib import Path

import click
import larpix
import larpix.io

from crs_daq.base import (
    config_loader,
    enforce_parallel,
    network,
    network_FSD,
    network_FSD_v3,
    pacman,
    utility,
)
from crs_daq.runenv import runenv as RUN

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)
DEFAULT_VERBOSE: bool = True
DEFAULT_CONTROLLER_CONFIG: Path = Path("configs/controller_config.json")
UPDATE_DEFAULT: bool = False


def enforce_iterative(
    nc, all_network_keys, n=1, configs=None, pbar_desc="p", pbar_position=0
):
    ok, diff, unconfigured = enforce_parallel.enforce_parallel(
        nc, all_network_keys, pbar_desc=pbar_desc, pbar_position=pbar_position
    )
    if ok:
        return ok, diff, unconfigured
    elif n == 0:
        return ok, diff, unconfigured
    else:
        all_keys = list(diff)
        for net in unconfigured:
            all_keys += list(net)

        all_network_keys = []
        io_group_tiles = {}
        for chip_key in diff:
            if chip_key.io_group not in io_group_tiles:
                io_group_tiles[chip_key.io_group] = set()
            io_group_tiles[chip_key.io_group].add(
                utility.io_channel_to_tile(chip_key.io_channel)
            )

        for chip_key in all_keys:
            if chip_key.io_group not in io_group_tiles:
                io_group_tiles[chip_key.io_group] = None

        for io_group in io_group_tiles:
            tiles = io_group_tiles[io_group]
            config = configs[str(io_group)]
            if RUN.config["io_group_asic_version_"][io_group] == "2b":
                c = network.network_v2b(config)

            elif RUN.config["io_group_asic_version_"][io_group] in [2, "lightpix-1"]:
                c = network.network_v2a(config)

            elif RUN.config["io_group_asic_version_"][io_group] in [3]:
                c = network_FSD_v3.network_v3(config, tiles=tiles)

            all_network_keys += enforce_parallel.get_chips_by_io_group_io_channel(
                config, use_keys=all_keys
            )

        return enforce_iterative(
            nc,
            all_network_keys,
            n=n - 1,
            configs=configs,
            pbar_desc=pbar_desc,
            pbar_position=pbar_position,
        )


@click.command()
@click.option("--verbose", "-v", is_flag=True, default=DEFAULT_VERBOSE)
@click.option(
    "--config-path",
    type=click.Path(writable=True, path_type=Path),
    help="Path to save configuration.",
)
@click.option(
    "--controller-config",
    default=DEFAULT_CONTROLLER_CONFIG,
    type=click.Path(readable=True, dir_okay=False, path_type=Path),
    help="""Controller config specifying hydra network""",
)
@click.option(
    "--pacman-config",
    default=Path("configs/io/pacman.json"),
    type=click.Path(readable=True, dir_okay=False, path_type=Path),
    help="Config specifying PACMANs.",
)
@click.option("--pid-logged", is_flag=True, default=False)
@click.option("--update-default", is_flag=True, default=UPDATE_DEFAULT)
def main(
    verbose: bool,
    controller_config: Path,
    io_group_tiles,
    pacman_config: Path,
    config_path: Path,
    pid_logged: bool,
    update_default: bool,
) -> larpix.Controller:
    """
    Network the LArPix chips from the given controller and PACMAN configurations.
    """
    pacman_configs = {}
    with open(pacman_config, "r") as f:
        pacman_configs = json.load(f)

    configs = {}
    with open(controller_config, "r") as f:
        configs = json.load(f)

    DCONFIGS = {}

    # for each io_group, perform networking
    all_network_keys = []
    for io_group_ip_pair in pacman_configs["io_group"]:
        io_group = io_group_ip_pair[0]
        tiles = None
        if io_group_tiles is not None:
            if io_group not in io_group_tiles:
                continue
            else:
                tiles = io_group_tiles[io_group]

        if verbose:
            print(f"Configuring {io_group=}")
        controller: larpix.Controller | None = None

        config = configs[str(io_group)]
        _ = utility.update_json(
            RUN.config["network_config_paths_file_"], io_group, config
        )
        if RUN.config["io_group_asic_version_"][io_group] in ["2b", "2d"]:
            controller = network_FSD.network_v2b(config)
        elif RUN.config["io_group_asic_version_"][io_group] in [3]:
            controller = network_FSD_v3.network_v3(config, tiles=tiles)
        elif RUN.config["io_group_asic_version_"][io_group] in [2, "lightpix-1"]:
            if verbose:
                print("loading network_v2a")
            controller = network.network_v2a(config)
            if verbose:
                print("done")

        all_network_keys += enforce_parallel.get_chips_by_io_group_io_channel(
            config, tiles
        )

        _tiles = []
        for _, io_channels in controller.network.items():
            _tiles += utility.io_channel_list_to_tile(list(io_channels))

        _update_now = False
        CONFIG = utility.get_from_json(
            RUN.config["default_asic_config_paths_file_"], io_group
        )
        if update_default or CONFIG is None:
            config_path = config_loader.write_config_to_file(controller, config_path)
            _update_now = True

        DCONFIG = None
        if _update_now:
            _ = utility.update_json(
                RUN.config["default_asic_config_paths_file_"], io_group, config_path
            )
            DCONFIG = config_path
        else:
            DCONFIG = utility.get_from_json(
                RUN.config["default_asic_config_paths_file_"], io_group
            )
        _ = utility.update_json(
            RUN.config["asic_config_paths_file_"], io_group, DCONFIG
        )
        DCONFIGS[io_group] = DCONFIG

    nc = larpix.Controller()
    nc.io = larpix.io.PACMAN_IO(
        relaxed=True, config_filepath=pacman_config, asic_version=3
    )
    logger.info("starting networking: io_groups={}".format(pacman_configs["io_group"]))
    for io_group_ip_pair in pacman_configs["io_group"]:
        io_group = io_group_ip_pair[0]
        for iog in DCONFIGS:
            config_loader.load_config_from_directory(nc, DCONFIGS[iog])
        pacman.enable_pacman_uart_from_io_channel(
            nc.io, io_group, list(set([chip.io_channel for chip in nc.chips]))
        )
    pos = 0

    tag = "networking..."
    if pid_logged:
        pid = os.getpid()
        tag = utility.get_from_process_log(pid)
        pos = enforce_parallel.tag_to_config_map[tag]

    ok, diff, _ = enforce_iterative(
        nc, all_network_keys, configs=configs, pbar_desc=tag, pbar_position=pos
    )
    if not ok:
        raise RuntimeError("Unconfigured chips!", diff)

    if pid_logged:
        print(f"\n{tag} networked successfully")

    logger.info("completed networking: io_groups={}".format(pacman_configs["io_group"]))
    return controller


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
