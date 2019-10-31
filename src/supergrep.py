"""Main supergrep script"""

from multiprocessing import Process, Queue, cpu_count, Pipe
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

    job_queue = Queue()
    worker_count = max(1, cpu_count() - 1)
    workers = [SearchWorker(job_queue) for _ in range(worker_count)]
    for worker in workers:
        worker.start()

    pipes = []
    for path in paths:
        parent_conn, child_conn = Pipe()
        pipes.append(parent_conn)
        job_queue.put((path, child_conn))

    for _ in range(worker_count):
        job_queue.put((None, None))

    for pipe in pipes:
        return_value = pipe.recv()
        print("Parent got", return_value)

    for worker in workers:
        worker.join()


class SearchWorker(Process):
    """A work to search files in a separate process"""

    def __init__(self, job_queue):
        self.job_queue = job_queue
        super().__init__()

    def run(self):
        while True:
            job, pipe = self.job_queue.get()
            print(self.name, "got", job)
            if job is None:
                break
            pipe.send(job)
        print(self.name, "Bye!")


if __name__ == "__main__":
    search()
