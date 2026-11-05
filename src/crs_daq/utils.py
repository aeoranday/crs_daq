"""
Utility functions that may be used anywhere.
"""

from time import strftime

import numpy as np
import numpy.typing as npt

from typing import Any

Integer = int | npt.NDArray[np.signedinteger]


def datetime_now() -> str:
    """Return a string with the common datetime format."""
    return strftime("%Y_%m_%d_%H_%M_%S_%Z")


def generate_uid_from_fields(array: npt.NDArray[Any]) -> Integer:
    """
    Generate UID from a NumPy Array.

    See Also
    --------
    generate_uid : Generate UID as parameters.
    """
    return generate_uid(
        array["io_group"].astype(int),
        array["io_channel"].astype(int),
        array["chip_id"].astype(int),
        array["channel_id"].astype(int),
    )


def generate_uid(
    io_group: Integer, io_channel: Integer, chip_id: Integer, channel_id: Integer
) -> Integer:
    """
    Generate the unique identifier using IO group, IO channel, chip ID, and channel ID.

    For example, a UID with value 12345678900 has the following mapping:
         [123][456][789][00]
           |    |    |    |
           |    |    |    channel_id
           |    |    |
           |    |    chip_id
           |    |
    io_group    io_channel

    Parameters
    ----------
    io_group : int
        The IO group number.
    io_channel : int
        The IO channel number.
    chip_id : int
        The chip ID number.
    channel_id : int
        The channel ID number.

    Returns
    -------
    int
        A UID generated from all 4 identifiers.
    """
    return ((io_group * 1000 + io_channel) * 1000 + chip_id) * 100 + channel_id


def uid_to_channel_id(uid: int) -> int:
    """Get the channel ID from the UID."""
    return uid % 100


def uid_to_chip_id(uid: int) -> int:
    """Get the chip ID from the UID."""
    return (uid // 100) % 1000


def uid_to_io_channel(uid: int) -> int:
    """Get the IO channel from the UID."""
    return (uid // 100_000) % 1000


def uid_to_tile_id(uid: int) -> int:
    """Get the tile ID from the UID."""
    return (uid_to_io_channel(uid) - 1) // 4 + 1


def uid_to_io_group(uid: int) -> int:
    """Get the IO group from the UID."""
    return (uid // 100_000_000) % 1000
