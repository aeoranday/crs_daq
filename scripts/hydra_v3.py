#!/usr/bin/env python3
"""
Create the hydra chip network configuration JSON.
"""
# TO DO: FIX ISSUE WITH MULTIPLE IO CHANNEL NETWORKS
# RIGHT NOW SECOND IO_CHANNEL CONTROLLER OVERWRITES FIRST


import time
from pathlib import Path

import click
import larpix
import larpix.io

from analysis import plot_hydra_network_10x16
from crs_daq.base import network_FSD_v3, utility
from crs_daq.runenv import runenv as RUN
from crs_daq.utils import datetime_now

DEFAULT_VERBOSE: bool = False
DEFAULT_V_CM_LVDS_TX: int = 5
DEFAULT_TX_DIFF: int = 7
DEFAULT_TX_SLICE: int = 15
DEFAULT_R_TERM: int = 7
DEFAULT_I_RX: int = 0
DEFAULT_RECHECK: bool = False

v2d_10x16_root_ids: list[int] = [21, 61, 101, 151]
v3_10x16_root_ids: list[int] = [151, 111, 61, 21]


@click.command()
@click.option("--io-group", "-g", default=1, type=int, help="IO Group to network on.")
@click.option(
    "--pacman-config",
    default=Path("configs/io/pacman.json"),
    type=click.Path(readable=True, path_type=Path),
    help="Config path for the PACMAN IO.",
    show_default=True,
)
@click.option("--pacman-tile", default=-1, type=int, help="PACMAN tile to work with.")
@click.option(
    "--verbose",
    default=DEFAULT_VERBOSE,
    is_flag=True,
    help="Enable verbose mode.",
)
@click.option(
    "--v-cm-lvds-tx",
    default=DEFAULT_V_CM_LVDS_TX,
    type=int,
    help="Trim DAC for primary reference current.",
    show_default=True,
)
@click.option(
    "--tx-diff",
    default=DEFAULT_TX_DIFF,
    type=int,
    help="Differential per-slice loop current DAC.",
    show_default=True,
)
@click.option(
    "--tx-slice",
    default=DEFAULT_TX_SLICE,
    type=int,
    help="Slices enabled per transmitter DAC.",
    show_default=True,
)
@click.option(
    "--r-term",
    default=DEFAULT_R_TERM,
    type=int,
    help="Receiver termination DAC.",
    show_default=True,
)
@click.option(
    "--i-rx",
    default=DEFAULT_I_RX,
    type=int,
    help="Receiver bias current DAC",
    show_default=True,
)
def main(
    io_group: int,
    pacman_config: Path,
    pacman_tile: int,
    verbose: bool,
    v_cm_lvds_tx: int,
    tx_diff: int,
    tx_slice: int,
    r_term: int,
    i_rx: int,
):
    """
    Create the hydra chip network configuration JSON.
    """
    start = time.time()

    controller: larpix.Controller = larpix.Controller()
    controller.io = larpix.io.PACMAN_IO(config_filepath=pacman_config, relaxed=True, asic_version=3)
    controller.io.reset_tiles([pacman_tile], length=4096 * 4, io_group=io_group)  # 2048
    time.sleep(4096 * 4 * 1e-6)
    controller.io.reset_tiles([pacman_tile], length=4096 * 4, io_group=io_group)  # 2048
    time.sleep(4096 * 4 * 1e-6)

    now: str = datetime_now()  # FIXME AEO: Remove unused variable (stage 2).
    config_name = "controller-config-" + now + ".json"  # FIXME AEO: Remove unused variable.

    for iog in [io_group]:
        print(f"Working on {iog=}")
        if RUN.config["io_group_asic_version_"][iog] == 3:
            tiles: list[int]
            if pacman_tile == -1:
                tiles = RUN.config["io_group_pacman_tile_"][iog]
            else:
                tiles = [pacman_tile]
            for tile in tiles:

                root_keys = []
                io_channels = utility.tile_to_io_channel([tile])
                for io_channel in io_channels:
                    cid = v3_10x16_root_ids[(io_channel - 1) % 4]
                    network_FSD_v3.network_ext_node_from_tuple(controller, iog, io_channel, cid)
                    if cid in RUN.config["iog_exclude"][iog][str(tile)]:
                        continue
                    candidate_root: larpix.Key | None = network_FSD_v3.setup_root(
                        controller,
                        controller.io,
                        iog,
                        io_channel,
                        cid,
                        verbose,
                        RUN.config["io_group_asic_version_"][iog],
                        v_cm_lvds_tx,
                        tx_diff,
                        tx_slice,
                        r_term,
                        i_rx,
                    )
                    if candidate_root is not None:
                        root_keys.append(candidate_root)

                print(f"\n\nTile {tile} ROOT KEYS: ", root_keys)

                iog_tile_to_root_keys = utility.partition_chip_keys_by_io_group_tile(root_keys)

                for iog_tile in iog_tile_to_root_keys:
                    network_FSD_v3.initial_network(
                        controller,
                        controller.io,
                        iog_tile[0],
                        iog_tile_to_root_keys[iog_tile],
                        verbose,
                        RUN.config["io_group_asic_version_"][iog],
                        v_cm_lvds_tx,
                        tx_diff,
                        tx_slice,
                        r_term,
                        i_rx,
                        exclude=RUN.config["iog_exclude"][iog],
                        exclude_links=RUN.config["iog_exclude_links"][iog],
                    )

                unconfigured: list[tuple[larpix.Key, int]] = []
                out_of_network: list[tuple[larpix.Key, int]] = network_FSD_v3.iterate_waitlist(
                    controller,
                    controller.io,
                    iog,
                    utility.tile_to_io_channel([tile]),
                    verbose,
                    RUN.config["io_group_asic_version_"][iog],
                    v_cm_lvds_tx,
                    tx_diff,
                    tx_slice,
                    r_term,
                    i_rx,
                    exclude=RUN.config["iog_exclude"][iog],
                    exclude_links=RUN.config["iog_exclude_links"][iog],
                )
                unconfigured.extend(out_of_network)

                network_file: str = network_FSD_v3.write_network_to_file(
                    controller,
                    f"iog_{io_group}-tile_{tile}",
                    {io_group: [tile]},
                    unconfigured,
                    asic_version=RUN.config["io_group_asic_version_"][iog],
                )

                plot_hydra_network_10x16.main(network_file, io_group=io_group)
            end = time.time()
            if verbose:
                print("Time elapsed: ", end - start, " s.")
            return controller, controller.io  # FIXME AEO: Inconsistent returns.


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
