import json
# import asyncio
import os
import subprocess
import time
from typing import Any

import larpix
import larpix.format.pacman_msg_format as pacman_msg_fmt
import larpix.format.rawhdf5format as rhdf5
import numpy as np
import numpy.typing as npt

from crs_daq import utils

# metadata dumping and generation for ctrl+c
_dump_and_exit_ = False
_broadcast_disable_nwrite = 3


def get_from_process_log(pid: int, logfile: str =".envrc") -> str | None:
    """
    Get log info based on PID.

    Parameters
    ----------
    pid : int
        The process ID to search with.
    logfile : str
        The file path to open and search in.

    Returns
    -------
    str | None
        The log information or None if the PID is not found.
    """
    with open(logfile, "r") as f:
        data: str = f.read()

    pid_str: str = str(pid)
    if pid_str in data:
        lines: list[str] = data.split("\n")
        for line in lines:
            if pid_str in line:
                print(line.split("_PID={}".format(pid))[0])
                return line.split("_PID={}".format(pid))[0]
    else:
        return None

    return None


def get_from_json(file: str, key: Any, meta_field: str = "configs") -> dict[str, Any] | Any | None:
    """
    Read from a JSON file and get a key's contents.

    Parameters
    ----------
    file : str
        The file path to read. Assumed to be JSON.
    key : Any
        The key to try to access in the JSON. When `key == "all"`, the `meta_field` subsection of the JSON is returned. If there is no `meta_field` in the JSON, then the entire JSON is returned.
    meta_field : str
        A meta field to search under. If `meta_field` is in the JSON, it is used at the primary key and `key` is used as the secondary key.

    Returns
    -------
    dict[str, Any] | Any | None
        None if the `meta_field` and `key` pair are both not in the JSON. Otherwise, the contents of the JSON with the primary access using `meta_field` and secondary access with `key`.
    """
    d: dict[str, Any] = {}
    iretry: int = 0
    loaded: bool = False
    while not loaded:
        iretry += 1
        try:
            with open(file, "r") as f:
                d = json.load(f)
            loaded = True
        except:
            if iretry > 10:
                print("Issue opening file {}".format(file))
                time.sleep(0.1)

    if meta_field not in d:
        if key == "all":
            return d

        if str(key) not in d:
            return None

        return d[str(key)]

    if key == "all":
        return d[meta_field]

    if str(key) not in d[meta_field]:
        return None

    return d[meta_field][str(key)]


def lock_file(fname: str) -> str | None:
    """
    Rename the given file by prepending '.temp_lock_'.

    Parameters
    ----------
    fname : str
        The file name and path to rename.

    Returns
    -------
    str | None
        String of the newly named file or None if not successful.
    """
    split: list[str] = fname.split("/")
    split[-1] = ".temp_lock_" + split[-1]
    new_name: str = "/".join(split)
    try:
        os.rename(fname, new_name)
        return new_name
    except:
        return None


def unlock_file(locked_name: str, fname: str) -> bool:
    """
    Rename the locked file name to `fname`.

    Parameters
    ----------
    locked_name : str
        The file name and path to be renamed.
    fname : str
        The new file name.

    Returns
    -------
    bool
        True if rename was successful. False otherwise.
    """
    split: list[str] = fname.split("/")
    split[-1] = fname
    new_name: str = "/".join(split)
    try:
        os.rename(locked_name, new_name)
        return True
    except:
        time.sleep(0.1)
        return False


def update_json(file: str, key: str, data: Any, meta_field: str ="configs") -> dict[str, Any]:
    """
    Update the given JSON file at [`meta_field`][`key`] with `data`.

    Parameters
    ----------
    file : str
        The path and file name of the JSON to update.
    key : str
    The key to update in the JSON.
    """
    loaded: bool = False
    locked_name: str | None = None
    iretry: int = 0
    while locked_name is None:
        locked_name = lock_file(file)
        if locked_name is None:
            time.sleep(0.1)
            if iretry > 10:
                print("failing to lock file... try={}".format(iretry))
            iretry += 1

    d: dict[str, Any] = {}
    iretry = 0
    while not loaded:
        iretry += 1
        try:
            with open(locked_name, "r") as f:
                d = json.load(f)
            loaded = True
        except:
            time.sleep(0.1)
            if itretry > 10:
                print("Warning: unable to open file {}".format(file))

    if meta_field in d:
        d[meta_field][str(key)] = data
    else:
        d[str(key)] = data

    written = False
    iretry = 0
    while not written:
        iretry += 1
        try:
            with open(locked_name, "w") as f:
                json.dump(d, f, indent=4)
            written = True
        except:
            time.sleep(0.1)
            if itretry > 10:
                print("Warning: unable to update file {}".format(file))

    unlocked = False
    iretry = 0
    while not unlocked:
        unlocked = unlock_file(locked_name, file)
        if not unlocked:
            if iretry > 10:
                print("failing to unlock file... try={}".format(iretry))
            iretry += 1

    return d


