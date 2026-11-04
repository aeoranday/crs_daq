# Adapted from: https://github.com/larpix/larpix-10x10-scripts/blob/main/plot_hydra_network_v2a.py

import argparse
import json
import logging
from collections import defaultdict
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import yaml
from matplotlib.patches import Rectangle

logger: logging.Logger = logging.getLogger("plotting_logger")

_default_controller_config: str | None = None
_default_io_group: int = 1
_default_geometry_yaml: str = "analysis/layout-3.0.0.yaml"


colors: list[str] = ["c", "m", "y", "g"]


def parse_hydra_network(network_json: str, iog: int) -> tuple[dict[str, list[int]],
                                                              list[int],
                                                              dict[str, list[str]]
                                                              ]:
    chip_id_uart: defaultdict[str, list[int]] = defaultdict(list)
    root_chips: list[int] = []
    ioc_to_chip_ids: dict[str, list[str]] = {}

    with open(network_json, "r") as f:
        data: dict[str, Any] = json.load(f)

    mapping: list[int] = data["network"]["miso_us_uart_map"]
    hydra: dict[str, Any] = data["network"][str(iog)]

    for ioc in hydra:
        ioc_to_chip_ids[ioc]: list = []
        for node in hydra[ioc]["nodes"]:
            if node["chip_id"] != "ext" and (
                int(node["chip_id"]) < 11 or int(node["chip_id"]) > 170
            ):
                continue

            ioc_to_chip_ids[ioc].append(node["chip_id"])

            if node.get("root", False):
                l: list[int | None] = node["miso_us"]
                for e in l:  # Iterates through all of node["miso_us"]
                    if e is not None:
                        root_chips.append(e)
                        break

            for i in range(len(node["miso_us"])):
                if node["miso_us"][i] is not None:
                    chip_id_uart[node["chip_id"]].append(mapping[i])

    return chip_id_uart, root_chips, ioc_to_chip_ids


def start_end(chipID, uart: int, chipid_pos):
    dX = chipid_pos[chipID]["maxX"] - chipid_pos[chipID]["avgX"]
    dY = chipid_pos[chipID]["maxY"] - chipid_pos[chipID]["avgY"]

    if uart == 1:
        start = (chipid_pos[chipID]["avgX"] + (dX / 2), chipid_pos[chipID]["avgY"])
        end = (dX, 0)
        return start, end
    if uart == 3:
        start = (chipid_pos[chipID]["avgX"] - (dX / 2), chipid_pos[chipID]["avgY"])
        end = (dX * -1, 0)
        return start, end
    if uart == 2:
        start = (chipid_pos[chipID]["avgX"], chipid_pos[chipID]["avgY"] + (dY / 2))
        end = (0, dY)
        return start, end
    if uart == 0:
        start = (chipid_pos[chipID]["avgX"], chipid_pos[chipID]["avgY"] - (dY / 2))
        end = (0, dY * -1)
        return start, end
    return start, end


def chip_to_ioc(chipID, ioc_chip):
    for ioc in ioc_chip:
        if chipID in ioc_chip[str(ioc)]:
            return int(ioc) - 1
    return


