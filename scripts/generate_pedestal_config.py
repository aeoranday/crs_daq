"""
These settings configure the v3a larpix chips for a pedestal run. Additional configs
are set in /larpix-control/larpix//configs/chip/default_v3.json.
"""
import json
from pathlib import Path
from typing import Any
from warnings import warn

import click
from tqdm import tqdm

from crs_daq.utils import datetime_now


DEFAULT_PERIODIC_TRIGGER_CYCLES: int = 150000
DEFAULT_PERIODIC_RESET_CYCLES: int = 4
DEFAULT_VREF_DAC: int = 220  ###cold 220 ### warm 185
DEFAULT_REF_CURRENT_TRIM: int = 16
DEFAULT_TX_DIFF: int = 8
DEFAULT_TX_SLICE: int = 1
DEFAULT_R_TERM: int = 7
DEFAULT_I_RX: int = 3


def generate_pedestal_config_patch(**kwargs) -> dict[str, Any]:
    """ Generate a minimal pedestal configuration patch. """
    config: dict[str, Any] = {}
    config["adc_comp_trim"] = 2
    config["adc_ibias_delay"] = 7
    config["cds_mode"] = 0
    config["channel_mask"] = [0] * 64
    config["csa_enable"] = [1] * 64
    config["enable_data_stats"] = 0
    config["enable_external_sync"] = 0
    config["enable_external_trigger"] = 0
    config["enable_hit_veto"] = 1
    config["enable_periodic_reset"] = 1
    config["enable_periodic_trigger"] = 1
    config["enable_periodic_trigger_veto"] = 0
    config["enable_rolling_periodic_reset"] = 1
    config["enable_rolling_periodic_trigger"] = 1
    config["enable_tally"] = 1
    config["i_rx0"] = kwargs["i_rx"]
    config["i_rx1"] = kwargs["i_rx"]
    config["i_rx2"] = kwargs["i_rx"]
    config["i_rx3"] = kwargs["i_rx"]
    config["i_tx_diff0"] = kwargs["tx_diff"]
    config["i_tx_diff1"] = kwargs["tx_diff"]
    config["i_tx_diff2"] = kwargs["tx_diff"]
    config["i_tx_diff3"] = kwargs["tx_diff"]
    config["ibias_vcm_buffer"] = 7
    config["mark_first_packet"] = 0
    config["periodic_trigger_mask"] = [0] * 64
    config["r_term0"] = kwargs["r_term"]
    config["r_term1"] = kwargs["r_term"]
    config["r_term2"] = kwargs["r_term"]
    config["r_term3"] = kwargs["r_term"]
    config["threshold_global"] = 255
    config["tx_slices0"] = kwargs["tx_slice"]
    config["tx_slices1"] = kwargs["tx_slice"]
    config["tx_slices2"] = kwargs["tx_slice"]
    config["tx_slices3"] = kwargs["tx_slice"]

    config["vref_dac"] = kwargs["vref_dac"]
    config["periodic_trigger_cycles"] = kwargs["periodic_trigger_cycles"]
    config["periodic_reset_cycles"] = kwargs["periodic_reset_cycles"]
    return config


@click.command()
@click.argument(
        "input_files",
        nargs=-1,
        required=True,
        type=click.Path(dir_okay=False, writable=True, readable=True, path_type=Path),
)
@click.option(
        "--out-dir",
        '-o',
        type=click.Path(writable=True, path_type=Path),
        default=Path("./asic_configs/pedestal_config"),
        show_default=True,
        help="Directory path to output the pedestal configurations.",
)
@click.option(
        "--periodic-trigger-cycles",
        '-t',
        type=int,
        default=DEFAULT_PERIODIC_TRIGGER_CYCLES,
        show_default=True,
        help="How many cycles (100 ns) per trigger.",
)
@click.option(
        "--periodic-reset-cycles",
        '-r',
        type=int,
        default=DEFAULT_PERIODIC_RESET_CYCLES,
        show_default=True,
        help="How many cycles (100 ns) per reset.",
)
@click.option(
        "--vref-dac",
        type=int,
        default=DEFAULT_VREF_DAC,
        show_default=True,
        help="Voltage reference DAC value.",
)
@click.option(
        "--ref-current-trim",
        type=int,
        default=DEFAULT_REF_CURRENT_TRIM,
        show_default=True,
        help="Current reference trim value.",
)
@click.option(
        "--tx-diff",
        type=int,
        default=DEFAULT_TX_DIFF,
        show_default=True,
        help="Transmitter's differential current DAC per slice-loop.",
)
@click.option(
        "--tx-slice",
        type=int,
        default=DEFAULT_TX_SLICE,
        show_default=True,
        help="Number of slices enabled per transmitter DAC.",
)
@click.option(
        "--r-term",
        type=int,
        default=DEFAULT_R_TERM,
        show_default=True,
        help="Receiver's termination DAC.",
)
@click.option(
        "--i-rx",
        type=int,
        default=DEFAULT_I_RX,
        show_default=True,
        help="Receiver's bias current DAC.",
)
def main(
    input_files: list[Path],
    out_dir: Path,
    **kwargs,
):
    """
    Configure the v3a LArPix chips for a pedestal-focused run.
    """
    if out_dir.exists() and out_dir.is_dir():
        for input_file in input_files:
            if (out_dir / input_file.name).exists():
                warn("At least one pedestal config file will be overwritten.")
                break
    elif not out_dir.exists():
        out_dir.mkdir()
        print(f"Made {out_dir!s}")

    patch_config: dict[str, Any] = generate_pedestal_config_patch(**kwargs)

    for file in tqdm(input_files, desc="Config files:"):
        with open(file, "r", encoding="utf-8") as f:
            config: dict[str, Any] = json.load(f)

        config.update(patch_config)
        if "meta" in config:
            config["meta"]["last_update"] = datetime_now()
            config["meta"]["description"] = "pedestal"

        with open(out_dir/file.name, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

    print(f"Pedestal configurations written to:\n\t{out_dir!s}")


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