def read(c, key, param):
    c.reads = []
    c.read_configuration(key, param, timeout=0.1)
    message = c.reads[-1]
    r, v = -1, -1
    for msg in message:
        if not isinstance(msg, larpix.packet.packet_v2.Packet_v2):
            continue
        if msg.packet_type not in [
            larpix.packet.packet_v2.Packet_v2.CONFIG_READ_PACKET
        ]:
            continue
        print(msg)
        r, v = msg.register_address, msg.register_data
        if msg.chip_id == key.chip_id and r == c[key].config.register_map[param]:
            break
    return r, v


def data_filename(c, packet, tag=None):
    now: str = utils.datetime_now()
    type_str = "binary"
    if packet:
        type_str = "packet"

    if tag is None:
        return "{}-{}.h5".format(type_str, now)

    return "{}-{}-{}.h5".format(type_str, tag, now)


def data(c, runtime, packet, LRS=False, fname=None):
    if packet == True:
        if fname is None:
            fname = "packets-" + now + ".h5"
        c.logger = larpix.logger.HDF5Logger(
            filename=fname, version="3.0"
        )  # LArPix-v3 packet format

        print("filename: ", c.logger.filename)
        c.logger.enable()
        c.run(runtime, " collecting data")
        c.logger.flush()
        c.logger.disable()

        c.reads.clear()

        if LRS:
            subprocess.call(["echo 0 > ~/.adc_watchdog_file"], shell=True)  # stop LRS
            time.sleep(1)

    else:
        c.io.disable_packet_parsing = True
        c.io.enable_raw_file_writing = True
        if fname is None:
            fname = "binary-" + now + ".h5"
        c.io.raw_filename = fname
        c.io.join()
        rhdf5.to_rawfile(
            filename=c.io.raw_filename, io_version=pacman_msg_fmt.latest_version
        )

        print("filename: ", c.io.raw_filename)
        run_start = time.time()
        c.start_listening()
        if LRS:
            subprocess.call(["echo 1 > ~/.adc_watchdog_file"], shell=True)  # start LRS
            print("starting LRS ...")
        data_rate_refresh = 5.0
        data_rate_start = time.time()
        last_counter = 0
        while True:

            c.read()
            time.sleep(0.1)
            now = time.time()
            if now - data_rate_start > data_rate_refresh and False:  # FIXME AEO: Find out why this is has an `and False`.
                if c.io.raw_filename and os.path.isfile(c.io.raw_filename):
                    counter = rhdf5.len_rawfile(c.io.raw_filename, attempts=0)
                    print(
                        "average message rate: {:0.2f} Hz\r".format(
                            (counter - last_counter) / data_rate_refresh
                        ),
                        end="",
                    )
                    last_counter = counter
                data_rate_start = now
            if now > (run_start + runtime) or _dump_and_exit_:
                break
        c.stop_listening()
        if LRS:
            subprocess.call(["echo 0 > ~/.adc_watchdog_file"], shell=True)  # stop LRS
            time.sleep(0.3)
        c.read()
        c.io.join()

    return fname


def get_from_json(file, key, meta_field="configs"):
    d = {}
    iretry = 0
    loaded = False
    while not loaded:
        iretry += 1
        try:
            with open(file, "r") as f:
                d = json.load(f)
            loaded = True
        except:
            if iretry > 10:
                print("Issue opening file {}".format(file))
                time.sleep(0.1)

    if meta_field not in d:
        if key == "all":
            return d

        if str(key) not in d:
            return None

        return d[str(key)]

    if key == "all":
        return d[meta_field]

    if str(key) not in d[meta_field]:
        return None

    return d[meta_field][str(key)]


