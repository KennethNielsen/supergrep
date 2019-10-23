"""Main supergrep script"""

import click


@click.command(
    help="supergrep will grep in plain text parts of plain text files and ..."
)
@click.argument("pattern")
@click.argument("paths", nargs=-1)
@click.option(
    "-a/-A",
    "--all/--not-all",
    "all_files",
    default=False,
    help="Whether to search ALL files including spreadsheets.",
)
@click.option(
    "-r/-R",
    "--recursive/--not-recursive",
    default=False,
    help="Whether to search recursively.",
)
def search(pattern, paths, all_files, recursive):
    """Search `paths` for `pattern`

    Args:
        pattern (str): The patterns to search for
        paths (tuple): A sequence of paths to search
        all_files (bool): Whether to search all files including spreadsheets
        recursive (bool): Whether to search recursively
    """
    print("PATTERN", pattern)
    print("PATHS", paths)
    print("all_files", all_files)
    print("recursive", recursive, end="\n\n")

    for path in paths:
        print(path)


if __name__ == "__main__":
    search()
