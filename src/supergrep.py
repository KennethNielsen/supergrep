"""Main supergrep script

This module contain the main supergrep code, to recursive over files,
do the text matching and output results.

"""

import zipfile
import codecs
import logging as LOG
import xml.etree.ElementTree as ET
from subprocess import run, PIPE, check_call, CalledProcessError, DEVNULL
from typing import Optional, List
from multiprocessing import Process, Queue, cpu_count, Pipe

import colorama
from colorama import Fore, Style
import click
import magic
import attr


LOG.basicConfig(level=LOG.ERROR)
colorama.init()


@click.command(
    help="supergrep will grep in plain text parts of plain text files and OpenDocument Text format (odt) files"
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
    LOG.info("Argument PATTERN  : %s", pattern)
    LOG.info("Argument PATHS    : %s", paths)
    LOG.info("Argument all_files: %s", all_files)
    LOG.info("Argument recursive: %s", recursive)

    # Check pdftotext dependency
    try:
        check_call(("which", "pdftotext"), stdout=DEVNULL, stderr=DEVNULL)
    except CalledProcessError:
        raise click.ClickException("supergrep needs the pdftotext command to work")

    job_queue = Queue()
    worker_count = max(1, cpu_count() - 1)
    workers = [SearchWorker(job_queue, pattern) for _ in range(worker_count)]
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
        LOG.debug("Got result: %s", return_value)
        if return_value:
            return_value.print_output("pretty")

    for worker in workers:
        worker.join()


def qn(namespace):
    """Return a odt qualified name"""
    nsmap = {
        "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
        "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    }
    spl = namespace.split(":")
    return "{{{}}}{}".format(nsmap[spl[0]], spl[1])


class SearchWorker(Process):
    """A work to search files in a separate process"""

    def __init__(self, job_queue, search_term):
        self.job_queue = job_queue
        self.search_term = search_term
        super().__init__()

    def run(self):
        while True:
            job, pipe = self.job_queue.get()
            LOG.debug("Worker %s got job: %s", self.name, job)
            if job is None:
                break

            result = self.search(job)
            pipe.send(result)

        LOG.info("Worker %s shutting down. Bye!", self.name)

    def search(self, filepath):
        with magic.Magic(flags=magic.MAGIC_MIME_TYPE) as m:
            filetype = m.id_filename(filepath)
        LOG.debug("Search: '%s' filetype: %s", filepath, filetype)

        if filetype.startswith("text/"):
            return self.search_txt(filetype, filepath)
        elif filetype == "application/pdf":
            return self.search_pdf(filetype, filepath)
        elif filetype == "application/vnd.oasis.opendocument.text":
            return self.search_odt(filetype, filepath)

    def search_txt(self, filetype, filepath):
        """Return search result for a text file"""
        # Lots more to do here for inferring encoding
        with magic.Magic(flags=magic.MAGIC_MIME_ENCODING) as m:
            encoding = m.id_filename(filepath)
        LOG.info("Encoding: %s", encoding)

        results = []
        with codecs.open(filepath, encoding=encoding) as file_:
            for line_no, line in enumerate(file_):
                if self.search_term in line:
                    results.append(SearchResult(filepath, line, line_no=line_no))

        if results:
            return SearchResults(results, self.search_term, rtype="text")
        return None

    def search_pdf(self, filetype, filepath):
        """Return search result for a text file"""
        completed_process = run(["pdftotext", filepath, "-"], stdout=PIPE)
        if completed_process.returncode != 0:
            raise RuntimeError("Something went wrong with pdf parsing")
        pages = completed_process.stdout.decode("utf-8").split("\x0c")

        results = []
        for page_num, page in enumerate(pages, start=1):
            for line in page.split("\n"):
                if self.search_term in line:
                    results.append(
                        SearchResult(filepath, line.strip(), page_no=page_num)
                    )

        if results:
            return SearchResults(results, self.search_term, rtype="pdf")

    def search_odt(self, filetype, filepath):
        """Return search results for an odt file"""
        # Most of the odt parsing including the qn function is
        # shamelessly stolen from
        # https://github.com/deanmalmgren/textract/blob/master/textract/parsers/odt_parser.py
        with open(filepath, "rb") as stream:
            zip_stream = zipfile.ZipFile(stream)
            content = ET.fromstring(zip_stream.read("content.xml"))
        results = self.search_odt_element(filepath, content, [], [])
        if results:
            return SearchResults(results, self.search_term, rtype="odt")

    def search_odt_element(self, filepath, element, sections, results):
        """Search an element, if it has sub elements iterate"""
        # Look for headers
        if element.tag == qn("text:h"):
            header_text = element.text
            if header_text is None:
                header_text = ""
            sections.append(header_text)

            if self.search_term in header_text:
                results.append(SearchResult(filepath, sections=tuple(sections)))
        # Else look for text
        else:
            etext = element.text
            if etext is not None and self.search_term in etext:
                results.append(
                    SearchResult(filepath, rtext=etext, sections=tuple(sections))
                )

        for child in element:
            results = self.search_odt_element(filepath, child, sections, results)

        return results


### Data classes


@attr.s(auto_attribs=True)
class SearchResult:
    """Class that represents a search result"""

    filepath: str
    rtext: Optional[str] = None
    line_no: Optional[int] = None
    page_no: Optional[int] = None
    sections: Optional[List[str]] = None


@attr.s(auto_attribs=True)
class SearchResults:
    """Class that respresents all search results from a file"""

    results: List[SearchResult]
    search_term: str
    rtype: str

    def print_output(self, output_format):
        getattr(self, f"print_{self.rtype}_{output_format}")()

    def print_text_pretty(self):
        for result in self.results:
            text = result.rtext.rstrip().replace(
                self.search_term, f"{Fore.RED}{self.search_term}{Fore.WHITE}"
            )
            print(
                f"{Fore.MAGENTA}{result.filepath}, {Fore.GREEN}L{result.line_no}: "
                f"{Fore.WHITE}{Style.BRIGHT}{text}{Style.NORMAL}"
            )

    def print_pdf_pretty(self):
        for result in self.results:
            text = result.rtext.rstrip().replace(
                self.search_term, f"{Fore.RED}{self.search_term}{Fore.WHITE}"
            )
            print(
                f"{Fore.MAGENTA}{result.filepath}, {Fore.GREEN}P{result.page_no}: "
                f"{Fore.WHITE}{Style.BRIGHT}{text}{Style.NORMAL}"
            )

    def print_odt_pretty(self):
        for result in self.results:
            sectionpath = "->".join('"' + section + '"' for section in result.sections)
            if not sectionpath:
                sectionpath = "-"
            if result.rtext:
                text = result.rtext.rstrip().replace(
                    self.search_term, f"{Fore.RED}{self.search_term}{Fore.WHITE}"
                )
                print(
                    f"{Fore.MAGENTA}{result.filepath}, {Fore.GREEN}{sectionpath}: "
                    f"{Fore.WHITE}{Style.BRIGHT}{text}{Style.NORMAL}"
                )
            else:
                modified_sectionpath = sectionpath.replace(
                    self.search_term, f"{Fore.RED}{self.search_term}{Fore.GREEN}"
                )
                print(
                    f"{Fore.MAGENTA}{result.filepath}, {Fore.GREEN}{sectionpath}"
                    f"{Style.NORMAL}"
                )


if __name__ == "__main__":
    search()
