"""Write a `value` to the specified `register` name or `remove` the register name."""

import json
import warnings
from pathlib import Path
from typing import Any

import click


#pylint: disable=unused-argument
def _custom_warning_format(message, category, filename, lineno, line=None) -> str:
    return f"{filename}:{lineno}:\n\t{category.__name__}: {message}\n"


warnings.formatwarning = _custom_warning_format


@click.command()
@click.argument(
    "input_files",
    nargs=-1,
    type=click.Path(writable=True, dir_okay=False, path_type=Path),
    help="Files to modify.",
)
@click.option("--register", "-r", type=str, help="Register address name.")
@click.option("--value", "-v", type=int, help="Value to write.")
@click.option("--remove", type=str, help="Address name to remove.")
def main(input_files: list[Path], register: str, value: int, remove: str):
    """Write a `value` to the specified `register` name or `remove` the register name."""
    if (register is None or value is None) and remove is None:
        raise RuntimeError("No register and value pair specified and no remove register specified.")
    if register == remove:
        raise RuntimeError(f"Given {register=} is the same as the {remove=}.")
    for file in input_files:
        with open(file, "r", encoding="utf-8") as f:
            config: dict[str, Any] = json.load(f)
        config[register] = value
        if remove is not None:
            try:
                _ = config.pop(remove)
            except KeyError:
                warnings.warn(f"Config '{str(file)}' doesn't have '{remove}' as a key.")
        with open(file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