def plot_hydra_network(
    geometry_yaml, chipID_uart, missingIO, root_chips, filename, io_group, ioc_chip
):
    with open(geometry_yaml) as fi:
        geo = yaml.full_load(fi)
    chip_pix = dict([(chip_id + 1, pix) for chip_id, pix in geo["chips"]])
    vertical_lines = np.linspace(-1 * (geo["width"] / 2), geo["width"] / 2, 17)
    horizontal_lines = np.linspace(-1 * (geo["height"] / 2), geo["height"] / 2, 11)

    fig, ax = plt.subplots(figsize=(16, 10))
    ax.set_aspect("equal")
    ax.set_xlabel("X Position [mm]")
    ax.set_ylabel("Y Position [mm]")
    ax.set_xticks(vertical_lines)
    ax.set_yticks(horizontal_lines)
    ax.set_xlim(vertical_lines[0] * 1.1, vertical_lines[-1] * 1.1)
    ax.set_ylim(horizontal_lines[0] * 1.1, horizontal_lines[-1] * 1.1)
    for vl in vertical_lines:
        ax.vlines(
            x=vl,
            ymin=horizontal_lines[0],
            ymax=horizontal_lines[-1],
            colors=["k"],
            linestyle="dotted",
        )
    for hl in horizontal_lines:
        ax.hlines(
            y=hl,
            xmin=vertical_lines[0],
            xmax=vertical_lines[-1],
            colors=["k"],
            linestyle="dotted",
        )

    chipid_pos = dict()
    for chipid in chip_pix:
        x, y = [[] for i in range(2)]
        for channelid in range(64):
            x.append(geo["pixels"][chip_pix[chipid][channelid]][1])
            y.append(geo["pixels"][chip_pix[chipid][channelid]][2])
        avgX = (max(x) + min(x)) / 2.0
        avgY = (max(y) + min(y)) / 2.0
        chipid_pos[chipid] = dict(
            minX=min(x), maxX=max(x), avgX=avgX, minY=min(y), maxY=max(y), avgY=avgY
        )
        plt.annotate(str(chipid), [avgX, avgY], ha="center", va="center")

    for chipID in chipID_uart:
        if chipID == "ext":
            continue
        for uart in chipID_uart[chipID]:
            start, end = start_end(int(chipID), uart, chipid_pos)
            plt.arrow(
                start[0],
                start[1],
                end[0],
                end[1],
                width=1.0,
                color=colors[(chip_to_ioc(chipID, ioc_chip) - 1) % 4],
                alpha=0.5,
            )

    for i in range(len(missingIO)):
        chipIDpair = missingIO[i]
        A = chipIDpair[0]
        B = chipIDpair[1]
        if A > B:
            A = chipIDpair[1]
            B = chipIDpair[0]

        r = Rectangle(
            (chipid_pos[A]["maxX"], chipid_pos[A]["minY"]),
            abs(chipid_pos[A]["maxX"] - chipid_pos[B]["minX"]),
            abs(chipid_pos[A]["maxY"] - chipid_pos[A]["minY"]),
            color="r",
            alpha=0.8,
        )

        if abs(A - B) == 10:
            r = Rectangle(
                (chipid_pos[A]["minX"], chipid_pos[A]["minY"]),
                abs(chipid_pos[A]["maxX"] - chipid_pos[A]["minX"]),
                abs(chipid_pos[A]["minY"] - chipid_pos[B]["maxY"]) * -1,
                color="r",
                alpha=0.8,
            )

        plt.gca().add_patch(r)

    for chipID in chipid_pos:
        if chipID not in chipID_uart:
            r = Rectangle(
                (chipid_pos[chipID]["minX"], chipid_pos[chipID]["minY"]),
                abs(chipid_pos[chipID]["maxX"] - chipid_pos[chipID]["minX"]),
                abs(chipid_pos[chipID]["maxY"] - chipid_pos[chipID]["minY"]),
                color="r",
                alpha=0.2,
            )
            plt.gca().add_patch(r)
        if chipID in root_chips:
            r = Rectangle(
                (chipid_pos[chipID]["minX"], chipid_pos[chipID]["minY"]),
                abs(chipid_pos[chipID]["maxX"] - chipid_pos[chipID]["minX"]),
                abs(chipid_pos[chipID]["maxY"] - chipid_pos[chipID]["minY"]),
                color="b",
                alpha=0.2,
            )
            plt.gca().add_patch(r)

    plt.title(filename)
    plt.tight_layout()
    plt.savefig(filename + ".png")
    print("Saved to: ", filename + ".png")


def main(
    controller_config=_default_controller_config,
    geometry_yaml=_default_geometry_yaml,
    io_group=_default_io_group,
    **kwargs
):
    if controller_config is None:
        raise RuntimeError(
            "Hydra network JSON configuration file missing.\n",
            "==> Specify with --controller_config <filename> commandline argument",
        )

    filename = controller_config.split(".")[0]

    chipID_uart, root_chips, ioc_chip = parse_hydra_network(
        controller_config, io_group
    )
    print(ioc_chip)

    plot_hydra_network(
        geometry_yaml, chipID_uart, missingIO, root_chips, filename, io_group, ioc_chip
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--controller_config",
        default=_default_controller_config,
        type=str,
        help="""Hydra network json configuration file""",
    )
    parser.add_argument(
        "--geometry_yaml",
        default=_default_geometry_yaml,
        type=str,
        help="""geometry yaml (layout 2.4.0 for LArPix-v2a 10x10 tile)""",
    )
    parser.add_argument(
        "--io_group", default=_default_io_group, type=int, help="""PACMAN IO group"""
    )
    args = parser.parse_args()
    main(**vars(args))
