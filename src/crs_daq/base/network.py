import json
import time
from typing import Any, Sequence

import larpix
import larpix.io
import numpy as np

from crs_daq.base import asic, uart, utility
from crs_daq.utils import datetime_now

# from timebudget import timebudget
# import asyncio

ref_current_trim: int = 0
i_tx_diff: int = 0
tx_slices: int = 15
r_term: int = 2
i_rx: int = 8

_default_clk_ctrl: int = 1
_uart_phase: int = 2

clk_ctrl_2_clk_ratio_map: dict[int, int] = {0: 10, 1: 20, 2: 40, 3: 80}


# @timebudget
def network_ext_node_from_tuple(
    controller: larpix.Controller, iog_ioc_cid: tuple[int, int, int]
) -> None:
    """
    Add an 'ext' node to the larpix Controller network using a 3-tuple.

    Parameters
    ----------
    controller : larpix.Controller
        Host controller that manages the system.
    iog_ioc_cid : tuple[int, int, int]
        A 3-tuple of (<IO group>, <IO channel>, <chip ID>).
    """
    controller.add_network_node(
        iog_ioc_cid[0], iog_ioc_cid[1], controller.network_names, "ext", root=True
    )
    controller.add_network_link(
        iog_ioc_cid[0], iog_ioc_cid[1], "miso_us", ("ext", iog_ioc_cid[2]), 0
    )
    controller.add_network_link(
        iog_ioc_cid[0], iog_ioc_cid[1], "miso_ds", (iog_ioc_cid[2], "ext"), 0
    )
    controller.add_network_link(
        iog_ioc_cid[0], iog_ioc_cid[1], "mosi", ("ext", iog_ioc_cid[2]), 0
    )
    return


# @timebudget
def configure_chip_id(
    controller: larpix.Controller,
    io_group: int,
    ioc: int,
    chip_id: int,
    asic_version: int | str,
) -> larpix.Key:
    """
    Add the corresponding chip key to the larpix Controller and write the configuration.

    Parameters
    ----------
    controller : larpix.Controller
        Host controller that manages the system.
    io_group : int
        The chip's IO group.
    ioc : int
        The chip's IO channel.
    chip_id : int
        The chip's ID.
    asic_version : int | str
        The asic version number (and revision letter if a string). See larpix.Chip.

    Returns
    -------
    larpix.Key
        The chip key of the configured chip.
    """
    setup_key: larpix.Key = larpix.key.Key(io_group, ioc, 1)
    if setup_key not in controller.chips:
        controller.add_chip(setup_key, version=asic_version)
    controller[setup_key].config.chip_id = chip_id
    controller.write_configuration(setup_key, "chip_id")
    controller.write_configuration(setup_key, "chip_id")
    controller.remove_chip(setup_key)
    chip_key: larpix.Key = larpix.key.Key(io_group, ioc, chip_id)
    if chip_key not in controller.chips:
        controller.add_chip(chip_key, version=asic_version)
    controller[chip_key].config.chip_id = chip_id
    return chip_key


