#!/usr/bin/env python3
import argparse
import os
import re
from dataclasses import dataclass
from typing import List, Tuple

INT_RE = re.compile(r"-?\d+")


@dataclass
class SpawnTableEntry:
    index: int
    spawn_id: int


@dataclass
class SpawnArray:
    count: int
    indices: List[int]


@dataclass
class Block:
    area: Tuple[int, int, int, int]
    valid_spawns: SpawnArray
    rebirth_spawns: SpawnArray
    trigger_spawns: SpawnArray
    vip_spawns: SpawnArray
    exceptional_spawns: SpawnArray
    text: str
    value: int


@dataclass
class ScriptData:
    name: str
    spawns: List[SpawnTableEntry]
    blocks: List[Block]


def parse_ints(line: str) -> List[int]:
    return [int(value) for value in INT_RE.findall(line)]


def sanitize_filename(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip())
    if not cleaned:
        cleaned = fallback
    return cleaned


def decode_script(data: bytes) -> str:
    decoded = bytes((b ^ 0xFF) for b in data)
    return decoded.decode("ascii", errors="replace")


def iter_lines(text: str) -> List[str]:
    return text.splitlines()


def next_line(lines: List[str], index: int, *, allow_empty: bool = False) -> Tuple[str, int]:
    while index < len(lines):
        line = lines[index]
        index += 1
        if line.lstrip().startswith(";"):
            continue
        if not allow_empty and line.strip() == "":
            continue
        return line, index
    raise ValueError("Unexpected end of script data")


def parse_spawn_array(line: str) -> SpawnArray:
    values = parse_ints(line)
    if not values:
        return SpawnArray(count=0, indices=[])
    count = values[0]
    indices = values[1:]
    return SpawnArray(count=count, indices=indices)


def parse_script(name: str, text: str) -> ScriptData:
    lines = iter_lines(text)
    index = 0

    line, index = next_line(lines, index)
    spawn_count_values = parse_ints(line)
    if not spawn_count_values:
        raise ValueError("Missing spawn count")
    spawn_count = spawn_count_values[0]

    spawns: List[SpawnTableEntry] = []
    for _ in range(spawn_count):
        line, index = next_line(lines, index)
        values = parse_ints(line)
        if len(values) >= 2:
            spawn_index, spawn_id = values[0], values[1]
        elif len(values) == 1:
            spawn_index, spawn_id = len(spawns), values[0]
        else:
            spawn_index, spawn_id = len(spawns), -1
        spawns.append(SpawnTableEntry(index=spawn_index, spawn_id=spawn_id))

    line, index = next_line(lines, index)
    block_count_values = parse_ints(line)
    if not block_count_values:
        raise ValueError("Missing block count")
    block_count = block_count_values[0]

    blocks: List[Block] = []
    for _ in range(block_count):
        line, index = next_line(lines, index)
        area_values = parse_ints(line)
        if len(area_values) < 4:
            raise ValueError("Missing area rectangle values")
        area = tuple(area_values[:4])

        line, index = next_line(lines, index)
        valid_spawns = parse_spawn_array(line)

        line, index = next_line(lines, index)
        rebirth_spawns = parse_spawn_array(line)

        line, index = next_line(lines, index)
        trigger_spawns = parse_spawn_array(line)

        line, index = next_line(lines, index)
        vip_spawns = parse_spawn_array(line)

        line, index = next_line(lines, index)
        exceptional_spawns = parse_spawn_array(line)

        line, index = next_line(lines, index, allow_empty=True)
        text_line = line.rstrip("\r\n")

        line, index = next_line(lines, index)
        value_values = parse_ints(line)
        if not value_values:
            raise ValueError("Missing block value")
        value = value_values[0]

        blocks.append(
            Block(
                area=area,
                valid_spawns=valid_spawns,
                rebirth_spawns=rebirth_spawns,
                trigger_spawns=trigger_spawns,
                vip_spawns=vip_spawns,
                exceptional_spawns=exceptional_spawns,
                text=text_line,
                value=value,
            )
        )

    return ScriptData(name=name, spawns=spawns, blocks=blocks)


def format_spawn_array(label: str, array: SpawnArray) -> List[str]:
    indices = " ".join(str(value) for value in array.indices)
    return [f"  {label} ({array.count}): {indices}".rstrip()]


def render_script(script: ScriptData) -> str:
    lines: List[str] = []
    lines.append(f"Script: {script.name}")
    lines.append(f"Spawn Count: {len(script.spawns)}")
    lines.append("Spawn Table:")
    for entry in script.spawns:
        lines.append(f"  {entry.index}\t{entry.spawn_id}")

    lines.append(f"Block Count: {len(script.blocks)}")
    for idx, block in enumerate(script.blocks, start=1):
        lines.append(f"Block {idx}:")
        left, top, right, bottom = block.area
        lines.append(f"  Area: {left} {top} {right} {bottom}")
        lines.extend(format_spawn_array("Valid Spawns", block.valid_spawns))
        lines.extend(format_spawn_array("Rebirth Spawns", block.rebirth_spawns))
        lines.extend(format_spawn_array("Trigger Spawns", block.trigger_spawns))
        lines.extend(format_spawn_array("VIP Spawns", block.vip_spawns))
        lines.extend(format_spawn_array("Exceptional Spawns", block.exceptional_spawns))
        lines.append(f"  Text: {block.text}")
        lines.append(f"  Value: {block.value}")

    return "\n".join(lines) + "\n"


def read_script_metadata(data: bytes) -> Tuple[List[str], List[int]]:
    if len(data) < 16:
        raise ValueError("File too small to contain header")
    script_count = int.from_bytes(data[12:16], "little")
    names: List[str] = []
    offset = 16
    for i in range(script_count):
        raw_name = data[offset : offset + 260]
        offset += 260
        name = raw_name.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()
        names.append(name or f"script_{i}")
    offsets: List[int] = []
    for _ in range(script_count):
        offsets.append(int.from_bytes(data[offset : offset + 4], "little"))
        offset += 4
    return names, offsets


def extract_scripts(bin_path: str, output_dir: str) -> List[str]:
    with open(bin_path, "rb") as handle:
        data = handle.read()

    names, offsets = read_script_metadata(data)
    output_files: List[str] = []
    for idx, (name, start) in enumerate(zip(names, offsets)):
        end = offsets[idx + 1] if idx + 1 < len(offsets) else len(data)
        script_bytes = data[start:end]
        decoded_text = decode_script(script_bytes)
        script = parse_script(name, decoded_text)
        rendered = render_script(script)
        filename = sanitize_filename(name, f"script_{idx}") + ".dun"
        output_path = os.path.join(output_dir, filename)
        with open(output_path, "w", encoding="utf-8") as out_handle:
            out_handle.write(rendered)
        output_files.append(output_path)
    return output_files


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract dungeon scripts from dungeon.bin")
    parser.add_argument("bin_path", help="Path to dungeon.bin")
    parser.add_argument(
        "-o",
        "--output-dir",
        default="dungeons",
        help="Directory to write extracted .dun files",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    output_files = extract_scripts(args.bin_path, args.output_dir)
    print(f"Extracted {len(output_files)} scripts to {args.output_dir}")


if __name__ == "__main__":
    main()
