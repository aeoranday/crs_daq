#!/usr/bin/env python3
"""
Network the LArPix chips from the given controller and PACMAN configurations.
"""

import json
import logging
import os
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Any

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


def network_new_controller_by_io_group(
    io_group: int,
    controller_config: str,
    tiles: set[int] | None = None,
    use_keys: list[larpix.Key] | None = None,
) -> tuple[list[list[larpix.Key]], larpix.Controller]:
    """
    Create a new LArPix Controller for the given IO group and initialize its chip network.

    Parameters
    ----------
    io_group : int
        The IO group number that is being initialized.
    controller_config : str
        The controller configuration path to use for the initialization.
    tiles : set[int] | None
        A list of tile numbers to configure. If None, configure all tiles for the IO group. **Only
        used by v3 chips.**
    use_keys : list[larpix.Key] | None
        Specific chip keys to use as part of the initialization. Chip keys that belong to the IO
        group and are _not_ in this list are skipped.

    Returns
    -------
    tuple[list[list[larpix.Key]], larpix.Controller]
        A list of the networked LArPix chip keys, groupe by IO group and IO channel number, and
        the initialized LArPix Controller for this network.
    """
    controller: larpix.Controller
    match RUN.config["io_group_asic_version_"][io_group]:
        case 2 | "lightpix-1":
            controller = network.network_v2a(controller_config)
        case "2b" | "2d":
            controller = network_FSD.network_v2b(controller_config)
        case 3:
            controller = network_FSD_v3.network_v3(controller_config, tiles=tiles)
        case _:
            raise RuntimeError(
                "RUN_CONFIG.json has an unsupported IO group ASIC version: "
                f"{RUN.config['io_group_asic_version_'][io_group]}. Supported "
                "versions are: 2, 'lightpix-1', '2b', '2d', or 3."
            )

    network_keys = enforce_parallel.get_chips_by_io_group_io_channel(
        controller_config, use_keys=use_keys
    )
    return network_keys, controller


def enforce_iterative(
    nc: larpix.Controller,
    all_network_keys: list[list[larpix.Key]],
    configs: dict[str, str],
    n: int = 1,
    pbar_desc: str = "p",  # FIXME: Unused by upstream. Remove in both locations.
    pbar_position: int = 0,  # FIXME: Unused by upstream. Remove in both locations.
):
    """
    Recursively initialize the chip network for the given LArPix controller.

    Parameters
    ----------
    nc : larpix.Controller
        The LArPix Controller to configure.
    all_network_keys : list[list[larpix.Key]]
        The LArPix chip keys, grouped by IO group number and IO channel number.
    configs : dict[str, str]
        A mapping from the `str(io_group)` to its configuration path as a string.
    n : int
        Recursion counter. Breaks recursion when `n == 1`.
    pbar_desc : str
        The `tqdm` progress bar description. **Unused by `enforce_parallel.enforce_parallel`.**
    pbar_position: int
        The `tqdm` progress bar position. **Unused by `enforce_parallel.enforce_parallel`.**

    Returns
    -------
    tuple[bool, dict[larpix.Key, dict[int, tuple[int, int]]], list[list[larpix.Key]]]
        A bool for if the config was set (True) or not (False); a dict for the differences in each
        misconfigured chip's register a tuple of the (<expected>, <received>) values; and a list
        of the LArPix chip keys that are not configured, grouped by (IO group number, IO channel
        number).

    See Also
    --------
    larpix.controller.Controller.verify_registers
        Generates the `ok` return bool and the `diff` differences dict for the chip registers.
    crs_daq.base.enforce_parallel.enforce_parallel
        Uses the above and adds the `unconfigured` chip list.
    """
    ok, diff, unconfigured = enforce_parallel.enforce_parallel(
        nc, all_network_keys, pbar_desc=pbar_desc, pbar_position=pbar_position
    )
    if ok:
        return ok, diff, unconfigured
    if n == 0:
        return ok, diff, unconfigured
    all_keys: list[larpix.Key] = list(diff)
    for net in unconfigured:
        all_keys += list(net)

    all_network_keys: list[list[larpix.Key]] = []
    io_group_tiles: dict[int, set | None] = defaultdict(set)
    for chip_key in diff:
        io_group_tiles[chip_key.io_group].add(utility.io_channel_to_tile(chip_key.io_channel))

    for chip_key in all_keys:
        if chip_key.io_group not in io_group_tiles:
            io_group_tiles[chip_key.io_group] = None

    for io_group, tiles in io_group_tiles.items():
        config = configs[str(io_group)]
        network_keys, _ = network_new_controller_by_io_group(io_group, config, tiles)
        all_network_keys += network_keys

    return enforce_iterative(
        nc,
        all_network_keys,
        configs,
        n=n - 1,
        pbar_desc=pbar_desc,
        pbar_position=pbar_position,
    )