# @timebudget
def configure_root_chip(
    controller: larpix.Controller,
    chip_key: larpix.Key,
    asic_version: int | str,
    ref_current_trim: int,
    tx_diff: int,
    tx_slice: int,
    r_term: int,
    i_rx: int,
) -> None:
    """
    Configure the root chip.

    Parameters
    ----------
    controller : larpix.Controller
        Host controller that manages the system.
    chip_key : larpix.Key
        The chip key used to configure.
    asic_version : int | str
        The ASIC version number of the chip. This function only supports version "2b".
    ref_current_trim : int
        Reference current trim value.
    tx_diff : int
        Transmission difference.
    tx_slice : int
        Transmission slice.
    r_term : int
    i_rx : int
    """
    if asic_version == "2b":
        controller[chip_key].config.ref_current_trim = ref_current_trim
        controller.write_configuration(chip_key, "ref_current_trim")
        registers: list[int] = []
        for uart in range(4):
            setattr(controller[chip_key].config, f"i_rx{uart}", i_rx)
            registers.append(controller[chip_key].config.register_map[f"i_rx{uart}"])
            setattr(controller[chip_key].config, f"r_term{uart}", i_rx)
            registers.append(controller[chip_key].config.register_map[f"r_term{uart}"])
        for reg in registers:
            controller.write_configuration(chip_key, reg)
        for reg in registers:
            controller.write_configuration(chip_key, reg)
        controller[chip_key].config.enable_posi = [0] * 4
        controller[chip_key].config.enable_posi[1] = 1
        controller.write_configuration(chip_key, "enable_posi")
        controller.write_configuration(chip_key, "enable_posi")
        controller[chip_key].config.i_tx_diff0 = tx_diff
        controller.write_configuration(chip_key, "i_tx_diff0")
        controller.write_configuration(chip_key, "i_tx_diff0")
        controller[chip_key].config.tx_slices0 = tx_slice
        controller.write_configuration(chip_key, "tx_slices0")
        controller[chip_key].config.enable_piso_downstream = [0] * 4
        controller[chip_key].config.enable_piso_downstream[0] = 1
        controller.write_configuration(chip_key, "enable_piso_downstream")
        controller[chip_key].config.enable_piso_upstream = [0] * 4
        controller.write_configuration(chip_key, "enable_piso_upstream")

    return


# @timebudget


def setup_root(
    controller: larpix.Controller,
    io: larpix.io.PACMAN_IO,
    io_group: int,
    io_channel: int,
    chip_id: int,
    verbose: bool,
    asic_version: int | str,
    ref_current_trim: int,
    tx_diff: int,
    tx_slice: int,
    r_term: int,
    i_rx: int,
) -> larpix.Key | None:
    """
    Try to configure the root chip.

    If configuration fails, the chip Key is removed from the larpix Controller.

    Parameters
    ----------
    controller : larpix.Controller
        Host controller that manages the system.
    io : larpix.io.PACMAN_IO
        The PACMAN network IO interface.
    io_group : int
        The chip's IO group number.
    io_channel : int
        The chip's IO channel number.
    chip_id : int
        The chip's ID.
    verbose: bool
        Prints configuration state if True.
    asic_version : int | str
        The ASIC version number of the chip. This function only supports version "2b".
    ref_current_trim : int
        Reference current trim value.
    tx_diff : int
        Transmission difference.
    tx_slice : int
        Transmission slice.
    r_term : int
    i_rx : int

    Returns
    -------
    larpix.Key | None
        If successfully configured, the configured chip's Key. Otherwise, None.
    """

    chip_key: larpix.Key = configure_chip_id(
        controller, io_group, io_channel, chip_id, asic_version
    )
    asic.disable_chip_csa_trigger(controller, chip_key)
    configure_root_chip(
        controller,
        chip_key,
        asic_version,
        ref_current_trim,
        tx_diff,
        tx_slice,
        r_term,
        i_rx,
    )

    io.set_reg(0x18, 2 ** (io_channel - 1), io_group=io_group)
    print("reconcile config")
    print(
        chip_key,
        "downstream enabled:",
        controller[chip_key].config.enable_piso_downstream,
    )
    ok, diff = utility.reconcile_configuration(controller, chip_key, verbose)
    if ok:
        if verbose:
            print(chip_key, " configured")
        return chip_key
    if verbose:
        print(chip_key, " NOT configured")
    uart.reset_uarts(controller, chip_key, verbose)
    controller.remove_chip(chip_key)
    return None


# @timebudget
def append_upstream_chip_ids(
    io_channel: int, chip_id: int, waitlist: set[int]
) -> set[int]:
    """
    Create an updated set of chip IDs to add to upstream.

    Parameters
    ----------
    io_channel : int
        The chip's IO channel number.
    chip_id : int
        The chip's ID.
    waitlist : set[int]
        The set of chip IDs still to be added to upstream.

    Returns
    -------
    set[int]
        An updated set of chip IDs.
    """
    addendum: set[int] = waitlist
    if io_channel in list(range(1, 33, 4)):
        for i in range(chip_id, 31):
            addendum.add(i)
            addendum.add(i - 10)
            addendum.add(i + 10)
    if io_channel in list(range(2, 33, 4)):
        for i in range(chip_id, 51):
            addendum.add(i)
            addendum.add(i + 10)
    if io_channel in list(range(3, 33, 4)):
        for i in range(chip_id, 81):
            addendum.add(i)
            addendum.add(i - 10)
    if io_channel in list(range(4, 33, 4)):
        for i in range(chip_id, 101):
            addendum.add(i)
            addendum.add(i - 10)
            addendum.add(i + 10)
    return addendum


