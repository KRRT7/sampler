from pathlib import Path
from dataclasses import dataclass
from json import load
from rich import print
from rich.table import Table
from statistics import mean


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

    def _calculate_stats(self, results: Stats) -> float:
        is_warmup_skewed: bool = min(results.warmup) == results.warmup[0]
        is_benchmark_skewed: bool = min(results.benchmark) == results.benchmark[0]
        warmup = mean(results.warmup[is_warmup_skewed:])
        benchmark = mean(results.benchmark[is_benchmark_skewed:])
        return min(warmup, benchmark)

    def calculate_nuitka_stats(self) -> str:
        return f"{self._calculate_stats(self.nuitka_stats):.2f}"

    def calculate_cpython_stats(self) -> str:
        return f"{self._calculate_stats(self.cpython_stats):.2f}"

    def __str__(self) -> str:
        return f"{self.target} - {self.nuitka_version} - {self.python_version}"

    def __repr__(self) -> str:
        return f"Benchmark(target={self.target}, nuitka_version={self.nuitka_version}, python_version={self.python_version})"


BENCHMARK_DIRECTORY = Path("benchmarks")

results_container: dict[tuple[int, int], list[Benchmark]] = {}

for benchmark_item in BENCHMARK_DIRECTORY.iterdir():
    if benchmark_item.is_dir() and not benchmark_item.name.startswith("bm_"):
        continue

    results = benchmark_item / "results"
    for date in results.iterdir():
        if not date.is_dir():
            continue

        for result in date.iterdir():
            if not result.is_file():
                continue

            benchmark_result = Benchmark.from_path(result, benchmark_item.name)

            results_container.setdefault(benchmark_result.python_version, []).append(
                benchmark_result
            )


def format_benchmark_stat(nuitka, cpython) -> str:
    if nuitka < cpython:
        percentage = (cpython / nuitka) * 100 - 100
        return f"{nuitka:.2f} +[green]{percentage:.2f}%[/green]"

    elif nuitka > cpython:
        percentage = (nuitka / cpython) * 100 - 100
        return f"{nuitka:.2f} -[red]{percentage:.2f}%[/red]"
    else:
        return f"{nuitka:.2f}"


sorted_results = sorted(results_container.items(), key=lambda x: x[0], reverse=True)


sorted_results = sorted(results_container.items(), key=lambda x: x[0], reverse=True)
for python_version, benchmarks in sorted_results:
    Bench_table = Table(title="Benchmarks")
    Bench_table.add_column("Benchmark", justify="center")
    Bench_table.add_column("CPython", justify="center")
    Bench_table.add_column("Nuitka Release", justify="center")
    Bench_table.add_column("Python Version", justify="center")

    for benchmark in benchmarks:
        Bench_table.add_row(
            benchmark.benchmark_name,
            str(benchmark.calculate_cpython_stats()),
            str(benchmark.calculate_nuitka_stats()),
            f"{python_version[0]}.{python_version[1]}",
        )
    # print(f"Python Version: {python_version[0]}.{python_version[1]} with {len(benchmarks)} benchmarks")
    print(Bench_table)

input("Press Enter to exit")