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

DEFAULT_VERBOSE: bool = False
SKIP_READBACK: bool = False
# 0x201c
# 1: disable
# 0: enable (default)


@click.command()
@click.option("--verbose", "-v", is_flag=True, default=DEFAULT_VERBOSE)
@click.option(
    "--pacman-config",
    default=Path("configs/io/pacman.json"),
    type=click.Path(readable=True, dir_okay=False, path_type=Path),
    help="Config specifying PACMANs.",
    show_default=True,
)
def main(verbose: bool, pacman_config: Path) -> None:
    """
    Configure PACMANs using the given configuration.
    """
    # number of clock cycles to hold for hard reset of LArPix
    RESET_CYCLES: int = 4096
    pacman_configs: dict[str, Any] = {}
    with open(pacman_config, "r", encoding="utf-8") as f:
        pacman_configs = json.load(f)

    controller: larpix.Controller = larpix.Controller()
    controller.io = larpix.io.PACMAN_IO(relaxed=True, config_filepath=pacman_config)

    # for each io_group, perform networking
    logger.info("starting power up")

    for io_group_ip_pair in pacman_configs["io_group"]:
        io_group: int = io_group_ip_pair[0]
        print(f"Configuring IO Group {io_group}")
        # read pacman information and metadata from RUNENV
        pacman_version: str = RUN.config["iog_pacman_version_"][io_group]
        VDDD_DAC: list[int] = RUN.config["iog_VDDD_DAC"][io_group]
        VDDA_DAC: list[int] = RUN.config["iog_VDDA_DAC"][io_group]

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

        for IO_CHAN in utility.tile_to_io_channel(
            RUN.config["io_group_pacman_tile_"][io_group]
        ):

            uart: int | None = pacman.convert_io_channel_to_uart(IO_CHAN)
            if uart is not None:
                controller.io.set_uart_clock_ratio(uart, 1)
                time.sleep(0.01)

        if verbose:
            print("enabling power")
        # enable pacman power
        controller.io.set_reg(0x00000014, 1, io_group=io_group)

        pacman_version = RUN.config["iog_pacman_version_"][io_group]

        VDDA_REG: int | None = None
        VDDD_REG: int | None = None

        if pacman_version == "v1rev5":
            VDDD_REG = 0x24020
            VDDA_REG = 0x24010
            for PACMAN_TILE in RUN.config["io_group_pacman_tile_"][io_group]:
                if verbose:
                    print(
                        "powering pacman tile:", PACMAN_TILE, "to", VDDD_DAC, VDDA_DAC
                    )
                # set voltage dacs to 0V
                controller.io.set_reg(
                    VDDD_REG + (PACMAN_TILE - 1), 0, io_group=io_group
                )
                controller.io.set_reg(
                    VDDA_REG + (PACMAN_TILE - 1), 0, io_group=io_group
                )
                time.sleep(0.2)

                # set voltage dacs VDDD first
                controller.io.set_reg(
                    VDDD_REG + (PACMAN_TILE - 1),
                    VDDD_DAC[PACMAN_TILE - 1],
                    io_group=io_group,
                )
                controller.io.set_reg(
                    VDDA_REG + (PACMAN_TILE - 1),
                    VDDA_DAC[PACMAN_TILE - 1],
                    io_group=io_group,
                )

        if verbose:
            print("reset larpix for n cycles", RESET_CYCLES)
        #   - set reset cycles

        controller.io.set_reg(0x1014, RESET_CYCLES, io_group=io_group)
        #   - toggle reset bit

        clk_ctrl: int = controller.io.get_reg(0x1010, io_group=io_group)
        controller.io.set_reg(0x1010, clk_ctrl | 4, io_group=io_group)
        controller.io.set_reg(0x1010, clk_ctrl, io_group=io_group)

        # enable tile power
        tile_enable_sum: int = 0
        tile_enable_val: int = 0
        for PACMAN_TILE in RUN.config["io_group_pacman_tile_"][io_group]:
            tile_enable_sum = +tile_enable_sum  # FIXME AEO: This is always 0.
            tile_enable_val = controller.io.get_reg(
                0x00000010, io_group=io_group
            ) + pow(2, PACMAN_TILE - 1)
            controller.io.set_reg(0x00000010, tile_enable_val, io_group)
            time.sleep(0.1)
            if verbose:
                print(f"enabling tilereg 0x10: {tile_enable_val:b}")

        if RUN.config["io_group_asic_version_"][io_group] == "2b":
            if verbose:
                print(f"Inverting PACMAN UARTs on {io_group=}")
            pacman.invert_pacman_uart(
                controller.io,
                io_group,
                RUN.config["io_group_asic_version_"][io_group],
                RUN.config["io_group_pacman_tile_"][io_group],
            )

        if not SKIP_READBACK:
            _ = pacman.power_readback(
                controller.io,
                io_group,
                pacman_version,
                RUN.config["io_group_pacman_tile_"][io_group],
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

    logger.info("completed")


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