# @timebudget
def find_daughter_id(parent_piso: int, parent_chip_id: int) -> int:
    """
    Calculate the daughter ID based on parent info.

    Parameters
    ----------
    parent_piso : int
    parent_chip_id : int
        The parent's chip ID.

    Returns
    -------
    int
        The daughter chip's ID.
    """
    daughter_id: int
    if parent_piso == 3:
        daughter_id = parent_chip_id - 10
    if parent_piso == 1:
        daughter_id = parent_chip_id + 10
    if parent_piso == 2:
        daughter_id = parent_chip_id + 1
    if parent_piso == 0:
        daughter_id = parent_chip_id - 1
    return daughter_id


# @timebudget
def initial_network(
    controller: larpix.Controller,
    io: larpix.io.PACMAN_IO,
    io_group: int,
    root_keys: list[larpix.Key],
    verbose: bool,
    asic_version: int | str,
    ref_current_trim: int,
    tx_diff: int,
    tx_slice: int,
    r_term: int,
    i_rx: int,
) -> None:
    root_ioc: list[int] = [rk.io_channel for rk in root_keys]
    waitlist: set[int] = set()
    cnt_configured, cnt_unconfigured = 0, 0
    firstIteration: bool = True
    for root in root_keys:
        if firstIteration == False:
            print(
                "\n CONFIGURED: ", cnt_configured, "\t UNCONFIGURED: ", cnt_unconfigured
            )

        io.set_reg(0x18, 2 ** (root.io_channel - 1), io_group=io_group)
        ok, diff = utility.reconcile_configuration(controller, root, verbose)
        if ok:
            cnt_configured += 1
        if not ok:
            waitlist = append_upstream_chip_ids(root.io_channel, root.chip_id, waitlist)
            cnt_unconfigured = len(waitlist)
            print("Parent ", root, " failed to configure")
            continue
        print(
            root,
            "\tconfigured: ",
            cnt_configured,
            "\t unconfigured: ",
            cnt_unconfigured,
        )
        io.set_reg(0x18, 0, io_group=io_group)

        bail: bool = False
        last_chip_id: int = root.chip_id
        last_daughter: list[tuple[int, int]] = []
        while last_chip_id <= root.chip_id + 9:
            if bail == True:
                break
            for parent_piso_us in [3, 1, 2]:
                if bail == True:
                    break
                daughter_id = find_daughter_id(parent_piso_us, last_chip_id)
                # UGLY HACK
                if (last_chip_id, daughter_id) not in last_daughter:
                    last_daughter.append((last_chip_id, daughter_id))
                else:
                    bail = True
                if verbose:
                    print(
                        "last chip id: ",
                        last_chip_id,
                        "\tdaughter chip id: ",
                        daughter_id,
                    )

                # UGLY HACK
                #                if last_chip_id==60 and daughter_id in [50,70,61]: bail=True
                #                if last_chip_id==80 and daughter_id in [70,90,81]: bail=True

                if daughter_id < 11 or daughter_id > 110:
                    continue
                cks = []
                for ck in controller.chips:
                    if ck.io_channel in root_ioc:
                        cks.append(ck.chip_id)
                if daughter_id in cks:
                    continue
                parent: larpix.Key = larpix.key.Key(
                    root.io_group, root.io_channel, last_chip_id
                )
                if parent not in controller.chips:
                    continue
                daughter: larpix.Key = larpix.key.Key(
                    root.io_group, root.io_channel, daughter_id
                )

                ok, diff = uart.setup_parent_piso(
                    controller, io, parent, daughter, verbose, tx_diff, tx_slice
                )
                if not ok:
                    print("\t\t==> PARENT PISO US ", parent, "failed to configure")
                    uart.disable_parent_piso_us(
                        controller, parent, daughter, verbose, tx_diff, tx_slice
                    )
                    waitlist = append_upstream_chip_ids(
                        root.io_channel, daughter.chip_id, waitlist
                    )
                    cnt_unconfigured = len(waitlist)
                    print(
                        daughter,
                        "\tconfigured: ",
                        cnt_configured,
                        "\t unconfigured: ",
                        cnt_unconfigured,
                    )
                    bail = True
                    continue

                ok, diff, piso = uart.setup_daughter(
                    controller,
                    io,
                    parent,
                    daughter,
                    verbose,
                    asic_version,
                    ref_current_trim,
                    tx_diff,
                    tx_slice,
                    r_term,
                    i_rx,
                )

                if ok:
                    cnt_configured += 1
                    print(
                        daughter,
                        "\tconfigured: ",
                        cnt_configured,
                        "\t unconfigured: ",
                        cnt_unconfigured,
                    )
                    last_chip_id = daughter.chip_id
                if not ok:
                    print("\t\t==> DAUGHTER ", daughter, "failed to configure")
                    uart.reset_uarts(controller, daughter, verbose)
                    uart.disable_parent_piso_us(
                        controller, parent, daughter, verbose, tx_diff, tx_slice
                    )
                    uart.disable_parent_posi(controller, parent, daughter, verbose)
                    controller.remove_chip(daughter)

                    if parent_piso_us == 2:
                        waitlist = append_upstream_chip_ids(
                            root.io_channel, daughter.chip_id, waitlist
                        )
                        bail = True
                    if parent_piso_us != 2:
                        cnt_unconfigured = len(waitlist)
                        print(
                            daughter,
                            "\tconfigured: ",
                            cnt_configured,
                            "\t unconfigured ",
                            cnt_unconfigured,
                        )
                io.set_reg(0x18, 0, io_group=io_group)
            # last_chip_id=daughter.chip_id
        firstIteration = False
    return


