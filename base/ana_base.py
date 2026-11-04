import glob
import json

import h5py
import numpy as np

from base import utility_base


def chip_pedestal(adc, unique_id, disable, noise_cut):
    d = disable
    unique_id_set = np.unique(unique_id)

    channel_pedestal = {}
    for i in unique_id_set:
        id_mask = unique_id == i
        masked_adc = adc[id_mask]
        mu = np.mean(masked_adc)
        std = np.std(masked_adc)
        if len(masked_adc) < 2 or std > noise_cut or mu > 200.0 or mu == 0.0:
            ck = utility_base.unique_to_chip_key(i)
            if ck not in d:
                d[ck] = []
            channel = int(utility_base.unique_to_channel_id(i))
            if channel not in d[ck]:
                d[ck].append(channel)
            continue
        channel_pedestal[i] = dict(mu=mu, std=std)

    temp, temp_mu, temp_std = [{} for i in range(3)]
    for i in channel_pedestal:
        ck = utility_base.unique_to_chip_key(i)
        if ck not in temp:
            temp[ck], temp_mu[ck], temp_std[ck] = [[] for i in range(3)]
        temp[ck].append(channel_pedestal[i]["mu"] + channel_pedestal[i]["std"])
        temp_mu[ck].append(channel_pedestal[i]["mu"])
        temp_std[ck].append(channel_pedestal[i]["std"])

    chip_pedestal = {}
    for ck in temp:
        chip_pedestal[ck] = dict(
            metric=np.mean(temp[ck]),
            mu=np.mean(temp_mu[ck]),
            median=np.median(temp_mu[ck]),
            std=np.mean(temp_std[ck]),
        )
    return chip_pedestal, d


def parse_file(filename, packet_type):
    f = h5py.File(filename, "r")
    data_mask = f["packets"][:]["packet_type"] == packet_type
    valid_parity_mask = f["packets"][:]["valid_parity"] == 1
    mask = np.logical_and(data_mask, valid_parity_mask)
    adc = f["packets"]["dataword"][mask]
    unique_id = utility_base.unique_channel_id(f["packets"][mask])
    return adc, unique_id


def metric(adc, unique_id, metric):
    d = {}
    unique_id_set = np.unique(unique_id)
    for i in unique_id_set:
        id_mask = unique_id == i
        masked_adc = adc[id_mask]
        value = 0
        if metric == "mean":
            value = np.mean(masked_adc)
        if metric == "std":
            value = np.std(masked_adc)
        d[i] = value
    return d
