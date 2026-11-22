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


ASIC_VERSION: int = 3
DEFAULT_VERBOSE: bool = False
DEFAULT_V_CM_LVDS_TX: int = 5
DEFAULT_TX_DIFF: int = 7
DEFAULT_TX_SLICE: int = 15
DEFAULT_R_TERM: int = 7
DEFAULT_I_RX: int = 0
DEFAULT_RECHECK: bool = False

v2d_10x16_root_ids: list[int] = [21, 61, 101, 151]
v3_10x16_root_ids: list[int] = [151, 111, 61, 21]


def network_larpix_tile(
    tile: int, io_group: int, controller: larpix.Controller, verbose: bool, **kwargs
) -> None:
    """
    Network the LArPix tile using the given controller.

    Parameters
    ----------
    tile : int
        The tile ID number to use.
    io_group : int
        The IO group number of the tile.
    controller : larpix.Controller
        The LArPix controller that controls the tile.
    verbose : bool
        Flag to print steps.
    """
    root_keys: list[larpix.Key] = []
    io_channels: list[int] = utility.tile_to_io_channel([tile])
    for io_channel in io_channels:
        channel_id: int = v3_10x16_root_ids[(io_channel - 1) % 4]
        if channel_id in RUN.config["iog_exclude"][io_group][str(tile)]:
            continue
        network_FSD_v3.network_ext_node_from_tuple(
            controller, io_group, io_channel, channel_id
        )
        candidate_root: larpix.Key | None = network_FSD_v3.setup_root(
            controller,
            controller.io,
            io_group,
            io_channel,
            channel_id,
            verbose,
            ASIC_VERSION,
            kwargs["v_cm_lvds_tx"],
            kwargs["tx_diff"],
            kwargs["tx_slice"],
            kwargs["r_term"],
            kwargs["i_rx"],
        )
        if candidate_root is not None:
            root_keys.append(candidate_root)

    if verbose:
        print(f"\n\nTile {tile} ROOT KEYS: ", root_keys)

    iog_tile_to_root_keys: dict[tuple[int, int], list[larpix.Key]] = (
        utility.partition_chip_keys_by_io_group_tile(root_keys)
    )

    for (iog, _), tile_root_keys in iog_tile_to_root_keys.items():
        network_FSD_v3.initial_network(
            controller,
            controller.io,
            iog,
            tile_root_keys,
            verbose,
            ASIC_VERSION,
            kwargs["v_cm_lvds_tx"],
            kwargs["tx_diff"],
            kwargs["tx_slice"],
            kwargs["r_term"],
            kwargs["i_rx"],
            exclude=RUN.config["iog_exclude"][io_group],
            exclude_links=RUN.config["iog_exclude_links"][io_group],
        )

    unconfigured: list[tuple[larpix.Key, int]] = network_FSD_v3.iterate_waitlist(
        controller,
        controller.io,
        io_group,
        utility.tile_to_io_channel([tile]),
        verbose,
        ASIC_VERSION,
        kwargs["v_cm_lvds_tx"],
        kwargs["tx_diff"],
        kwargs["tx_slice"],
        kwargs["r_term"],
        kwargs["i_rx"],
        exclude=RUN.config["iog_exclude"][io_group],
        exclude_links=RUN.config["iog_exclude_links"][io_group],
    )

    network_file: str = network_FSD_v3.write_network_to_file(
        controller,
        f"iog_{io_group}-tile_{tile}",
        {io_group: [tile]},
        unconfigured,
        asic_version=ASIC_VERSION,
    )

    plot_hydra_network_10x16.main(network_file, io_group=io_group)


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
    **kwargs,
):
    """
    Create the hydra chip network configuration JSON.
    """
    if (asic_version := RUN.config["io_group_asic_version_"][io_group]) != ASIC_VERSION:
        raise RuntimeError(
            f"Unsupported ASIC version. Got {asic_version}."
            f"Requires version {ASIC_VERSION}."
        )

    start = time.time()

    controller: larpix.Controller = larpix.Controller()
    controller.io = larpix.io.PACMAN_IO(
        config_filepath=pacman_config, relaxed=True, asic_version=ASIC_VERSION
    )
    controller.io.reset_tiles([pacman_tile], length=4096 * 4, io_group=io_group)  # 2048
    time.sleep(4096 * 4 * 1e-6)

    if verbose:
        print(f"Working on {io_group=}")

    tiles: list[int]
    if pacman_tile == -1:
        tiles = RUN.config["io_group_pacman_tile_"][io_group]
    else:
        tiles = [pacman_tile]

    for tile in tiles:
        network_larpix_tile(tile, io_group, controller, verbose, **kwargs)
    end = time.time()
    if verbose:
        print("Time elapsed: ", end - start, " s.")
    return controller, controller.io


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
