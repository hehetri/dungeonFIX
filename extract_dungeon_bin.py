from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable, List


DEFAULT_BIN_PATH = Path("dungeon.bin")
DEFAULT_OUTPUT_DIR = Path("extracted_dungeons")
DEFAULT_PARSED_DIR = Path("parsed_dungeons")
SCRIPT_NAME_SIZE = 260
XOR_KEY = 0xFF


def read_script_names(data: bytes, count: int, start: int) -> List[str]:
    names: List[str] = []
    for i in range(count):
        block = data[start + i * SCRIPT_NAME_SIZE : start + (i + 1) * SCRIPT_NAME_SIZE]
        name = block.split(b"\x00", 1)[0].decode("ascii")
        if not name:
            raise ValueError(f"Encountered empty script name at index {i}")
        names.append(name)
    return names


def read_offsets(data: bytes, count: int, start: int) -> List[int]:
    offsets: List[int] = []
    for i in range(count):
        chunk = data[start + i * 4 : start + (i + 1) * 4]
        offsets.append(int.from_bytes(chunk, "little"))
    return offsets


def decode_script(chunk: bytes) -> bytes:
    return bytes(b ^ XOR_KEY for b in chunk)


def _parse_ints(parts: Iterable[str]) -> List[int]:
    return [int(part) for part in parts if part]


def parse_dungeon_script(decoded: bytes) -> dict:
    lines = decoded.decode("ascii", errors="replace").splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)

    if not lines:
        raise ValueError("Unexpected dungeon header: empty script")

    header = ""
    while lines and not re.search(r"\d", header):
        header = lines.pop(0).strip()

    match = re.search(r"(\d+)", header)
    if not match:
        raise ValueError("Unexpected dungeon header: missing spawn count")

    spawn_count = int(match.group(1))
    spawns: List[int] = []

    cursor = 0
    while len(spawns) < spawn_count and cursor < len(lines):
        line = lines[cursor].strip()
        cursor += 1
        if not line:
            continue
        tokens = _parse_ints(line.split("\t"))
        if len(tokens) < 2:
            raise ValueError(f"Malformed spawn line {len(spawns)}: '{line}'")
        spawns.append(tokens[-1])

    while cursor < len(lines) and not re.search(r"\d", lines[cursor]):
        cursor += 1

    if cursor >= len(lines):
        raise ValueError("Missing block count")

    block_match = re.search(r"(\d+)", lines[cursor])
    if not block_match:
        raise ValueError(f"Malformed block count line: '{lines[cursor]}'")

    block_count = int(block_match.group(1))
    cursor += 1

    blocks = []
    for block_index in range(block_count):
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1

        rect = _parse_ints(lines[cursor].strip().split("\t"))
        cursor += 1

        enemies_raw = _parse_ints(lines[cursor].strip().split("\t"))
        cursor += 1

        respawn_raw = _parse_ints(lines[cursor].strip().split("\t"))
        cursor += 1

        clear_raw = _parse_ints(lines[cursor].strip().split("\t"))
        cursor += 1

        vip_raw = _parse_ints(lines[cursor].strip().split("\t"))
        cursor += 1

        exceptional_raw = _parse_ints(lines[cursor].strip().split("\t"))
        cursor += 1

        text = lines[cursor].replace("\t", "").strip()
        cursor += 1

        countdown_line = lines[cursor].strip()
        cursor += 1

        countdown_match = re.search(r"(\d+)", countdown_line)
        countdown_value = int(countdown_match.group(1)) if countdown_match else 0

        block = {
            "rect": rect,
            "enemies": enemies_raw[1:] if enemies_raw else [],
            "respawn": respawn_raw[1:] if respawn_raw else [],
            "clear": clear_raw[1:] if clear_raw else [],
            "vip": vip_raw[1:] if vip_raw else [],
            "exceptional": exceptional_raw[1:] if exceptional_raw else [],
            "text": text,
            "countdown": countdown_value,
        }

        blocks.append(block)

    return {"spawns": spawns, "blocks": blocks}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Decode dungeon*.bin archives and emit .dun plus structured JSON."
    )
    parser.add_argument(
        "--bin",
        dest="bin_path",
        type=Path,
        default=DEFAULT_BIN_PATH,
        help="Path to the dungeon archive (default: dungeon.bin)",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for decoded .dun files (default: extracted_dungeons)",
    )
    parser.add_argument(
        "--parsed-dir",
        dest="parsed_dir",
        type=Path,
        default=DEFAULT_PARSED_DIR,
        help="Directory for parsed JSON files (default: parsed_dungeons)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    data = args.bin_path.read_bytes()

    script_count = int.from_bytes(data[12:16], "little")
    names_start = 16
    names = read_script_names(data, script_count, names_start)

    offsets_start = names_start + script_count * SCRIPT_NAME_SIZE
    offsets = read_offsets(data, script_count, offsets_start)
    offsets.append(len(data))

    args.output_dir.mkdir(exist_ok=True)
    args.parsed_dir.mkdir(exist_ok=True)

    for index, name in enumerate(names):
        start = offsets[index]
        end = offsets[index + 1]
        decoded = decode_script(data[start:end])

        filename = f"{name}.dun" if not name.endswith(".dun") else name
        output_path = args.output_dir / filename
        output_path.write_bytes(decoded)

        try:
            parsed = parse_dungeon_script(decoded)
        except ValueError as exc:
            raise ValueError(f"Failed to parse script '{filename}': {exc}") from exc
        json_path = args.parsed_dir / f"{Path(filename).stem}.json"
        json_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False))

    print(
        f"Extracted {len(names)} scripts from {args.bin_path} to {args.output_dir}/"
    )


if __name__ == "__main__":
    main()
