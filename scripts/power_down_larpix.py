#!/usr/bin/env python3
"""
Power down the LArPix using the given PACMAN configuration.
"""
import json
import logging
import warnings
from pathlib import Path
from typing import Any

import click
import larpix
import larpix.io

from crs_daq.base import utility
from crs_daq.runenv import runenv as RUN

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)


DEFAULT_VERBOSE: bool = False


@click.command()
@click.argument(
    "pacman-config",
    required=False,
    default=Path("configs/io/pacman.json"),
    type=click.Path(readable=True, dir_okay=False, path_type=Path),
    help="Config specifying PACMANs.",
)
def main(pacman_config: Path):
    """
    Power down the LArPix using the given PACMAN configuration.
    """
    logging.info("power_down_larpix.py")
    controller: larpix.Controller = larpix.Controller()
    controller.io: larpix.io.PACMAN_IO = larpix.io.PACMAN_IO(
        relaxed=True, config_filepath=pacman_config, asic_version=3
    )

    with open(pacman_config, "r", encoding="utf-8") as f:
        pacman_configs: dict[str, Any] = json.load(f)

    for io_group_ip_pair in pacman_configs["io_group"]:
        io_group: int = io_group_ip_pair[0]

        # disable pacman receivers
        # c.io.set_reg(0x18, 0, io_group=io_group)

        # disable tile power, LARPIX clock
        controller.io.set_reg(0x00000010, 0, io_group=io_group)
        controller.io.set_reg(0x00000014, 0, io_group=io_group)

        utility.update_json(RUN.config["asic_config_paths_file_"], io_group, None)
        utility.update_json(RUN.config["network_config_paths_file_"], io_group, None)
    logger.info("powered down")


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