# @timebudget
def find_waitlist(
    controller: larpix.Controller, io_group: int, ioc_range: Sequence[int]
) -> tuple[list[int], dict[int, larpix.Key]]:
    """
    Gather the chips that match the IO group and IO channel range and generate a waitlist for
    missing chips.

    Parameters
    ----------
    controller : larpix.Controller
        The LArPix Controller that is managing the system.
    io_group : int
        The IO group number to search on.
    ioc_range : Sequence[int]
        The IO channels to search over.

    Returns
    -------
    tuple[list[int], dict[int, larpix.Key]]
        A list of chip IDs to be added to the network and mapping from chip IDs to chip Keys that
        are already in the network.
    """
    network: dict[int, larpix.Key] = {}
    waitlist: list[int] = []
    for chip_key in controller.chips:
        if chip_key.io_group != io_group:
            continue
        if chip_key.io_channel not in ioc_range:
            continue
        network[chip_key.chip_id] = chip_key
    for chip_id in range(11, 111):
        if chip_id not in network:
            waitlist.append(chip_id)
    return waitlist, network


# @timebudget
def find_potential_parents(
    chip_id: int,
    network: dict[int, larpix.Key],
    verbose: bool,
) -> list[larpix.Key]:
    """
    Find the potential parent chip Keys from the network.

    Parameters
    ----------
    chip_id : int
        The chip ID to find the parents for.
    network : dict[int, larpix.Key]
        A mapping from chip ID to chip Key.
    verbose : bool
        Not used.

    Returns
    -------
    list[larpix.Key]
        Potential parents to the given chip ID.
    """
    parents: list[larpix.Key] = []
    for i in [10, -10, 1, -1]:
        if chip_id % 10 == 0 and (chip_id + i) % 10 == 1:
            continue
        if (chip_id + i) % 10 == 0 and chip_id % 10 == 1:
            continue
        if chip_id + i in network:
            parents.append(network[chip_id + i])
    return parents