def reconcile_configuration(
    c, chip_keys, verbose, timeout=0.02, connection_delay=0.02, n=2, n_verify=2
):
    if isinstance(chip_keys, (str, larpix.key.Key)):
        chip_keys = [chip_keys]
    chip_key_register_pairs = [
        (chip_key, range(c[chip_key].config.num_registers)) for chip_key in chip_keys
    ]

    return reconcile_registers(
        c,
        chip_key_register_pairs,
        verbose,
        timeout=timeout,
        connection_delay=connection_delay,
        n=n,
        n_verify=n_verify,
    )


def reconcile_registers(
    c,
    chip_key_register_pairs,
    verbose,
    timeout=0.1,
    connection_delay=0.01,
    n=2,
    n_verify=2,
):
    ok, diff = c.enforce_registers(
        chip_key_register_pairs,
        timeout=timeout,
        connection_delay=connection_delay,
        n=n,
        n_verify=n_verify,
    )
    if not ok and verbose:
        print(diff)
    # print(c.reads[-1])
    # if diff != {}:
    #     flag = True
    #     # print(diff)
    #     for a in diff:
    #         if flag == False:
    #             break
    #         for b in diff[a]:
    #             pair = diff[a][b]
    #             if verbose:
    #                 print(a, '\t', n, ':\t', b, '\t', pair)
    #             if pair[1] == None:
    #                 flag = False
    #                 break
    # if not ok:
    #     chip_key_register_pairs = [(chip_key, register)
    #                                for chip_key in diff
    #                                for register in diff[chip_key]]
    #     c.multi_write_configuration(chip_key_register_pairs, write_read=0,
    #                                 connection_delay=connection_delay)
    #     if n != 1:
    #         ok, diff = reconcile_registers(c, chip_key_register_pairs,
    #                                        verbose, timeout=timeout,
    #                                        connection_delay=connection_delay,
    #                                        n=n-1, n_verify=n_verify)
    #     else:
    #         ok, diff = c.enforce_registers(chip_key_register_pairs,
    #                                       timeout=timeout,
    #                                       connection_delay=connection_delay,
    #                                       n=n_verify, n_verify=2)
    return ok, diff


def partition_chip_keys_by_io_group_tile(chip_keys: list[larpix.key.Key]):
    io_group_list = []
    for chip in chip_keys:
        if chip.io_group not in io_group_list:
            io_group_list.append(chip.io_group)
    d: dict[tuple[int, int], list[larpix.Key]] = {}
    for iog in io_group_list:
        for i in range(1, 11):
            d[(iog, i)] = []
    for key in d:
        for ck in chip_keys:
            if ck.io_group == key[0] and io_channel_to_tile(ck.io_channel) == key[1]:
                d[key].append(ck)
    return d


def tile_to_io_channel(tiles: list[int]) -> list[int]:
    io_channel: list[int] = []
    for tile in tiles:
        for i in range(1, 5, 1):
            io_channel.append(((tile - 1) * 4) + i)
    return io_channel


def unique_to_chip_key(uid: int) -> str:
    chip_key: str = (
        str(utils.uid_to_io_group(uid))
        + "-"
        + str(utils.uid_to_io_channel(uid))
        + "-"
        + str(utils.uid_to_chip_id(uid))
    )
    return chip_key


def io_channel_to_tile(io_channel: int) -> int:
    return int(np.floor((io_channel - 1 - ((io_channel - 1) % 4)) / 4 + 1))


def io_channel_list_to_tile(io_channel: list[int]) -> list[int]:
    io_channel: npt.NDArray = np.array(io_channel)
    return list(np.array(np.floor((io_channel - 1 - ((io_channel - 1) % 4)) / 4 + 1)))


def unique(io_group: int, io_channel: int, chip_id: int, channel_id: int) -> int:
    return ((io_group * 256 + io_channel) * 256 + chip_id) * 64 + channel_id


def chip_key_to_asic_id(chip_key: str) -> str:
    args = str(chip_key).split("-")
    tile: int = io_channel_to_tile(int(args[1]))
    return f"{args[0]}-{tile}-{args[2]}"
