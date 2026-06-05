# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "msoffcrypto-tool>=5.4.2",
#   "pikepdf>=9.0.0",
# ]
# ///
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import msoffcrypto
import pikepdf


OFFICE_EXTS = {".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt"}
PDF_EXTS = {".pdf"}
SKIP_DIRS = {
    ".docmemory",
    "__pycache__",
    "_history",
    "doctovec_password_backup",
    "doctovec_unlocked",
    "docmemory_tool",
    "markdown",
    "skills",
}


@dataclass
class Result:
    status: str
    source: Path
    output: Path | None
    detail: str


def parse_args() -> argparse.Namespace:
    app_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    default_root = app_dir if getattr(sys, "frozen", False) else app_dir.parent
    default_password_file = default_root / "Config" / "pass.txt"

    parser = argparse.ArgumentParser(
        description="Remove open-password protection from Office/PDF files."
    )
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        default=[default_root],
        help="Folders/files to scan. You can drag and drop them onto the exe.",
    )
    parser.add_argument(
        "--password",
        action="append",
        default=None,
        help="Open password used to decrypt files. Can be repeated. Defaults to Config\\pass.txt.",
    )
    parser.add_argument(
        "--password-file",
        type=Path,
        default=default_password_file,
        help="Password config file. Defaults to Config\\pass.txt.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Folder for unlocked copies when not using --in-place.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Replace encrypted originals after writing backups.",
    )
    parser.add_argument(
        "--backup",
        type=Path,
        default=None,
        help="Backup folder used with --in-place.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="TSV report path. Defaults beside the output/backup folder.",
    )
    return parser.parse_args()


def read_passwords(path: Path) -> list[str]:
    if not path.exists():
        return []
    passwords: list[str] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            passwords.append(value)
    return passwords


def password_candidates(args: argparse.Namespace) -> list[str]:
    values = args.password if args.password else read_passwords(args.password_file)
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def default_output_root_for(scan_root: Path) -> Path:
    if scan_root.is_file():
        return scan_root.parent / "unlocked"
    return scan_root.parent / f"{scan_root.name}_unlocked"


def default_backup_root_for(scan_root: Path) -> Path:
    if scan_root.is_file():
        return scan_root.parent / "password_backup"
    return scan_root.parent / f"{scan_root.name}_password_backup"


def iter_targets(root: Path) -> list[Path]:
    root = root.resolve()
    if root.is_file():
        return [root]

    targets: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name.startswith("~$"):
            continue
        if path.suffix.lower() in OFFICE_EXTS | PDF_EXTS:
            targets.append(path)
    return sorted(targets)


def output_path_for(src: Path, scan_root: Path, output_root: Path) -> Path:
    if scan_root.is_file():
        return output_root / src.name
    return output_root / src.relative_to(scan_root)


def backup_path_for(src: Path, scan_root: Path, backup_root: Path) -> Path:
    if scan_root.is_file():
        return backup_root / src.name
    return backup_root / src.relative_to(scan_root)


def decrypt_office(src: Path, dst: Path, passwords: list[str]) -> Result:
    last_error = ""
    for password in passwords:
        try:
            with src.open("rb") as input_file:
                office_file = msoffcrypto.OfficeFile(input_file)
                if not office_file.is_encrypted():
                    return Result("skipped", src, None, "office file is not encrypted")
                office_file.load_key(password=password)
                dst.parent.mkdir(parents=True, exist_ok=True)
                with dst.open("wb") as output_file:
                    office_file.decrypt(output_file)
            return Result("unlocked", src, dst, "office password removed")
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
    return Result("failed", src, None, f"configured passwords failed: {last_error}")


def decrypt_pdf(src: Path, dst: Path, passwords: list[str]) -> Result:
    for password in passwords:
        try:
            with pikepdf.open(src, password=password) as pdf:
                if not pdf.is_encrypted:
                    return Result("skipped", src, None, "pdf is not encrypted")
                dst.parent.mkdir(parents=True, exist_ok=True)
                pdf.save(dst)
            return Result("unlocked", src, dst, "pdf password removed")
        except pikepdf.PasswordError:
            continue
        except Exception as exc:
            return Result("failed", src, None, f"{type(exc).__name__}: {exc}")
    return Result("failed", src, None, "configured passwords failed")


def decrypt_one(src: Path, dst: Path, passwords: list[str]) -> Result:
    suffix = src.suffix.lower()
    if suffix in OFFICE_EXTS:
        return decrypt_office(src, dst, passwords)
    if suffix in PDF_EXTS:
        return decrypt_pdf(src, dst, passwords)
    return Result("skipped", src, None, "unsupported extension")


def replace_original(src: Path, unlocked: Path, scan_root: Path, backup_root: Path) -> None:
    backup = backup_path_for(src, scan_root, backup_root)
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(src, backup)
    shutil.move(str(unlocked), str(src))


def write_report(results: list[Result], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, delimiter="\t")
        writer.writerow(["status", "source", "output", "detail"])
        for result in results:
            writer.writerow(
                [
                    result.status,
                    str(result.source),
                    "" if result.output is None else str(result.output),
                    result.detail,
                ]
            )


def process_root(args: argparse.Namespace, scan_root: Path, passwords: list[str]) -> tuple[list[Result], Path]:
    scan_root = scan_root.resolve()
    if not scan_root.exists():
        print(f"Root does not exist: {scan_root}", file=sys.stderr)
        return [Result("failed", scan_root, None, "root does not exist")], scan_root.parent

    output_root = args.output.resolve() if args.output else default_output_root_for(scan_root)
    backup_root = args.backup.resolve() if args.backup else default_backup_root_for(scan_root)
    report_root = backup_root if args.in_place else output_root

    results: list[Result] = []
    for src in iter_targets(scan_root):
        dst = output_path_for(src, scan_root, output_root)
        result = decrypt_one(src, dst, passwords)
        if args.in_place and result.status == "unlocked" and result.output is not None:
            try:
                replace_original(src, result.output, scan_root, backup_root)
                result = Result(
                    "replaced",
                    src,
                    backup_path_for(src, scan_root, backup_root),
                    "original replaced; backup saved",
                )
            except Exception as exc:
                result = Result("failed", src, result.output, f"in-place replace failed: {exc}")
        results.append(result)
        print(f"{result.status}: {src}")
    return results, report_root


def main() -> int:
    args = parse_args()
    passwords = password_candidates(args)
    if not passwords:
        print(f"No passwords configured: {args.password_file}")
        print("Password removal skipped.")
        return 0

    all_results: list[Result] = []
    report_roots: set[Path] = set()

    for raw_root in args.roots:
        print(f"Scan: {raw_root}")
        results, report_root = process_root(args, raw_root, passwords)
        all_results.extend(results)
        report_roots.add(report_root.resolve())
        print()

    report_paths = (
        [args.report.resolve()]
        if args.report
        else [root / "password_remove_report.tsv" for root in sorted(report_roots)]
    )
    for report_path in report_paths:
        write_report(all_results, report_path)

    results = all_results
    unlocked_count = sum(1 for result in results if result.status in {"unlocked", "replaced"})
    failed_count = sum(1 for result in results if result.status == "failed")
    skipped_count = sum(1 for result in results if result.status == "skipped")
    print()
    for report_path in report_paths:
        print(f"Report: {report_path}")
    print(f"Unlocked/replaced: {unlocked_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Failed: {failed_count}")
    return 1 if failed_count else 0


if __name__ == "__main__":
    exit_code = main()
    if getattr(sys, "frozen", False):
        input("Done. Press Enter to close this window...")
    raise SystemExit(exit_code)
