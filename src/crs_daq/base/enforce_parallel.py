import logging
from copy import deepcopy

import larpix
import numpy as np
from tqdm import tqdm

from base import utility

logger = logging.getLogger(__name__)
tag_to_config_map = {"MOD1": 0, "MOD2": 1, "MOD3": 2, "MOD4": 3, None: 0}


def get_chips_by_io_group_io_channel(network_config, tiles=None, use_keys=None):

    dc = larpix.Controller()
    dc.load(network_config)
    all_keys = []
    for io_group, io_channels in dc.network.items():
        for io_channel in io_channels:
            if tiles is not None:
                if utility.io_channel_to_tile(io_channel) not in tiles:
                    continue
            keys = dc.get_network_keys(io_group, io_channel, root_first_traversal=True)

            if use_keys is not None:
                remove = []
                for key in keys:
                    if key not in use_keys:
                        remove.append(key)
                for key in remove:
                    keys.remove(key)

            all_keys.append(keys)

    return all_keys


def enforce_parallel(c, network_keys, unmask_last=True, pbar_desc="p", pbar_position=0):

    ichip = -1

    chips = [
        network_keys[net][inet]
        for net in range(len(network_keys))
        for inet in range(len(network_keys[net]))
    ]

    nchip = sum([len(net) for net in network_keys])
    p_bar = tqdm(range(nchip))
    p_bar.refresh()
    ok, diff = False, {}
    masks = {}
    csas = {}
    ptmasks = {}

    unconfigured = deepcopy(network_keys)

    while True:
        current_chips = []
        ichip += 1
        working = False
        for inet, net in enumerate(network_keys):
            if ichip >= len(net):
                continue
            working = True
            current_chips.append(net[ichip])
            unconfigured[inet].remove(net[ichip])

        if unmask_last:
            for chip in current_chips:
                masks[str(chip)] = c[chip].config.channel_mask
                c[chip].config.channel_mask = [1] * 64

                ptmasks[str(chip)] = c[chip].config.periodic_trigger_mask
                c[chip].config.periodic_trigger_mask = [1] * 64

                csas[str(chip)] = c[chip].config.csa_enable
                c[chip].config.csa_enable = [0] * 64
        if not working:
            break

        ok, diff = c.enforce_configuration(
            current_chips, timeout=0.1, connection_delay=0.05, n=5, n_verify=3
        )

        if not ok:
            print("Re-configuring: ", diff)
            ok, diff = c.enforce_configuration(
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

    n_write_unmask = 10

    send = False
    if unmask_last:
        for chip in reversed(masks):
            c[chip].config.channel_mask = masks[chip]
            c[chip].config.csa_enable = csas[chip]
            c[chip].config.periodic_trigger_mask = ptmasks[chip]
            if send == False:
                if np.any(csas[chip]):
                    send = True
        if send:
            for _ in range(n_write_unmask):
                for chip in c.chips:
                    if chip.io_group in c.io._io_group_table:
                        c.multi_write_configuration(
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
