#!/usr/bin/env python3
"""
Configure a LArPix Controller with the given configurations.
"""

import json
import logging
import os
import warnings
from pathlib import Path
from typing import Any

import click
import larpix
import larpix.io

from crs_daq.base import config_loader, enforce_parallel, pacman, utility
from crs_daq.runenv import runenv as RUN

warnings.filterwarnings("ignore")
logger: logging.Logger = logging.getLogger(__name__)

ASIC_VERSION: int = 3


def get_io_group_config_path(
    io_group: int, asic_config_dir: Path | None, config_subdir: Path | None
) -> Path:
    """
    Get the configuration path for the given IO group.

    Parameters
    ----------
    io_group : int
        The IO group number to be searching with.
    asic_config_dir : Path | None
        The ASIC configuration directory or None. Uses `asic_config_paths_file_` defined in
        `config/RUN_CONFIG.json` if None.
    config_subdir : Path | None
        A subdirectory within `asic_config_dir` to search within.

    Returns
    -------
    Path
        A path to the ASIC configuration directory to use for this IO group.
    """
    config: Path
    if asic_config_dir is None:
        print("Loading current config...")
        config = Path(utility.get_from_json(RUN.config["asic_config_paths_file_"], io_group))
        return config
    config = asic_config_dir
    if config_subdir is not None:
        config = asic_config_dir / config_subdir
    utility.update_json(RUN.config["asic_config_paths_file_"], io_group, str(config))
    return config


def get_io_group_keys(
    io_group: int,
    controller: larpix.Controller,
    asic_config_dir: Path | None,
    config_subdir: Path | None,
) -> list[list[larpix.Key]]:
    """
    Get the LArPix keys that belong to the given IO group.

    Parameters
    ----------
    io_group : int
        The IO group number to query on.
    controller : larpix.Controller
        The Controller that manages the system. The config for the given IO group will be loaded
        into this controller.
    asic_config_dir : Path | None
        A directory containing ASIC configuration files. If None, uses the default ASIC config dir
        path that is in `configs/RUN_CONFIG.json`.
    config_subdir : Path | None
        An optional subdirectory within `asic_config_dir`. Would load the contents of this subdir.

    Returns
    -------
    list[list[larpix.Key]]
        The LArPix chip keys that belong to the same IO group number and IO channel number.
    """
    config: Path = get_io_group_config_path(io_group, asic_config_dir, config_subdir)
    network_config_file: dict[str, Any] | Any | None = utility.get_from_json(
        RUN.config["network_config_paths_file_"], io_group
    )

    if not isinstance(network_config_file, str):
        raise RuntimeError(
            "Unexpected type for `network_config_file`."
            f"Got {type(network_config_file)}; expected str."
        )
    group_keys: list[list[larpix.Key]] = enforce_parallel.get_chips_by_io_group_io_channel(
        network_config_file
    )
    _ = config_loader.load_config_from_directory(controller, config)
    return group_keys


@click.command()
@click.option(
    "--asic-config-dir",
    type=click.Path(readable=True, file_okay=False, dir_okay=True, path_type=Path),
    help="ASIC config directory to load from and enforce.",
)
@click.option(
    "--config-subdir",
    type=click.Path(readable=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Subdirectory in larger config dir. Ignored if asic-config is not specified.",
)
@click.option(
    "--pacman-config",
    type=click.Path(readable=True, dir_okay=False, path_type=Path),
    default=Path("configs/io/pacman.json"),
    help="Config specifying PACMANs.",
)
@click.option("--pid-logged", is_flag=True, default=False)
@click.option("--no-unmask-last", is_flag=True, default=False)
def main(
    asic_config_dir: Path,
    config_subdir: Path,
    pacman_config: Path,
    no_unmask_last: bool,
    pid_logged: bool,
) -> None:
    """
    Configure a LArPix Controller with the given configurations.
    """
    with open(pacman_config, "r", encoding="utf-8") as f:
        pacman_configs: dict[str, Any] = json.load(f)

    controller: larpix.Controller = larpix.Controller()
    controller.io = larpix.io.PACMAN_IO(
        relaxed=True, config_filepath=pacman_config, asic_version=ASIC_VERSION
    )

    # list of network keys in order from root chip, for parallel configuration enforcement
    all_network_keys: list[list[larpix.Key]] = []
    for (io_group, _) in pacman_configs["io_group"]:
        all_network_keys += get_io_group_keys(io_group, controller, asic_config_dir, config_subdir)

    # ensure UARTs are enable on pacman to receive configuration packets
    for io_group_ip_pair in pacman_configs["io_group"]:
        io_group: int = io_group_ip_pair[0]
        pacman.enable_pacman_uart_from_io_channel(
            controller.io,
            io_group,
            list({chip.io_channel for chip in controller.chips}),
        )

    pos: int = 0
    tag: str = "configuring..."
    if pid_logged:
        pid: int = os.getpid()
        tag = utility.get_from_process_log(pid)
        if tag is None:
            raise RuntimeError(f"Could not find the PID = {pid} in the log file.")
        pos = enforce_parallel.tag_to_config_map[tag]

    logger.info(
        "started configuring: io_groups=%s, %s/%s",
        pacman_configs["io_group"],
        asic_config_dir,
        config_subdir,
    )
    # enforce all configurations in parallel (one chip per io channel per cycle)
    ok, diff, _ = enforce_parallel.enforce_parallel(
        controller,
        all_network_keys,
        unmask_last=not no_unmask_last,
        pbar_desc=tag,
        pbar_position=pos,
    )
    if not ok:
        raise RuntimeError(diff)

    if pid_logged:
        print(f"\n{tag} configured successfully")
    logger.info("completed configuring: io_groups=%s", pacman_configs["io_group"])


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
