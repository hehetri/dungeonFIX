from __future__ import annotations

import argparse
from pathlib import Path
from typing import List


BIN_PATH = Path("dungeon.bin")
OUTPUT_PATH = Path("dungeon_packed.bin")
INPUT_DIR = Path("extracted_dungeons")
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


def encode_script(chunk: bytes) -> bytes:
    return bytes(b ^ XOR_KEY for b in chunk)


def build_bin(base_path: Path, input_dir: Path, output_path: Path) -> None:
    data = base_path.read_bytes()
    script_count = int.from_bytes(data[12:16], "little")
    names_start = 16
    names = read_script_names(data, script_count, names_start)

    offsets_start = names_start + script_count * SCRIPT_NAME_SIZE
    data_start = offsets_start + script_count * 4

    encoded_scripts: List[bytes] = []
    for name in names:
        filename = f"{name}.dun" if not name.endswith(".dun") else name
        script_path = input_dir / filename
        if not script_path.exists():
            raise FileNotFoundError(f"Missing script file: {script_path}")
        encoded_scripts.append(encode_script(script_path.read_bytes()))

    header = bytearray(data[:16])
    header[12:16] = script_count.to_bytes(4, "little")

    names_blob = bytearray()
    for name in names:
        encoded = name.encode("ascii")
        if len(encoded) >= SCRIPT_NAME_SIZE:
            raise ValueError(f"Script name too long: {name}")
        names_blob.extend(encoded)
        names_blob.extend(b"\x00" * (SCRIPT_NAME_SIZE - len(encoded)))

    offsets_blob = bytearray()
    current_offset = data_start
    for chunk in encoded_scripts:
        offsets_blob.extend(current_offset.to_bytes(4, "little"))
        current_offset += len(chunk)

    output = bytearray()
    output.extend(header)
    output.extend(names_blob)
    output.extend(offsets_blob)
    for chunk in encoded_scripts:
        output.extend(chunk)

    output_path.write_bytes(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pack dungeon scripts back into a .bin file.")
    parser.add_argument("--base", type=Path, default=BIN_PATH, help="Base dungeon.bin to read header and names from.")
    parser.add_argument("--input", type=Path, default=INPUT_DIR, help="Directory with .dun scripts.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Output .bin path.")
    args = parser.parse_args()

    build_bin(args.base, args.input, args.output)
    print(f"Packed {args.input} into {args.output}")


if __name__ == "__main__":
    main()