# @timebudget
def iterate_waitlist(
    controller: larpix.Controller,
    io: larpix.io.PACMAN_IO,
    io_group: int,
    io_channels,
    verbose: bool,
    asic_version: int | str,
    ref_current_trim: int,
    tx_diff: int,
    tx_slice: int,
    r_term: int,
    i_rx: int,
) -> list[tuple[larpix.Key, int]]:
    """
    """
    print("\n\n----- Iterating waitlist ----\n")
    flag: bool = True
    while flag == True:
        waitlist, network = find_waitlist(controller, io_group, io_channels)
        n_waitlist: int = len(waitlist)
        outstanding: list[tuple[larpix.Key, int]] = []

        for chip_id in waitlist:
            potential_parents: list[larpix.Key] = find_potential_parents(chip_id, network, verbose)
            for parent in potential_parents:
                daughter: larpix.Key = larpix.key.Key(parent.io_group, parent.io_channel, chip_id)

                ok, diff = uart.setup_parent_piso(
                    controller, io, parent, daughter, verbose, tx_diff, tx_slice
                )
                if not ok:
                    print("\t\t==> PARENT PISO US ", parent, "failed to configure")
                    uart.disable_parent_piso_us(
                        controller, parent, daughter, verbose, tx_diff, tx_slice
                    )
                    io.set_reg(0x18, 0, io_group=io_group)
                    continue

                ok, diff, piso = uart.setup_daughter(
                    controller,
                    io,
                    parent,
                    daughter,
                    verbose,
                    asic_version,
                    ref_current_trim,
                    tx_diff,
                    tx_slice,
                    r_term,
                    i_rx,
                )
                if ok:
                    waitlist.remove(chip_id)
                    print("WAITLIST RESOLVED\t", daughter)
                    break
                if not ok:
                    print("\t\t==> DAUGHTER ", daughter, " failed to configure")
                    uart.reset_uarts(controller, daughter, verbose)
                    uart.disable_parent_piso_us(
                        controller, parent, daughter, verbose, tx_diff, tx_slice
                    )
                    uart.disable_parent_posi(controller, parent, daughter, verbose)
                    controller.remove_chip(daughter)
                    outstanding.append((daughter, piso))
                io.set_reg(0x18, 0, io_group=io_group)

        if n_waitlist == len(waitlist):
            print("\n", len(waitlist), " NON-CONFIGURED chips\n", waitlist, "\n")
            flag = False
        else:
            print("\n\n*****RE-TESTING ", len(waitlist), " CHIPS\n", waitlist)
    return outstanding


# @timebudget
def configure_asic_network_links(controller: larpix.Controller) -> larpix.Controller:
    for chip_key in controller.chips:
        piso_us: list[int] = controller[chip_key].config.enable_piso_upstream
        for uart in range(len(piso_us)):
            if piso_us[uart] != 1:
                continue
            if uart == 3:
                daughter_chip_id = chip_key.chip_id - 10
            if uart == 1:
                daughter_chip_id = chip_key.chip_id + 10
            if uart == 2:
                daughter_chip_id = chip_key.chip_id + 1
            if uart == 0:
                daughter_chip_id = chip_key.chip_id - 1
            controller.add_network_link(
                chip_key.io_group,
                chip_key.io_channel,
                "miso_us",
                (chip_key.chip_id, daughter_chip_id),
                uart,
            )
        piso_ds: list[int] = controller[chip_key].config.enable_piso_downstream
        for uart in range(len(piso_ds)):
            if piso_ds[uart] != 1:
                continue
            if uart == 3:
                daughter_chip_id = chip_key.chip_id - 10
            if uart == 1:
                daughter_chip_id = chip_key.chip_id + 10
            if uart == 2:
                daughter_chip_id = chip_key.chip_id + 1
            if uart == 0:
                daughter_chip_id = chip_key.chip_id - 1
            controller.add_network_link(
                chip_key.io_group,
                chip_key.io_channel,
                "miso_ds",
                (chip_key.chip_id, daughter_chip_id),
                uart,
            )
        posi: list[int] = controller[chip_key].config.enable_posi
        for uart in range(len(posi)):
            if posi[uart] != 1:
                continue
            if uart == 0:
                mother_chip_id = chip_key.chip_id - 10
            if uart == 2:
                mother_chip_id = chip_key.chip_id + 10
            if uart == 3:
                mother_chip_id = chip_key.chip_id + 1
            if uart == 1:
                mother_chip_id = chip_key.chip_id - 1
            controller.add_network_link(
                chip_key.io_group,
                chip_key.io_channel,
                "mosi",
                (chip_key.chip_id, mother_chip_id),
                uart,
            )
    return controller


