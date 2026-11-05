"""
Configuration related functions.

These configuration functions include loading and writing configuration files.
"""
import json
import os
from typing import Any

import larpix

from crs_daq.base import utility
from crs_daq.utils import datetime_now
from crs_daq.runenv import runenv as RUN

asic_config_dir = RUN.asic_config_dir


hydra_registers = [
    "enable_piso_downstream",
    "enable_piso_upstream",
    "enable_posi",
    "enable_miso_downstream",
    "enable_miso_upstream",
    "enable_mosi",
]


def write_config_to_file(
    controller: larpix.Controller,
    path: str | None = None,
    chip_key: str | None = None,
    description: str = "default",
) -> str:
    """
    Write the larpix Controller configuration to file.

    Parameters
    ----------
    controller : larpix.Controller
        The larpix Controller that is managing the system.
    path : str | None
        The path to save the file to. Saves as a json file.
    description : str, default: 'default'
        A description to add to the generated file's metadata.

    Returns
    -------
    str
        The path to the written file.
    """
    now = datetime_now()
    if path is None:
        path = f"{asic_config_dir}/asic_configs_{now}"

    if not os.path.isdir(path):
        os.mkdir(path)

    chips: dict[larpix.Key, larpix.Chip] | list[larpix.Key]
    if chip_key is None:
        chips = controller.chips
    else:
        chips = [larpix.Key(chip_key)]

    for chip in chips:
        full_dict: dict[str, Any] = controller[chip].config.to_dict()
        chip_dict: dict[str, Any] = {
            key: full_dict[key]
            for key in controller[chip].config.get_nondefault_registers()
        }
        chip_dict["meta"] = {}
        chip_dict["meta"]["CHIP_KEY"] = str(chip)
        chip_dict["meta"][
            "ASIC_ID"
        ] = f"{chip.io_group}-{utility.io_channel_to_tile(chip.io_channel)}-{chip.chip_id}"
        chip_dict["meta"]["ASIC_VERSION"] = controller[chip].asic_version
        chip_dict["meta"]["description"] = description
        chip_dict["meta"]["created"] = now
        chip_dict["meta"]["last_update"] = now
        with open(path + f"/config_{str(chip)}.json", "w") as f:
            json.dump(chip_dict, f, indent=4)

    return path


def load_config_from_directory(
    controller: larpix.Controller, directory: str, verbose: bool = False
) -> larpix.Controller:
    """
    Load into controller memory all ASIC configuration JSON Files from directory.

    Parameters
    ----------
    controller : larpix.Controller
        The larpix Controller to load config into.
    directory : str
        The string path to a directory with ASIC JSON configs to load.
    verbose : bool, default: False
        Prints files being loaded.

    Returns
    -------
    larpix.Controller
        The updated larpix Controller with the given configurations.
    """
    for file in os.listdir(directory):
        if verbose:
            print("loading file:", directory + "/" + file)
        if file[-5:] == ".json":
            controller = load_config_from_file(controller, directory + "/" + file)

    return controller


def load_config_from_file(controller: larpix.Controller, config: str) -> larpix.Controller:
    """
    Load into controller memory an ASIC configuration from JSON File.

    Parameters
    ----------
    controller : larpix.Controller
        The larpix Controller to load config into.
    config : str
        The path to the JSON configuration file to read.

    Returns
    -------
    larpix.Controller
        The larpix Controller with the configuration loaded.
    """

    with open(config, "r") as f:
        asic_config: dict[str, Any] = json.load(f)

    chip_key: larpix.Key = larpix.Key(asic_config["meta"]["CHIP_KEY"])
    version: int = asic_config["meta"]["ASIC_VERSION"]
    key_tile: int = utility.io_channel_to_tile(chip_key.io_channel)

    if chip_key not in controller.chips:
        # check other possible io_channels it could correspond to
        io_channels: list[int] = utility.tile_to_io_channel([key_tile])

        for io_ch in io_channels:
            new_key: str = f"{chip_key.io_group}-{io_ch}-{chip_key.chip_id}"
            if new_key in controller.chips:
                chip_key = larpix.Key(new_key)
                break
        else:
            controller.add_chip(chip_key, version=version)

    for key in asic_config:
        if key == "meta":
            continue
        # if key in hydra_registers: continue

        setattr(controller[chip_key].config, key, asic_config[key])

    return controller
