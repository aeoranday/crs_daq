### FIX ME:
### (1) change version to pacman version (discriminate from asic version)
### (2) substitute inversion table for hex(0x0201c+0x01000*ioc)
### (3) debug enable_pacman_uart bit declaration
import sys

import larpix.io

from crs_daq.base import utility
from runenv import runenv as RUN

module = sys.modules[__name__]
for var in RUN.config:
    setattr(module, var, getattr(RUN, var))


##########################################################################
# ---------------PACMAN UART INVERSION/DISABLE/ENABLE---------------------#
##########################################################################
# Temporary rev5 firmware
# rx_en register: 0x201c
# 1: disable
# 0: enable (default)


def invert_pacman_uart(
    io: larpix.io.PACMAN_IO, io_group: int, asic_version: int | str, tile: list[int]
) -> None:
    if asic_version != "2b":
        return
    inversion_registers: dict[int, int] = {
        1: 0x0301C,
        2: 0x0401C,
        3: 0x0501C,
        4: 0x0601C,
        5: 0x0701C,
        6: 0x0801C,
        7: 0x0901C,
        8: 0x0A01C,
        9: 0x0B01C,
        10: 0x0C01C,
        11: 0x0D01C,
        12: 0x0E01C,
        13: 0x0F01C,
        14: 0x1001C,
        15: 0x1101C,
        16: 0x1201C,
        17: 0x1301C,
        18: 0x1401C,
        19: 0x1501C,
        20: 0x1601C,
        21: 0x1701C,
        22: 0x1801C,
        23: 0x1901C,
        24: 0x1A01C,
        25: 0x1B01C,
        26: 0x1C01C,
        27: 0x1D01C,
        28: 0x1E01C,
        29: 0x1F01C,
        30: 0x2001C,
        31: 0x2101C,
        32: 0x2201C,
    }
    io_channel: list[int] = utility.tile_to_io_channel(tile)
    for ioc in io_channel:
        io.set_reg(inversion_registers[ioc], 0b11, io_group=io_group)
    return


def convert_io_channel_to_uart(io_channel: int) -> int | None:
    io_channel_to_uart: dict[int, int | None] = {
        1: 1,
        2: 2,
        3: 3,
        4: 4,
        5: 5,
        6: 6,
        7: 7,
        8: 8,
        9: 9,
        10: 10,
        11: 11,
        12: None,
        13: 12,
        14: 13,
        15: 14,
        16: None,
        17: 15,
        18: 16,
        19: 17,
        20: None,
        21: 18,
        22: 19,
        23: 20,
        24: None,
        25: 21,
        26: 22,
        27: 23,
        28: None,
        29: 24,
        30: 25,
        31: 26,
        32: None,
        33: 27,
        34: 28,
        35: 29,
        36: None,
        37: 30,
        38: 31,
        39: 32,
        40: None,
    }
    return io_channel_to_uart[io_channel]


def enable_pacman_uart_from_io_channel(
    io: larpix.io.PACMAN_IO, io_group: int, io_channel: int | list[int]
) -> None:
    bits: list[str] = list("11111111111111111111111111111111")

    uart: None | list[int | None] = None
    if type(io_channel) is int:
        uart = [convert_io_channel_to_uart(io_channel)]

    if type(io_channel) is list:
        uart = [convert_io_channel_to_uart(io_ch) for io_ch in io_channel]

    if uart is None:
        return

    for u in uart:
        if u is None:
            continue
        bits[-1 * u] = "0"
    io.set_reg(0x201C, int("".join(bits), 2), io_group=io_group)
    return


def enable_all_pacman_uart_from_io_group(
    io: larpix.io.PACMAN_IO, io_group: int, true_all: bool = False
) -> None:
    bits: list[str] = list("00000000000000000000000000000000")
    if not true_all:
        enable_pacman_uart_from_tile(io, io_group, io_group_pacman_tile_[io_group])
    else:
        io.set_reg(0x201C, int("".join(bits), 2), io_group=io_group)
    return


