import json
# import asyncio
import os
import subprocess
import time

import larpix
import larpix.format.pacman_msg_format as pacman_msg_fmt
import larpix.format.rawhdf5format as rhdf5
import numpy as np

import utils

# metadata dumping and generation for ctrl+c
_dump_and_exit_ = False
_broadcast_disable_nwrite = 3


def get_from_process_log(pid, logfile=".envrc"):
    with open(logfile, "r") as f:
        data = f.read()
    pid = str(pid)
    if pid in data:
        lines = data.split("\n")
        for line in lines:
            if pid in line:
                print(line.split("_PID={}".format(pid))[0])
                return line.split("_PID={}".format(pid))[0]
    else:
        return None

    return None


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


def lock_file(fname):
    split = fname.split("/")
    split[-1] = ".temp_lock_" + split[-1]
    new_name = "/".join(split)
    try:
        os.rename(fname, new_name)
        return new_name
    except:
        return None


def unlock_file(locked_name, fname):
    split = fname.split("/")
    split[-1] = fname
    new_name = "/".join(split)
    try:
        os.rename(locked_name, new_name)
        return True
    except:
        time.sleep(0.1)
        return False


def update_json(file, key, data, meta_field="configs"):
    loaded = False
    locked_name = None
    iretry = 0
    while locked_name is None:
        locked_name = lock_file(file)
        if locked_name is None:
            time.sleep(0.1)
            if iretry > 10:
                print("failing to lock file... try={}".format(iretry))
            iretry += 1

    d = {}
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
        oldfilename = c.io.raw_filename
        while True:

            c.read()
            time.sleep(0.1)
            now = time.time()
            if now - data_rate_start > data_rate_refresh and False:
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
                data_rate_counter = 0
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


def partition_chip_keys_by_io_group_tile(chip_keys):
    io_group_list = []
    for chip in chip_keys:
        if chip.io_group not in io_group_list:
            io_group_list.append(chip.io_group)
    d = {}
    for iog in io_group_list:
        for i in range(1, 11):
            d[(iog, i)] = []
    for key in d:
        for ck in chip_keys:
            if ck.io_group == key[0] and io_channel_to_tile(ck.io_channel) == key[1]:
                d[key].append(ck)
    return d


def tile_to_io_channel(tile):
    io_channel = []
    for t in tile:
        for i in range(1, 5, 1):
            io_channel.append(((t - 1) * 4) + i)
    return io_channel


def unique_to_chip_key(i):
    chip_key = (
        str(unique_to_io_group(i))
        + "-"
        + str(unique_to_io_channel(i))
        + "-"
        + str(unique_to_chip_id(i))
    )
    return chip_key


def io_channel_to_tile(io_channel):
    return int(np.floor((io_channel - 1 - ((io_channel - 1) % 4)) / 4 + 1))


def io_channel_list_to_tile(io_channel):
    io_channel = np.array(io_channel)
    return list(np.array(np.floor((io_channel - 1 - ((io_channel - 1) % 4)) / 4 + 1)))


def unique(io_group, io_channel, chip_id, channel_id):
    return ((io_group * 256 + io_channel) * 256 + chip_id) * 64 + channel_id


def chip_key_to_asic_id(chip_key):
    args = str(chip_key).split("-")
    return "{}-{}-{}".format(args[0], io_channel_to_tile(int(args[1])), args[2])
