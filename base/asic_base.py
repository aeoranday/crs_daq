# from memory_profiler import profile
import json
import time
from copy import deepcopy

import larpix
import numpy as np

# from timebudget import timebudget
# import asyncio
from base import ana_base, pacman_base, utility_base

# @profile

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


def enable_io(c, io, io_group):
    io.group_packets_by_io_group = True
    io.double_send_packets = True
    pacman_tile = utility_base.all_chip_key_to_tile(c, io_group)
    pacman_base.enable_pacman_uart_from_tile(io, io_group, pacman_tile)
    return


def disable_io(c, io, io_group):
    io.set_reg(0x18, 0, io_group=io_group)
    io.group_packets_by_io_group = False
    io.double_send_packets = False


def toggle_global_dac(c, io, io_group, set_rate, sample_time, initial_global=25):
    enable_io(c, io, io_group)
    for ck in c.chips:
        c[ck].config.threshold_global = initial_global
        c.write_configuration(ck, "threshold_global")

    flag = True
    while flag:
        c.reads = []
        c.multi_read_configuration(c.chips, timeout=sample_time, message="rate check")
        triggers = c.reads[-1].extract("chip_key", "channel_id", packet_type=0)
        count = 0
        for chip_key, channel in set(map(tuple, triggers)):
            if chip_key not in c.chips:
                continue
            rate = triggers.count([chip_key, channel]) / sample_time
            if rate > set_rate:
                if rate > 100 * set_rate:
                    c[chip_key].config.channel_mask[channel] = 0
                    c.write_configuration(chip_key, "channel_mask")
                    print("DISABLE ", chip_key, "  ", channel, "\trate: ", rate, " Hz")
                c[chip_key].config.threshold_global = (
                    c[chip_key].config.threshold_global + 1
                )
                c.write_configuration(chip_key, "threshold_global")
                print(chip_key, " threshold DAC ", c[chip_key].config.threshold_global)
        c.reads = []
        if count == 0:
            flag = False
    c.reads = []
    disable_io(c, io, io_group)
    return


def disable_chip_csa_trigger(c, chip_key):
    c[chip_key].config.csa_enable = [0] * 64
    c.write_configuration(chip_key, "csa_enable")
    c[chip_key].config.channel_mask = [1] * 64
    c.write_configuration(chip_key, "channel_mask")
    return
