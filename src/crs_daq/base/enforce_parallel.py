import logging
from copy import deepcopy

import larpix
import numpy as np
from tqdm import tqdm

from crs_daq.base import utility

logger: logging.Logger = logging.getLogger(__name__)
tag_to_config_map: dict[str | None, int] = {"MOD1": 0, "MOD2": 1, "MOD3": 2, "MOD4": 3, None: 0}


def get_chips_by_io_group_io_channel(
    network_config: str,
    tiles: list[int] | None = None,
    use_keys: list[larpix.Key] | None = None,
) -> list[list[larpix.Key]]:
    """
    Get a list of chip Keys categorized by the IO group and IO channel numbers.

    Parameters
    ----------
    network_config : str
        The network configuration path to be loaded and parsed for connections.
    tiles : list[int] | None, default: None
        When given, used to check that an IO channel number is within the list of tiles.
    use_keys : list[larpix.Key] | None, default: None
        When given, used as a list of Keys that are already in use. These keys are then removed
        from the list of keys to consider.

    Returns
    -------
    list[list[larpix.Key]]
        Each element has chip Keys that belong to the same IO group and IO channel.
    """

    dc: larpix.Controller = larpix.Controller()
    dc.load(network_config)
    all_keys: list[list[larpix.Key]] = []
    for io_group, io_channels in dc.network.items():
        for io_channel in io_channels:
            if tiles is not None:
                if utility.io_channel_to_tile(io_channel) not in tiles:
                    continue
            keys: list[larpix.Key] = dc.get_network_keys(
                io_group, io_channel, root_first_traversal=True
            )

            if use_keys is not None:
                remove: list[larpix.Key] = []
                for key in keys:
                    if key not in use_keys:
                        remove.append(key)
                for key in remove:
                    keys.remove(key)

            all_keys.append(keys)

    return all_keys


def enforce_parallel(
    controller: larpix.Controller,
    network_keys: list[list[larpix.Key]],
    unmask_last: bool = True,
    pbar_desc: str = "p",
    pbar_position: int = 0,
) -> tuple[bool, dict[larpix.Key, dict[int, tuple[int, int]]], list[list[larpix.Key]]]:
    """
    Enforce chip configuration in batches.

    Parameters
    ----------
    controller : larpix.Controller
        The LArPix Controller used to enforce the configuration application.
    network_keys : list[list[larpix.Key]]
        A list of lists of larpix Keys to be configured. Keys are batched according to the inner
        list index, e.g., network_keys[i][k] and network_keys[i + 1][k] are configured together.
    unmask_last : bool, default: True
        Mask all chip Keys and unmask the last batch of chip Keys.
    pbar_desc: str, default: "p"
        Not used.
    pbar_position: int, default: 0
        Not used.

    Returns
    -------
    tuple[bool, dict[larpix.Key, dict[int, tuple[int, int]]], list[list[larpix.Key]]]
        The OK state and differences dict from larpix.Controller.enforce_configuration and the
        remainder of `network_keys` that was not configured.

    See Also
    --------
    larpix.controller.Controller.enforce_configuration : Used to apply the configuration for the
    given Keys.
    """
    ichip: int = -1

    chips: list[larpix.Key] = [
        network_keys[net][inet]
        for net in range(len(network_keys))
        for inet in range(len(network_keys[net]))
    ]

    nchip: int = sum([len(net) for net in network_keys])
    p_bar: tqdm = tqdm(range(nchip))
    p_bar.refresh()
    ok, diff = False, {}
    masks: dict[larpix.Key, list[int]] = {}
    csas: dict[larpix.Key, list[int | bool]] = {}
    ptmasks: dict[larpix.Key, list[int]] = {}

    unconfigured: list[list[larpix.Key]] = deepcopy(network_keys)

    while True:
        current_chips: list[larpix.Key] = []
        ichip += 1
        working: bool = False
        for inet, net in enumerate(network_keys):
            if ichip >= len(net):
                continue
            working = True
            current_chips.append(net[ichip])
            unconfigured[inet].remove(net[ichip])

        if unmask_last:
            for chip in current_chips:
                masks[chip] = controller[chip].config.channel_mask
                controller[chip].config.channel_mask = [1] * 64

                ptmasks[chip] = controller[chip].config.periodic_trigger_mask
                controller[chip].config.periodic_trigger_mask = [1] * 64

                csas[chip] = controller[chip].config.csa_enable
                controller[chip].config.csa_enable = [0] * 64
        if not working:
            break

        ok, diff = controller.enforce_configuration(
            current_chips, timeout=0.1, connection_delay=0.05, n=5, n_verify=3
        )

        if not ok:
            print("Re-configuring: ", diff)
            ok, diff = controller.enforce_configuration(
                diff, timeout=0.2, connection_delay=0.1, n=15, n_verify=3
            )
            if not ok:
                logger.info("could not configure:" + str(diff))
                print("Could not configure: ", diff)
                if len(diff) < 3:
                    ok = True
                    for key in diff:
                        if len(diff[key]) > 2:
                            ok = False
                if not ok:
                    break

        p_bar.update(len(current_chips))
        p_bar.refresh()

    p_bar.close()

    n_write_unmask: int = 10

    send: bool = False
    if unmask_last:
        for chip in reversed(masks):
            controller[chip].config.channel_mask = masks[chip]
            controller[chip].config.csa_enable = csas[chip]
            controller[chip].config.periodic_trigger_mask = ptmasks[chip]
            if send == False:
                if np.any(csas[chip]):
                    send = True
        if send:
            for _ in range(n_write_unmask):
                for chip in controller.chips:
                    if chip.io_group in controller.io._io_group_table:
                        controller.multi_write_configuration(
                            [
                                (
                                    chip,
                                    list(range(131, 139))
                                    + list(range(66, 74))
                                    + list(range(155, 163)),
                                )
                            ]
                        )
    return ok, diff, unconfigured
