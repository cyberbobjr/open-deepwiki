from __future__ import annotations

import tempfile
from pathlib import Path

from indexer import iter_java_files


def test_iter_java_files_excludes_maven_test_layout_by_default() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        main_dir = root / "src" / "main" / "java" / "com" / "example"
        test_dir = root / "src" / "test" / "java" / "com" / "example"
        main_dir.mkdir(parents=True)
        test_dir.mkdir(parents=True)

        (main_dir / "MainService.java").write_text("class MainService {}\n", encoding="utf-8")
        (test_dir / "MainServiceTest.java").write_text("class MainServiceTest {}\n", encoding="utf-8")

        files = [p.resolve() for p in iter_java_files(str(root))]
        assert (main_dir / "MainService.java").resolve() in files
        assert (test_dir / "MainServiceTest.java").resolve() not in files


def test_iter_java_files_does_not_exclude_test_suffix_outside_test_dirs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        src = root / "src" / "main" / "java"
        src.mkdir(parents=True)

        (src / "Benefit.java").write_text("class Benefit {}\n", encoding="utf-8")
        (src / "PaymentServiceTest.java").write_text("class PaymentServiceTest {}\n", encoding="utf-8")
        (src / "OrderIT.java").write_text("class OrderIT {}\n", encoding="utf-8")

        files = {p.name for p in iter_java_files(str(root))}
        assert "Benefit.java" in files
        assert "PaymentServiceTest.java" in files
        assert "OrderIT.java" in files


def test_iter_java_files_can_include_tests_when_disabled() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        test_dir = root / "src" / "test" / "java"
        test_dir.mkdir(parents=True)
        (test_dir / "FooTest.java").write_text("class FooTest {}\n", encoding="utf-8")

        files = {p.name for p in iter_java_files(str(root), exclude_tests=False)}
        assert "FooTest.java" in files