def enable_pacman_uart_from_tile(
    io: larpix.io.PACMAN_IO, io_group: int, tile: list[int]
) -> None:
    bits: list[str] = list("11111111111111111111111111111111")
    io_channel: list[int] = utility.tile_to_io_channel(tile)
    for ioc in io_channel:
        uart: int | None = convert_io_channel_to_uart(ioc)
        if uart is None:
            continue
        bits[-1 * uart] = "0"
    io.set_reg(0x201C, int("".join(bits), 2), io_group=io_group)
    return


def disable_all_pacman_uart(io: larpix.io.PACMAN_IO, io_group: int) -> None:
    io.set_reg(0x201C, 0xFFFFFFFF, io_group=io_group)
    return


def set_packet_delay(io: larpix.io.PACMAN_IO, io_group: int, delay: int = 0xFF) -> None:
    for uart in range(32):
        reg: int = 0x03014 + uart * 0x1000
        v: int = (io.get_reg(reg, io_group=io_group) & 0xFF) + (delay << 8)
        io.set_reg(reg, v, io_group=io_group)
    return


##########################################################################
# ---------------------------POWER SET/READBACK---------------------------#
##########################################################################


def power_readback(
    io: larpix.io.PACMAN_IO, io_group: int, pacman_version: str, tile: list[int]
) -> dict[int, list[float]]:
    readback: dict[int, list[float]] = {}
    for i in tile:
        readback[i] = []
        if pacman_version == "v1rev5":
            vdda: int = io.get_reg(0x24030 + (i - 1), io_group=io_group)
            vddd: int = io.get_reg(0x24040 + (i - 1), io_group=io_group)
            idda: int = io.get_reg(0x24050 + (i - 1), io_group=io_group)
            iddd: int = io.get_reg(0x24060 + (i - 1), io_group=io_group)
            print(
                "Tile ",
                i,
                "  VDDA: ",
                vdda,
                " mV  IDDA: ",
                idda / 4,
                " mA  ",
                "VDDD: ",
                vddd,
                " mV  IDDD: ",
                iddd / 4,
                " mA",
            )
            readback[i] = [vdda, idda / 4, vddd, iddd / 4]

        elif pacman_version == "v1rev4":
            vdda = io.get_reg(0x24030 + (i - 1), io_group=io_group)
            vddd = io.get_reg(0x24040 + (i - 1), io_group=io_group)
            idda = io.get_reg(0x24050 + (i - 1), io_group=io_group)
            iddd = io.get_reg(0x24060 + (i - 1), io_group=io_group)
            print(
                "Tile ",
                i,
                "  VDDA: ",
                vdda,
                " mV  IDDA: ",
                int(idda * 0.1),
                " mA  ",
                "VDDD: ",
                vddd,
                " mV  IDDD: ",
                int(iddd >> 12),
                " mA",
            )
            readback[i] = [vdda, idda * 0.1, vddd, iddd >> 12]

        # FIXME AEO: This is always true. Python does not do string comparisons like this.
        elif pacman_version == "v1rev3" or "v1revS1":
            vdda = io.get_reg(0x00024001 + (i - 1) * 32 + 1, io_group=io_group)
            idda = io.get_reg(0x00024001 + (i - 1) * 32, io_group=io_group)
            vddd = io.get_reg(0x00024001 + (i - 1) * 32 + 17, io_group=io_group)
            iddd = io.get_reg(0x00024001 + (i - 1) * 32 + 16, io_group=io_group)
            print(
                "Tile ",
                i,
                "  VDDA: ",
                (((vdda >> 16) >> 3) * 4),
                " mV  IDDA: ",
                (((idda >> 16) - (idda >> 31) * 65535) * 500 * 0.001),
                " mV  VDDD: ",
                (((vddd >> 16) >> 3) * 4),
                " mV  IDDD: ",
                (((iddd >> 16) - (iddd >> 31) * 65535) * 500 * 0.001),
                " mA",
            )
            readback[i] = [
                (((vdda >> 16) >> 3) * 4),
                (((idda >> 16) - (idda >> 31) * 65535) * 500 * 0.001),
                (((vddd >> 16) >> 3) * 4),
                (((iddd >> 16) - (iddd >> 31) * 65535) * 500 * 0.001),
            ]
        else:
            print("WARNING: PACMAN version ", pacman_version, " unknown")
            return readback
    return readback