def network_by_io_group(
    io_group: int,
    controller_config: str,
    config_path: Path | None,
    update_default: bool,
    verbose: bool,
) -> tuple[Path, list[list[larpix.Key]]]:
    """
    Initialize the LArPix chip network by IO group.

    Parameters
    ----------
    io_group : int
        The IO group number to initialize.
    controller_config : str
        The LArPix controller configuration to use for this IO group.
    config_path : Path | None
        A path to write the configuration to.
    update_default : bool
        Flag whether to update the default configuration or not.
    verbose : bool

    Returns
    -------
    tuple[Path, list[list[larpix.Key]]
        A path for the configuration that was used and a list of LArPix chip Keys grouped by
        IO group and IO channel.
    """
    if verbose:
        print(f"Configuring {io_group=}")

    _ = utility.update_json(RUN.config["network_config_paths_file_"], io_group, controller_config)

    network_keys, controller = network_new_controller_by_io_group(io_group, controller_config)

    update_now: bool = False
    config = utility.get_from_json(RUN.config["default_asic_config_paths_file_"], io_group)
    if update_default or config is None:
        config_path = config_loader.write_config_to_file(controller, config_path)
        update_now = True

    default_config: Path
    if update_now:
        _ = utility.update_json(
            RUN.config["default_asic_config_paths_file_"], io_group, config_path
        )
        default_config = Path(config_path)
    else:
        default_config = Path(
            utility.get_from_json(RUN.config["default_asic_config_paths_file_"], io_group)
        )
    _ = utility.update_json(RUN.config["asic_config_paths_file_"], io_group, default_config)
    return default_config, network_keys


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
    config_path: Path | None,
    pid_logged: bool,
    update_default: bool,
):
    """
    Network the LArPix chips from the given controller and PACMAN configurations.
    """
    with open(pacman_config, "r", encoding="utf-8") as f:
        pacman_configs: dict[str, Any] = json.load(f)

    with open(controller_config, "r", encoding="utf-8") as f:
        controller_configs: dict[str, Any] = json.load(f)

    controller: larpix.Controller = larpix.Controller()
    controller.io = larpix.io.PACMAN_IO(relaxed=True, config_filepath=pacman_config, asic_version=3)

    # for each io_group, perform networking
    all_network_keys: list[list[larpix.Key]] = []
    for io_group, _ in pacman_configs["io_group"]:
        default_config, new_network_keys = network_by_io_group(
            io_group, controller_configs[str(io_group)], config_path, update_default, verbose
        )
        all_network_keys += new_network_keys
        config_loader.load_config_from_directory(controller, default_config)
        pacman.enable_pacman_uart_from_io_channel(
            controller.io, io_group, list({chip.io_channel for chip in controller.chips})
        )

    logger.info("starting networking: io_groups=%s", pacman_configs["io_group"])
    pos: int = 0

    tag = "networking..."
    if pid_logged:
        pid: int = os.getpid()
        tag = utility.get_from_process_log(pid)
        pos = enforce_parallel.tag_to_config_map[tag]

    ok, diff, _ = enforce_iterative(
        controller, all_network_keys, controller_configs, pbar_desc=tag, pbar_position=pos
    )
    if not ok:
        raise RuntimeError("Unconfigured chips!", diff)

    if pid_logged:
        print(f"\n{tag} networked successfully")

    logger.info("completed networking: io_groups=%s", pacman_configs["io_group"])


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