# @timebudget
def miso_us_chip_id_list(
    chip2chip_pair: tuple[str, str] | tuple[int, int], miso_us: list[Any]
) -> list[Any]:
    if chip2chip_pair[0] == "ext" or chip2chip_pair[1] == "ext":
        miso_us[3] = chip2chip_pair[1]
        return miso_us
    assert type(chip2chip_pair[0]) is int and type(chip2chip_pair[1]) is int
    if chip2chip_pair[1] - chip2chip_pair[0] == 1:
        miso_us[3] = chip2chip_pair[1]  # piso 2
    if chip2chip_pair[1] - chip2chip_pair[0] == -1:
        miso_us[1] = chip2chip_pair[1]  # piso 0
    if chip2chip_pair[1] - chip2chip_pair[0] == -10:
        miso_us[0] = chip2chip_pair[1]  # piso 3
    if chip2chip_pair[1] - chip2chip_pair[0] == 10:
        miso_us[2] = chip2chip_pair[1]  # piso 1
    return miso_us


def write_network_to_file(
    controller: larpix.Controller,
    file_prefix: str,
    io_group_pacman_tile,
    unconfigured,
    layout: str ="2.5.1",
    asic_version: str ="2b",
) -> str:

    d: dict[str, Any] = dict()
    d["_config_type"] = "controller"
    d["name"] = file_prefix
    d["asic_version"] = asic_version
    d["layout"] = layout

    controller = configure_asic_network_links(controller)
    d["network"] = {}
    for iog in io_group_pacman_tile:
        if iog not in controller.network:
            continue
        d["network"][iog] = {}
        io_channels = utility.tile_to_io_channel(io_group_pacman_tile[iog])
        for ioc in io_channels:
            d["network"][iog][ioc] = {}
            d["network"][iog][ioc]["nodes"] = []
            for node in list(controller.network[iog][ioc]["miso_us"]):
                temp: dict[str, Any] = {}
                temp["chip_id"] = node
                miso_us: list[Any] = [None] * 4
                for edge in list(controller.network[iog][ioc]["miso_us"].edges()):
                    for chip2chip_pair in controller.network[iog][ioc]["miso_us"].edges(edge):
                        if chip2chip_pair[0] == node:
                            miso_us_chip_id_list(chip2chip_pair, miso_us)
                temp["miso_us"] = miso_us
                if controller.network[iog][ioc]["miso_us"].nodes[node]["root"] == True:
                    temp["root"] = True
                d["network"][iog][ioc]["nodes"].append(temp)
    d["network"]["miso_us_uart_map"] = [3, 0, 1, 2]
    d["network"]["miso_ds_uart_map"] = [1, 2, 3, 0]
    d["network"]["mosi_uart_map"] = [2, 3, 0, 1]

    d["missing"] = {}
    for pair in unconfigured:
        key: larpix.Key = pair[0]
        if key.io_group not in d["missing"]:
            d["missing"][key.io_group] = {}
        if key.io_channel not in d["missing"][key.io_group]:
            d["missing"][key.io_group][key.io_channel] = {}
        if key.chip_id not in d["missing"][key.io_group][key.io_channel]:
            d["missing"][key.io_group][key.io_channel][key.chip_id] = []
        d["missing"][key.io_group][key.io_channel][key.chip_id].append(pair[1])

    now: str = datetime_now()
    fname: str
    if file_prefix != None:
        fname = file_prefix + "-network-" + now + ".json"
    if file_prefix == None:
        fname = "network-" + now + ".json"
    with open(fname, "w") as out:
        json.dump(d, out, indent=4)
    print("network JSON: ", fname)

    return fname


