from larpix.controller import Controller

from typing import Any

v2a_nonrouted_channels = [6, 7, 8, 9, 22, 23, 24, 25, 38, 39, 40, 54, 55, 56, 57]


def update_chip(controller: Controller, status: dict[str, Any]):
    """
    Update chips for CSA disabling.

    If a channel is set to be disabled or not active in `status` for a specific, update this for
    `controller` and apply the changes.

    Parameters
    ----------
    controller : larpix.controller.Controller
        The larpix Controller that is managing the system.
    status : dict[str, Any]
        A dict of chip states.
    """
    chip_register_pairs: list[tuple[str, list[int]]] = []
    for chip_key in status:
        chip_register_pairs.append(
            (chip_key, list(range(64)) + list(range(66, 74)) + list(range(131, 139)))
        )
        controller[chip_key].config.pixel_trim_dac = status[chip_key]["pixel_trim"]
        for channel in range(64):
            if (
                status[chip_key]["disable"][channel] == True
                or status[chip_key]["active"][channel] == False
            ):
                controller[chip_key].config.csa_enable[channel] = 0
                controller[chip_key].config.channel_mask[channel] = 1
    controller.multi_write_configuration(chip_register_pairs, connection_delay=0.001)
    return


def disable_chip_csa_trigger(controller: Controller, chip_key: str):
    """
    Disable chip CSA and mask channels.

    Parameters
    ----------
    controller : larpix.controller.Controller
        The larpix Controller that is managing the system.
    chip_key : str
        The chip key to disable and mask.
    """
    controller[chip_key].config.csa_enable = [0] * 64
    controller.write_configuration(chip_key, "csa_enable")
    controller[chip_key].config.channel_mask = [1] * 64
    controller.write_configuration(chip_key, "channel_mask")
    return
