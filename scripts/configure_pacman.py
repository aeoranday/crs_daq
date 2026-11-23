#!/usr/bin/env python3
"""
Configure PACMANs using the given configuration.
"""

import json
import logging
import time
import warnings
from pathlib import Path
from typing import Any

import click
import larpix
import larpix.io

from crs_daq.base import pacman, utility
from crs_daq.runenv import runenv as RUN

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

# number of clock cycles to hold for hard reset of LArPix
RESET_CYCLES: int = 4096
DEFAULT_VERBOSE: bool = False
SKIP_READBACK: bool = False
# 0x201c
# 1: disable
# 0: enable (default)


def apply_pacman_v1rev5_patch(
    controller: larpix.Controller, tiles: list[int], io_group: int, verbose: bool
) -> None:
    """
    Apply register patch for PACMAN v1rev5.

    The PACMAN v1rev5 board has a specific set of registers that also need adjustments.

    Parameters
    ----------
    controller : larpix.Controller
        The LArPix controller used for register getting and setting.
    tiles : list[int]
        Tile numbers to augment.
    io_group : int
        The IO group number to augment.
    verbose : bool
        Prints additional processing info.
    """
    vddd_dac: list[int] = RUN.config["iog_VDDD_DAC"][io_group]
    vdda_dac: list[int] = RUN.config["iog_VDDA_DAC"][io_group]
    vddd_reg: int = 0x24020
    vdda_reg: int = 0x24010
    for pacman_tile in tiles:
        if verbose:
            print("powering pacman tile:", pacman_tile, "to", vddd_dac, vdda_dac)
        # set voltage dacs to 0V
        controller.io.set_reg(vddd_reg + (pacman_tile - 1), 0, io_group=io_group)
        controller.io.set_reg(vdda_reg + (pacman_tile - 1), 0, io_group=io_group)
        time.sleep(0.2)

        # set voltage dacs VDDD first
        controller.io.set_reg(
            vddd_reg + (pacman_tile - 1),
            vddd_dac[pacman_tile - 1],
            io_group=io_group,
        )
        controller.io.set_reg(
            vdda_reg + (pacman_tile - 1),
            vdda_dac[pacman_tile - 1],
            io_group=io_group,
        )


def configure_io_group(
    controller: larpix.Controller, io_group: int, verbose: bool
) -> None:
    """
    Configure the given IO group.

    Parameters
    ----------
    controller : larpix.Controller
        The LArPix controller used for register getting and setting.
    io_group : int
        The IO group number to augment.
    verbose : bool
        Prints additional processing info.
    """
    # read pacman information and metadata from RUNENV
    pacman_version: str = RUN.config["iog_pacman_version_"][io_group]
    tiles: list[int] = RUN.config["io_group_pacman_tile_"][io_group]

    if verbose:
        print("disabling tile power and clock")
    # disable tile power, LARPIX clock
    controller.io.set_reg(0x00000010, 0, io_group=io_group)
    controller.io.set_reg(0x00000014, 0, io_group=io_group)

    if verbose:
        print("setting up mclk")
    # set up mclk in pacman
    controller.io.set_reg(0x101C, 0x4, io_group=io_group)
    time.sleep(0.1)

    for io_chan in utility.tile_to_io_channel(tiles):
        uart: int | None = pacman.convert_io_channel_to_uart(io_chan)
        if uart is not None:
            controller.io.set_uart_clock_ratio(uart, 1)
            time.sleep(0.01)

    if verbose:
        print("enabling power")
    # enable pacman power
    controller.io.set_reg(0x00000014, 1, io_group=io_group)

    if pacman_version == "v1rev5":
        apply_pacman_v1rev5_patch(controller, tiles, io_group, verbose)

    if verbose:
        print("reset larpix for n cycles", RESET_CYCLES)
    #   - set reset cycles

    controller.io.set_reg(0x1014, RESET_CYCLES, io_group=io_group)
    #   - toggle reset bit

    clk_ctrl: int = controller.io.get_reg(0x1010, io_group=io_group)
    controller.io.set_reg(0x1010, clk_ctrl | 4, io_group=io_group)
    controller.io.set_reg(0x1010, clk_ctrl, io_group=io_group)

    # enable tile power
    for pacman_tile in tiles:
        tile_enable_val: int = controller.io.get_reg(
            0x00000010, io_group=io_group
        ) + pow(2, pacman_tile - 1)
        controller.io.set_reg(0x00000010, tile_enable_val, io_group)
        time.sleep(0.1)
        if verbose:
            print(f"enabling tilereg 0x10: {tile_enable_val:b}")

    if (asic_version := RUN.config["io_group_asic_version_"][io_group]) == "2b":
        if verbose:
            print(f"Inverting PACMAN UARTs on {io_group=}")
        pacman.invert_pacman_uart(controller.io, io_group, asic_version, tiles)

    if not SKIP_READBACK:
        _ = pacman.power_readback(
            controller.io,
            io_group,
            pacman_version,
            tiles,
        )
    #   - toggle reset bit
    controller.io.set_reg(0x1014, RESET_CYCLES, io_group=io_group)
    clk_ctrl = controller.io.get_reg(0x1010, io_group=io_group)
    controller.io.set_reg(0x1010, clk_ctrl | 4, io_group=io_group)
    controller.io.set_reg(0x1010, clk_ctrl, io_group=io_group)
    # disable trigger forwarding
    controller.io.set_reg(0x2014, 0xFFFFFFFF, io_group=io_group)
    time.sleep(0.01)
    # Set sync mask
    controller.io.set_reg(0x18, 0x3FF, io_group=io_group)

    pacman.disable_all_pacman_uart(controller.io, io_group)

    pacman.set_packet_delay(controller.io, io_group)

    utility.update_json(RUN.config["asic_config_paths_file_"], io_group, None)
    utility.update_json(RUN.config["network_config_paths_file_"], io_group, None)


@click.command()
@click.option("--verbose", "-v", is_flag=True, default=DEFAULT_VERBOSE)
@click.option(
    "--pacman-config",
    default=Path("configs/io/pacman.json"),
    type=click.Path(readable=True, dir_okay=False, path_type=Path),
    help="Config specifying PACMANs.",
    show_default=True,
)
@click.option(
    "--asic-version",
    default=3,
    type=int,
    help="ASIC version number.",
)
def main(verbose: bool, pacman_config: Path, asic_version: int) -> None:
    """
    Configure PACMANs using the given configuration.
    """
    pacman_configs: dict[str, Any] = {}
    with open(pacman_config, "r", encoding="utf-8") as f:
        pacman_configs = json.load(f)

    controller: larpix.Controller = larpix.Controller()
    controller.io = larpix.io.PACMAN_IO(relaxed=True, config_filepath=pacman_config, asic_version=asic_version)

    # for each io_group, perform networking
    logger.info("starting power up")

    for io_group_ip_pair in pacman_configs["io_group"]:
        io_group: int = io_group_ip_pair[0]
        print(f"Configuring IO Group {io_group}")
        configure_io_group(controller, io_group, verbose)

    logger.info("completed")


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
