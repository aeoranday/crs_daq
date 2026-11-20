#!/usr/bin/env python3
"""
Monitor the power of the PACMAN IO groups 1.
"""
import datetime as dt
import json
import time
import warnings
from pathlib import Path
from typing import Any

import click
import larpix
import larpix.io

from crs_daq.base import pacman


warnings.filterwarnings("ignore")

DEFAULT_VERBOSE = False


@click.command()
@click.option("--verbose", "-v", is_flag=True, default=DEFAULT_VERBOSE)
@click.option(
    "--pacman-config",
    default=Path("configs/io/pacman.json"),
    type=click.Path(readable=True, dir_okay=False, path_type=Path),
    help="Config specifying PACMANs.",
)
def main(verbose: bool, pacman_config: Path):
    """
    Monitor the power for the IO group 1.
    """
    with open(pacman_config, "r", encoding="utf-8") as f:
        pacman_configs: dict[str, Any] = json.load(f)

    controller: larpix.Controller = larpix.Controller()
    controller.io: larpix.io.PACMAN_IO = larpix.io.PACMAN_IO(
        relaxed=True, config_filepath=pacman_config
    )

    if verbose:
        print(pacman_configs)

    # for each io_group, read power
    while True:
        print()
        print(dt.datetime.now())
        for io_group in range(1, 2):
            print(f"Looking at IO Group {io_group}")

            _ = pacman.power_readback(controller.io, io_group, "v1rev5", range(1, 11))
        time.sleep(10)


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
