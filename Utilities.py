from contextlib import contextmanager
from time import perf_counter
import os
from typing import Any
from pathlib import Path
import sys
from subprocess import run, Popen, PIPE
from statistics import mean
from json import load
from rich import print
from rich.progress import track
from dataclasses import dataclass

# NUITKA_VERSIONS = ["nuitka", '"https://github.com/Nuitka/Nuitka/archive/factory.zip"'] # Currently factory is equivalent to release
NUITKA_VERSIONS = ["nuitka"]


class Timer:
    def __init__(self):
        self.start = 0
        self.end = 0

        self.time_taken = 0

    def __enter__(self):
        self.start = perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end = perf_counter()

        self.time_taken = self.end - self.start

    def __call__(self, func: Any):
        def wrapper(*args, **kwargs):
            with self:
                return func(*args, **kwargs)

        return wrapper


@contextmanager
def temporary_directory_change(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Directory {path} does not exist")
    current_directory = Path.cwd()
    os.chdir(path)
    yield
    os.chdir(current_directory)


def resolve_venv_path() -> Path:
    resolved_path = Path(sys.executable).resolve()
    if is_in_venv():
        return resolved_path
    else:
        venv_create = run(f"{resolved_path} -m venv venv", stdout=PIPE, stderr=PIPE)
        if venv_create.returncode != 0:
            raise RuntimeError("Failed to create venv")

        new_venv_path = Path("venv")
        if new_venv_path.exists():
            return (new_venv_path / "Scripts" / "python.exe").resolve()
        else:
            raise FileNotFoundError("Failed to create venv")


def create_venv_with_version(version: str) -> Path:
    venv_create = run(f"py -{version} -m venv {version}_venv")
    if venv_create.returncode != 0:
        raise RuntimeError("Failed to create venv")

    new_venv_path = Path(f"{version}_venv")
    if new_venv_path.exists():
        return (new_venv_path / "Scripts" / "python.exe").resolve()
    else:
        raise FileNotFoundError("Failed to create venv")


def run_benchmark(
    benchmark: Path,
    python_executable: Path,
    iterations: int,
    cpython_version: str,
    type: str,
    nuitka_name: str,
) -> dict[str, list[float]]:
    local_results: dict[str, list[float]] = {
        "warmup": [],
        "benchmark": [],
    }
    run_command = {
        "Nuitka": Path(os.getcwd()) / "run_benchmark.dist/run_benchmark.exe",
        "CPython": [python_executable, "run_benchmark.py"],
    }
    description_dict = {
        "Nuitka": f"{benchmark.name} with {type} | Nuitka Version: {nuitka_name}",
        "CPython": f"{benchmark.name} with {type} | Python Version: {cpython_version}",
    }

    for _ in track(
        range(iterations),
        description=f"Warming up {description_dict[type]}",
        total=iterations,
    ):
        with Timer() as timer:
            res = run(run_command[type])  # type: ignore
            if res.returncode != 0:
                raise RuntimeError(f"Failed to run benchmark {benchmark.name}")
        local_results["warmup"].append(timer.time_taken)

    if max(local_results["warmup"]) == local_results["warmup"][0]:
        local_results["warmup"].pop(0)

    for _ in track(
        range(iterations),
        description=f"Warming up {description_dict[type]} (benchmark)",
        total=iterations,
    ):
        with Timer() as timer:
            res = run(run_command[type])  # type: ignore
            if res.returncode != 0:
                raise RuntimeError(f"Failed to run benchmark {benchmark.name}")

        local_results["benchmark"].append(timer.time_taken)

    print(
        f"Results for {benchmark.name} with {nuitka_name} | Python Version: {cpython_version}"
    )

    return local_results


def parse_py_launcher():
    BLACKLIST = ["3.13", "3.13t", "3.6", "3.7", "3.8", "3.9", "3.10", "3.12"]
    res = Popen(["py", "-0"], shell=True, stdout=PIPE, stderr=PIPE)
    resp = [line.decode("utf-8").strip().split("Python") for line in res.stdout]
    if "Active venv" in resp[0][0]:
        resp.pop(0)
    versions = [
        version[0].strip().replace("-V:", "").replace(" *", "") for version in resp
    ]
    versions = [version for version in versions if version not in BLACKLIST]
    return versions


def is_in_venv():
    # https://stackoverflow.com/a/1883251
    return sys.prefix != sys.base_prefix


@dataclass
class Stats:
    name: str
    warmup: list[float]
    benchmark: list[float]


@dataclass
class Benchmark:
    target: str
    nuitka_version: str
    python_version: tuple[int, int]
    file_json: dict
    nuitka_stats: Stats
    cpython_stats: Stats
    benchmark_name: str

    @staticmethod
    def parse_file_name(file_name: str) -> tuple[str, str, tuple[int, int]]:
        target, nuitka_version, python_version = file_name.split("-")
        py_ver_split = python_version.split(".")
        python_version_tuple = (int(py_ver_split[0]), int(py_ver_split[1]))
        return target, nuitka_version, python_version_tuple

    @staticmethod
    def parse_stats(stats: dict) -> dict:
        nuitka_stats = stats["nuitka"]
        cpython_stats = stats["cpython"]
        return {
            "nuitka": Stats(
                "nuitka",
                nuitka_stats["warmup"],
                nuitka_stats["benchmark"],
            ),
            "cpython": Stats(
                "cpython",
                cpython_stats["warmup"],
                cpython_stats["benchmark"],
            ),
        }

    @classmethod
    def from_path(cls, file_path: Path, benchmark_name: str) -> "Benchmark":
        if not file_path.stat().st_size > 0:
            raise FileNotFoundError(f"File {file_path} does not exist or is empty")

        with open(file_path, "r") as f:
            file_json = load(f)

        file_info = cls.parse_file_name(file_path.stem)
        parsed_stats = cls.parse_stats(file_json)
        return cls(
            target=file_info[0],
            nuitka_version=file_info[1],
            python_version=file_info[2],
            file_json=file_json,
            nuitka_stats=parsed_stats["nuitka"],
            cpython_stats=parsed_stats["cpython"],
            benchmark_name=benchmark_name.strip("bm_"),
        )
