import warnings

warnings.filterwarnings("ignore")
import argparse
import json
import logging
import sys
import time
from typing import Any

import larpix
import larpix.io

from crs_daq.base import pacman, utility

logger = logging.getLogger(__name__)

_default_verbose = False
skip_readback = False
# 0x201c
# 1: disable
# 0: enable (default)

from crs_daq.runenv import runenv as RUN

module = sys.modules[__name__]
for var in RUN.config:
    setattr(module, var, getattr(RUN, var))


def main(verbose: bool, pacman_config: str) -> None:

    # number of clock cycles to hold for hard reset of LArPix
    RESET_CYCLES: int = 4096
    pacman_configs: dict[str, Any] = {}
    with open(pacman_config, "r") as f:
        pacman_configs = json.load(f)

    controller: larpix.Controller = larpix.Controller()
    controller.io = larpix.io.PACMAN_IO(relaxed=True, config_filepath=pacman_config)

    # for each io_group, perform networking
    logger.info("starting power up")

    for io_group_ip_pair in pacman_configs["io_group"]:
        io_group: int = io_group_ip_pair[0]
        print("Configuring IO Group {}".format(io_group))
        # read pacman information and metadata from RUNENV
        pacman_version: str = iog_pacman_version_[io_group]
        VDDD_DAC: list[int] = iog_VDDD_DAC[io_group]
        VDDA_DAC: list[int] = iog_VDDA_DAC[io_group]

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

        for IO_CHAN in utility.tile_to_io_channel(io_group_pacman_tile_[io_group]):

            uart: int | None = pacman.convert_io_channel_to_uart(IO_CHAN)
            if uart is not None:
                controller.io.set_uart_clock_ratio(uart, 1)
                time.sleep(0.01)

        if verbose:
            print("enabling power")
        # enable pacman power
        controller.io.set_reg(0x00000014, 1, io_group=io_group)

        pacman_version = iog_pacman_version_[io_group]

        VDDA_REG: int | None = None
        VDDD_REG: int | None = None

        if pacman_version == "v1rev5":
            VDDD_REG = 0x24020
            VDDA_REG = 0x24010
            for PACMAN_TILE in io_group_pacman_tile_[io_group]:
                if verbose:
                    print(
                        "powering pacman tile:", PACMAN_TILE, "to", VDDD_DAC, VDDA_DAC
                    )
                # set voltage dacs to 0V
                controller.io.set_reg(VDDD_REG + (PACMAN_TILE - 1), 0, io_group=io_group)
                controller.io.set_reg(VDDA_REG + (PACMAN_TILE - 1), 0, io_group=io_group)
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
        for PACMAN_TILE in io_group_pacman_tile_[io_group]:
            tile_enable_sum = +tile_enable_sum  # FIXME AEO: This is always 0.
            tile_enable_val = controller.io.get_reg(0x00000010, io_group=io_group) + pow(
                2, PACMAN_TILE - 1
            )
            controller.io.set_reg(0x00000010, tile_enable_val, io_group)
            time.sleep(0.1)
            if verbose:
                print("enabling tilereg 0x10: {0:b}".format(tile_enable_val))

        if io_group_asic_version_[io_group] == "2b":
            if verbose:
                print("Inverting PACMAN UARTs on io_group={}".format(io_group))
            pacman.invert_pacman_uart(
                controller.io,
                io_group,
                io_group_asic_version_[io_group],
                io_group_pacman_tile_[io_group],
            )

        if not skip_readback:
            readback = pacman.power_readback(
                controller.io, io_group, pacman_version, io_group_pacman_tile_[io_group]
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

        utility.update_json(asic_config_paths_file_, io_group, None)
        utility.update_json(network_config_paths_file_, io_group, None)

    logger.info("completed")

    return


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pacman_config",
        default="configs/io/pacman.json",
        type=str,
        help="""Config specifying PACMANs""",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", default=_default_verbose
    )
    args = parser.parse_args()
    main(**vars(args))
