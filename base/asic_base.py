import json
import time
from copy import deepcopy

import larpix
import numpy as np

from base import pacman_base, utility_base

v2a_nonrouted_channels = [6, 7, 8, 9, 22, 23, 24, 25, 38, 39, 40, 54, 55, 56, 57]


def update_chip(c, status):
    chip_register_pairs = []
    for chip_key in status:
        chip_register_pairs.append(
            (chip_key, list(range(64)) + list(range(66, 74)) + list(range(131, 139)))
        )
        c[chip_key].config.pixel_trim_dac = status[chip_key]["pixel_trim"]
        for channel in range(64):
            if (
                status[chip_key]["disable"][channel] == True
                or status[chip_key]["active"][channel] == False
            ):
                c[chip_key].config.csa_enable[channel] = 0
                c[chip_key].config.channel_mask[channel] = 1
    c.multi_write_configuration(chip_register_pairs, connection_delay=0.001)
    return


def disable_chip_csa_trigger(c, chip_key):
    c[chip_key].config.csa_enable = [0] * 64
    c.write_configuration(chip_key, "csa_enable")
    c[chip_key].config.channel_mask = [1] * 64
    c.write_configuration(chip_key, "channel_mask")
    return
