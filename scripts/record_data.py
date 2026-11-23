import os
import warnings
from signal import SIGINT, signal
from pathlib import Path

import click
import larpix
import larpix.io

from crs_daq.base import utility
from crs_daq.runenv import runenv as RUN

warnings.filterwarnings("ignore")


DEFAULT_FILE_COUNT: int = -1
DEFAULT_RUNTIME: int = 300


# FIXME AEO: `ctrlc_handler` should have 2 positional arguments. Ref. signal.signal documentation.
def ctrlc_handler() -> None:
    utility._dump_and_exit_: bool = True
    print("CTRL-C detected. Starting Dump.")


@click.command()
@click.option(
    "--file-count",
    default=DEFAULT_FILE_COUNT,
    type=int,
    help="Number of output files to create, default inf.",
)
@click.option(
    "--runtime",
    default=DEFAULT_RUNTIME,
    type=int,
    help="Runtime duration in seconds.",
    show_default=True,
)
@click.option(
    "--packet",
    is_flag=True,
    help="Generate packet file (default binary).",
)
@click.option(
    "--filename",
    "-f",
    type=click.Path(writable=True, path_type=Path),
    help="Specifiy a file name to save to.",
)
@click.option(
    "--file-tag",
    default=None,
    type=str,
    help="Automatic filename generation including this tag",
)
@click.option(
    "--pacman-config",
    default=Path("configs/io/pacman.json"),
    type=click.Path(readable=True, dir_okay=False, path_type=Path),
    help="Config specifying PACMANs.",
    show_default=True,
)
@click.option("--return-filename", is_flag=True, help="Return last filename.")
@click.option(
    "--record-metadata",
    is_flag=True,
    help="Dump metadata.",
)
@click.option(
    "--run",
    default=-1,
    type=int,
    help="Run number, passed from combined run control.",
)
@click.option(
    "--data-stream",
    default="",
    type=str,
    help="Data stream, passed from combined run control.",
)
def main(
    file_count: int,
    runtime: int,
    packet: bool,
    filename: str,
    file_tag: str,
    pacman_config: str,
    return_filename: bool,
    record_metadata: bool,
    run: int,
    data_stream: str,
) -> str | None:
    """
    Record data until reaching a specified file count or early exit.

    Arguments
    ---------
    file_count : int
        The upper bound for the number of files to generate.
        Data recording can be stopped early with Ctrl-C.
    runtime : int
        The amount of time in seconds to run for.
    message : str
        Unused argument.
    packet : bool
        To generate a packet file or binary file (default).
    filename : str
        The file name to save as.
    file_tag : str
        An additional tag to add to the file name.
    pacman_config : str
        The path to the PACMAN configuration JSON.
    return_filename : bool
        Returns the saved data's filename if True.
    record_metadata : bool
        Record meta data to a JSON file.
    run : int
        This data recording's run number.
    data_stream : str
        Uses the given data stream name as meta data. Used with `record_metadata`.

    Returns
    -------
    str | None
        Returns the recorded data's file name if `return_filename`. Otherwise None.
    """
    if filename is not None and file_count > 1:
        raise RuntimeError("All files will have same filename and will be overwritten")

    # Launch archiving process in the background to copy ASIC configs / detector parameters
    if RUN.config["monitor"]:
        # check if destination_dir_ ends with "/"
        if RUN.config["destination_dir_"].endswith("/"):
            copy_configs_here: str = f"{RUN.config['destination_dir_'][:-1]}.configs"
        else:
            copy_configs_here = f"{RUN.config['destination_dir_']}.configs"

        # check if copy_configs_here directory exists
        if not os.path.exists(copy_configs_here):
            os.mkdir(copy_configs_here)
        os.system(
            f"python scripts/archive.py --ignore_busy --monitor_dir {copy_configs_here} &"
        )

    controller: larpix.Controller = larpix.Controller()
    controller.io = larpix.io.PACMAN_IO(
        relaxed=True, config_filepath=pacman_config, asic_version=3
    )

    # data taking loop
    ctr: int = 0
    while (ctr < file_count or file_count < 0) and not utility._dump_and_exit_:

        # dump ASIC configs to temporary directory to embed in data files
        # note that this archiviving command is called inside the loop, so it will be updated for each file
        # i.e. if changes are made during the run, they will be picked up automatically in the next file
        os.system("./scripts/dump_temp_archive.sh &")

        if filename is None or ctr > 0:
            filename = (
                RUN.config["destination_dir_"]
                + "/"
                + utility.data_filename(controller, packet, file_tag)
            )
        elif ctr == 0:
            filename = RUN.config["destination_dir_"] + "/" + filename

        # set command to archive in case of ctrl+c

        embed_command: str = f"./embed_configs.sh {filename.split('/')[-1]} &"
        dump_command: str = (
            f"./dump_metadata.sh {filename.split('/')[-1]} {run} {data_stream} &"
        )

        utility.data(controller, runtime, packet, False, filename)
        # metadata handling here

        # embed configs in data file
        os.system(embed_command)

        # dump metadata file
        if record_metadata:
            os.system(dump_command)

        ctr += 1

    if return_filename:
        return filename

    return


if __name__ == "__main__":
    signal(SIGINT, ctrlc_handler)
    main()  # pylint: disable=no-value-for-parameter