def network_v2b(controller_config: str, verbose: bool = False) -> larpix.Controller:

    controller: larpix.Controller = larpix.Controller()
    controller.io = larpix.io.PACMAN_IO(relaxed=True)

    if controller_config is None:
        raise RuntimeError("No controller config specified!")
    else:
        controller.load(controller_config)

    for io_group, io_channels in controller.network.items():
        if verbose:
            print("resetting io group:", io_group)
        controller.io.reset_larpix(length=2048, io_group=io_group)
        time.sleep(2048 * (1 / (10e6)))
        controller.io.reset_larpix(length=2048, io_group=io_group)
        time.sleep(2048 * (1 / (10e6)))

    # throttle the data rate to insure no FIFO collisions
    controller.io.group_packets_by_io_group = False
    for io_group, io_channels in controller.network.items():
        for io_channel in io_channels:
            controller.init_network(io_group, io_channel, modify_mosi=False)

    # write tx, rx, etc configs
    for chip_key in controller.chips:
        controller[chip_key].config.ref_current_trim = ref_current_trim
        controller.write_configuration(chip_key, "ref_current_trim")
        registers: list[int | str] = []
        for uart in range(4):
            setattr(controller[chip_key].config, f"i_rx{uart}", i_rx)
            registers.append(controller[chip_key].config.register_map[f"i_rx{uart}"])
            setattr(controller[chip_key].config, f"r_term{uart}", i_rx)
            registers.append(controller[chip_key].config.register_map[f"r_term{uart}"])
            setattr(controller[chip_key].config, f"i_tx_diff{uart}", i_tx_diff)
            registers.append(controller[chip_key].config.register_map[f"i_tx_diff{uart}"])
            setattr(controller[chip_key].config, f"tx_slices{uart}", tx_slices)
            registers.append(controller[chip_key].config.register_map[f"tx_slices{uart}"])
        for reg in registers:
            controller.write_configuration(chip_key, reg)
        for reg in registers:
            controller.write_configuration(chip_key, reg)

    # issue soft reset (resets state machines, configuration memory untouched)
    for io_group, io_channels in controller.network.items():
        controller.io.reset_larpix(length=24, io_group=io_group)

    return controller


def network_v2a(controller_config: str, verbose: bool =False):

    controller = larpix.Controller()
    controller.io = larpix.io.PACMAN_IO(relaxed=True)

    if controller_config is None:
        raise RuntimeError("No controller config specified!")
    else:
        controller.load(controller_config)

    for io_group in c.network:
        io_channels = np.array(list(controller.network[io_group])).astype(int)
        tiles = utility.io_channel_list_to_tile(io_channels)

    for io_group, io_channels in controller.network.items():
        if verbose:
            print("resetting io group:", io_group)
        controller.io.reset_larpix(length=2048, io_group=io_group)
        time.sleep(2048 * (1 / (10e6)))
        controller.io.reset_larpix(length=2048, io_group=io_group)
        time.sleep(2048 * (1 / (10e6)))

        for io_channel in io_channels:
            controller.io.set_uart_clock_ratio(
                io_channel, clk_ctrl_2_clk_ratio_map[0], io_group=io_group
            )

    # throttle the data rate to insure no FIFO collisions
    controller.io.group_packets_by_io_group = False
    for io_group, io_channels in controller.network.items():
        for io_channel in io_channels:
            controller.init_network(io_group, io_channel, modify_mosi=False)

    # set uart speed (v2a at 2.5 MHz transmit clock, v2b fine at 5 MHz transmit clock)
    for io_group, io_channels in controller.network.items():
        for io_channel in io_channels:
            chip_keys = controller.get_network_keys(
                io_group, io_channel, root_first_traversal=False
            )
            for chip_key in chip_keys:
                controller[chip_key].config.clk_ctrl = _default_clk_ctrl
                controller.write_configuration(chip_key, "clk_ctrl")

    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            controller.io.set_uart_clock_ratio(
                io_channel,
                clk_ctrl_2_clk_ratio_map[_default_clk_ctrl],
                io_group=io_group,
            )

    # issue soft reset (resets state machines, configuration memory untouched)
    for io_group, io_channels in controller.network.items():
        controller.io.reset_larpix(length=24, io_group=io_group)

    return controller
