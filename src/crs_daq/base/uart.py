from typing import Any

import larpix
import larpix.io

from crs_daq.base import asic, network_FSD, pacman, uart, utility


def reset_uarts(
    controller: larpix.Controller, chip_key: larpix.Key, verbose: bool
) -> None:
    controller[chip_key].config.enable_piso_downstream = [0] * 4
    controller.write_configuration(chip_key, "enable_piso_downstream")
    if verbose:
        print(chip_key, " PISO DS ", controller[chip_key].config.enable_piso_downstream)
    controller[chip_key].config.enable_piso_upstream = [0] * 4
    controller.write_configuration(chip_key, "enable_piso_upstream")
    if verbose:
        print(chip_key, " PISO US ", controller[chip_key].config.enable_piso_upstream)
    controller[chip_key].config.enable_posi = [1] * 4
    controller.write_configuration(chip_key, "enable_posi")
    if verbose:
        print(chip_key, " POSI ", controller[chip_key].config.enable_posi)
    return


def setup_parent_piso(
    controller: larpix.Controller,
    io: larpix.io.PACMAN_IO,
    parent: larpix.Key,
    daughter: larpix.Key,
    verbose: bool,
    tx_diff: int,
    tx_slice: int,
) -> tuple[bool, dict[larpix.Key, dict[int, tuple[int, int]]]]:
    enable_parent_piso_us(controller, parent, daughter, verbose, tx_diff, tx_slice)
    pacman.enable_pacman_uart_from_io_channel(io, parent.io_group, parent.io_channel)
    # ok, diff = c.enforce_configuration(parent, timeout=0.001, connection_delay=0.005, n=10, n_verify=3)
    ok, diff = utility.reconcile_configuration(
        controller,
        parent,
        verbose,
        timeout=0.02,
        connection_delay=0.01,
        n=3,
        n_verify=2,
    )
    # ok, diff = utility.reconcile_configuration(
    #     controller, parent, verbose)
    # ok, diff = utility.simple_reconcile_configuration(
    #    controller, parent)

    return ok, diff


def setup_daughter(
    controller: larpix.Controller,
    io: larpix.io.PACMAN_IO,
    parent: larpix.Key,
    daughter: larpix.Key,
    verbose: bool,
    asic_version: str | int,
    v_cm_lvds_tx: int,
    tx_diff: int,
    tx_slice: int,
    r_term: int,
    i_rx: int,
) -> tuple[bool, dict[larpix.Key, dict[int, tuple[int, int]]], int]:
    daughter: larpix.Key = network_FSD.configure_chip_id(
        controller, parent.io_group, parent.io_channel, daughter.chip_id, asic_version
    )
    uart.enable_daughter_posi(controller, parent, daughter, verbose, r_term, i_rx)
    piso = uart.enable_daughter_piso(
        controller, parent, daughter, verbose, tx_diff, tx_slice
    )
    asic.disable_chip_csa_trigger(controller, daughter)
    uart.enable_parent_posi(controller, parent, daughter, verbose, r_term, i_rx)
    # print('CHECK')
    # ok, diff = controller.enforce_configuration(daughter, timeout=0.001, connection_delay=0.005, n=10, n_verify=3)
    ok, diff = utility.reconcile_configuration(
        controller,
        daughter,
        verbose,
        timeout=0.02,
        connection_delay=0.01,
        n=3,
        n_verify=2,
    )
    # ok, diff = utility.simple_reconcile_configuration(
    #    controller, daughter)
    # print(diff)
    return ok, diff, piso


def enable_parent_piso_us(
    controller: larpix.Controller,
    parent: larpix.Key,
    daughter: larpix.Key,
    verbose: bool,
    tx_diff: int,
    tx_slice: int,
) -> None:
    """
    Enable the parent chip's PISO upstream.
    """
    piso: int
    if parent.chip_id - daughter.chip_id == 10:
        piso = 3
    if parent.chip_id - daughter.chip_id == -10:
        piso = 1
    if parent.chip_id - daughter.chip_id == -1:
        piso = 0
    if parent.chip_id - daughter.chip_id == 1:
        piso = 2

    if verbose:
        print("PARENT ", parent, "\tDAUGHTER ", daughter, "==>\t enable PISO US ", piso)

    registers_to_write: list[int] = []

    setattr(controller[parent].config, f"i_tx_diff{piso}", tx_diff)
    registers_to_write.append(controller[parent].config.register_map[f"i_tx_diff{piso}"])

    setattr(controller[parent].config, f"tx_slices{piso}", tx_slice)
    registers_to_write.append(controller[parent].config.register_map[f"tx_slices{piso}"])

    for reg in registers_to_write:
        controller.write_configuration(parent, reg)
    controller[parent].config.enable_piso_upstream[piso] = 1
    controller.write_configuration(parent, "enable_piso_upstream")

    if verbose:
        print(controller[parent].config.enable_piso_upstream)

    return


def disable_parent_piso_us(
    controller: larpix.Controller,
    parent: larpix.Key,
    daughter: larpix.Key,
    verbose: bool,
    tx_diff: int,
    tx_slice: int,
):
    piso: int
    if parent.chip_id - daughter.chip_id == 10:
        piso = 3
    if parent.chip_id - daughter.chip_id == -10:
        piso = 1
    if parent.chip_id - daughter.chip_id == -1:
        piso = 0
    if parent.chip_id - daughter.chip_id == 1:
        piso = 2

    if verbose:
        print(
            "PARENT ", parent, "\tDAUGHTER ", daughter, "==>\t disable PISO US ", piso
        )

    controller[parent].config.enable_piso_upstream[piso] = 0
    controller.write_configuration(parent, "enable_piso_upstream")

    if verbose:
        print(controller[parent].config.enable_piso_upstream)

    registers_to_write: list[int] = []

    setattr(controller[parent].config, f"i_tx_diff{piso}", tx_diff)
    registers_to_write.append(
        controller[parent].config.register_map[f"i_tx_diff{piso}"]
    )

    setattr(controller[parent].config, f"tx_slices{piso}", tx_slice)
    registers_to_write.append(
        controller[parent].config.register_map[f"tx_slices{piso}"]
    )

    for reg in registers_to_write:
        controller.write_configuration(parent, reg)

    return


