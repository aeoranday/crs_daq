"""
Utility functions that may be used anywhere.
"""

import numpy.typing as npt

def datetime_now() -> str:
    """ Return a string with the common datetime format. """
    from time import strftime
    return strftime("%Y_%m_%d_%H_%M_%S_%Z")


def generate_uid_from_fields(array: npt.NDArray) -> int:
    return generate_uid(array["io_group"],
                        array["io_channel"],
                        array["chip_id"],
                        array["channel_id"],
                        )


def generate_uid(io_group: int, io_channel: int, chip_id: int, channel_id: int) -> int:
    return ((io_group * 1000 + io_channel) * 1000 + chip_id) * 100 + channel_id


def uid_to_channel_id(uid: int) -> int:
    return uid % 100


def uid_to_chip_id(uid: int) -> int:
    return (uid // 100) % 1000


def uid_to_io_channel(uid: int) -> int:
    return (uid // 100_000) % 1000


def uid_to_tile_id(uid: int) -> int:
    return (uid_to_io_channel(uid) - 1) // 4 + 1


def uid_to_io_group(uid: int) -> int:
    return (uid // 100_000_000) % 1000