def enable_parent_posi(
    controller: larpix.Controller,
    parent: larpix.Key,
    daughter: larpix.Key,
    verbose: bool,
    r_term: int,
    i_rx: int,
) -> None:
    posi: int
    if parent.chip_id - daughter.chip_id == 10:
        posi = 0
    if parent.chip_id - daughter.chip_id == -10:
        posi = 2
    if parent.chip_id - daughter.chip_id == -1:
        posi = 1
    if parent.chip_id - daughter.chip_id == 1:
        posi = 3

    if verbose:
        print("PARENT ", parent, "\tdaughter ", daughter, "==>\t enable POSI ", posi)

    if verbose:
        print(controller[parent].config.enable_posi)

    registers_to_write: list[int] = []

    setattr(controller[parent].config, f"r_term{posi}", r_term)
    registers_to_write.append(controller[parent].config.register_map[f"r_term{posi}"])

    setattr(controller[parent].config, f"i_rx{posi}", i_rx)
    registers_to_write.append(controller[parent].config.register_map[f"i_rx{posi}"])

    for reg in registers_to_write:
        controller.write_configuration(parent, reg)

    controller[parent].config.enable_posi[posi] = 1
    controller.write_configuration(parent, "enable_posi")

    if verbose:
        print(controller[parent].config.enable_posi)

    return


def enable_daughter_posi(
    controller: larpix.Controller,
    parent: larpix.Key,
    daughter: larpix.Key,
    verbose: bool,
    r_term: int,
    i_rx: int,
) -> None:
    posi: int
    if parent.chip_id - daughter.chip_id == 10:
        posi = 2
    if parent.chip_id - daughter.chip_id == -10:
        posi = 0
    if parent.chip_id - daughter.chip_id == -1:
        posi = 3
    if parent.chip_id - daughter.chip_id == 1:
        posi = 1

    if verbose:
        print("PARENT ", parent, "\tDAUGHTER ", daughter, "==>\t enable POSI ", posi)

    registers_to_write: list[int] = []

    setattr(controller[daughter].config, f"r_term{posi}", r_term)
    registers_to_write.append(controller[daughter].config.register_map[f"r_term{posi}"])

    setattr(controller[daughter].config, f"i_rx{posi}", i_rx)
    registers_to_write.append(controller[daughter].config.register_map[f"i_rx{posi}"])

    for reg in registers_to_write:
        controller.write_configuration(parent, reg)

    controller[daughter].config.enable_posi = [0] * 4
    controller[daughter].config.enable_posi[posi] = 1
    controller.write_configuration(daughter, "enable_posi")

    if verbose:
        print(controller[daughter].config.enable_posi)

    return


def disable_parent_posi(
    controller: larpix.Controller,
    parent: larpix.Key,
    daughter: larpix.Key,
    verbose: bool,
) -> None:
    posi: int
    if parent.chip_id - daughter.chip_id == 10:
        posi = 0
    if parent.chip_id - daughter.chip_id == -10:
        posi = 2
    if parent.chip_id - daughter.chip_id == -1:
        posi = 1
    if parent.chip_id - daughter.chip_id == 1:
        posi = 3

    if verbose:
        print("PARENT ", parent, "\tdaughter ", daughter, "==>\t disable POSI ", posi)

    posi_list: list[int] = controller[parent].config.enable_posi  # !!!!
    if posi_list.count(1) == 1:  # !!!!
        controller[parent].config.enable_posi = [1] * 4  # !!!!
        controller[parent].config.enable_posi[posi] = 0  # !!!!
    else:
        controller[parent].config.enable_posi[posi] = 0

    controller.write_configuration(parent, "enable_posi")

    if verbose:
        print(controller[parent].config.enable_posi)
    return


def enable_daughter_piso(
    controller: larpix.Controller,
    parent: larpix.Key,
    daughter: larpix.Key,
    verbose: bool,
    tx_diff: int,
    tx_slice: int,
) -> int:
    controller[daughter].config.enable_piso_upstream = [0] * 4
    controller.write_configuration(daughter, "enable_piso_upstream")

    piso: int
    if parent.chip_id - daughter.chip_id == 10:
        piso = 1
    if parent.chip_id - daughter.chip_id == -10:
        piso = 3
    if parent.chip_id - daughter.chip_id == -1:
        piso = 2
    if parent.chip_id - daughter.chip_id == 1:
        piso = 0

    if verbose:
        print("parent ", parent, "\tDAUGHTER ", daughter, "==>\t PISO DS ", piso)

    registers_to_write: list[int] = []

    setattr(controller[daughter].config, f"i_tx_diff{piso}", tx_diff)
    registers_to_write.append(
        controller[daughter].config.register_map[f"i_tx_diff{piso}"]
    )

    setattr(controller[daughter].config, f"tx_slices{piso}", tx_slice)
    registers_to_write.append(
        controller[daughter].config.register_map[f"tx_slices{piso}"]
    )

    for reg in registers_to_write:
        controller.write_configuration(parent, reg)

    controller[daughter].config.enable_piso_downstream = [0] * 4
    controller[daughter].config.enable_piso_downstream[piso] = 1
    controller.write_configuration(daughter, "enable_piso_downstream")

    if verbose:
        print(controller[daughter].config.enable_piso_downstream)

    return piso
