# ADFS Tools

Python tools for working with RISC OS Filecore (ADFS-style) disc images. These tools
support the E+ new map format used by modern RISC OS systems.

## Overview

These tools are primarily designed to assist with resizing Raspberry Pi SD cards
running RISC OS. Because Filecore does not support resizing discs in place, the
workflow involves reformatting the card and preserving the boot loader partition.

See [Pi-Resize.txt](Pi-Resize.txt) for the full step-by-step resizing workflow.

## Tools

### Core Modules

#### `objects.py`

Core data structures for the Filecore disc format. Provides classes for
reading, writing, and manipulating disc structures:

- **`DiscRecord`** — A `ctypes.Structure` representing the 60-byte disc record
  found in the boot block. Contains disc geometry (sector size, heads, sectors
  per track), map layout (zones, zone spare bits, bytes per map bit), and
  root directory information.

- **`Map`** — Manages the Filecore allocation map (zone map). The map is
  divided into zones, each one sector in size. Each zone contains a header
  (check byte, free space link, cross-check byte) followed by allocation bits.
  Fragments are identified by a fragment ID of `idlen` bits, followed by
  zero or more data bits, terminated by a stop bit. Provides methods to:
  - Allocate and find fragments
  - Convert between disc addresses and map coordinates
  - Calculate zone checksums and cross-checks
  - Display zone contents for debugging

- **`BigDir`** — Represents a Filecore "Big Directory" (new format directory).
  Directories start with a `SBPr` marker and end with an `oven` marker, and
  contain a name heap for variable-length entry names. Each entry
  (`BigDir.Entry`) stores load/exec addresses, length, attributes, and an
  indirect disc address (fragment ID + sector offset).

- **`BootBlock`** — A `ctypes.Structure` representing the 512-byte boot block
  located at disc offset `0xC00`. Contains a defect list, the disc record,
  and a checksum byte.

- **`dir_check_words(data, count, dircheck)`** — Computes a directory checksum
  over 32-bit words using a rotate-and-XOR algorithm.

- **`dir_check_bytes(data, count, dircheck)`** — Computes a directory checksum
  over individual bytes using the same algorithm.

#### `utils.py`

Utility functions for locating and reading Filecore maps from disc images:

- **`find_map(fd)`** — Reads the disc record from the boot block and calculates
  the map's disc address and length.

- **`get_map(fd)`** — Reads the complete allocation map from a disc image file
  and returns a `Map` object.

### Command-Line Tools

#### `fcform.py` — Format a Filecore disc

Creates a new Filecore-formatted disc image or device. Calculates optimal disc
geometry, finds a valid map allocation (zone count, LFAU, ID length), and writes
the boot block, allocation map, and empty root directory.

```
python fcform.py <device> <sectors> [--4k] [--lfau <size_in_K>]
```

- `device` — Output file or device path.
- `sectors` — Total number of sectors on the disc.
- `--4k` — Use 4096-byte sectors instead of the default 512-byte sectors.
- `--lfau` — Set a specific LFAU (Largest File Allocation Unit) in kilobytes.
  If not specified, displays available options and prompts for a choice.

#### `explore.py` — Interactive disc explorer

An interactive shell for browsing the directory structure of a Filecore disc
image. Uses Python's `cmd` module for a command-line interface.

```
python explore.py <device>
```

Commands:
- `dir <name>` — Navigate into a subdirectory.
- `up` — Navigate to the parent directory.
- `cat` — List the contents of the current directory.
- `zone <n>` — Display detailed allocation map information for zone `n`.
- `quit` — Exit the explorer.

#### `walk.py` — Directory tree walker

Recursively traverses and prints the entire directory tree of a Filecore disc.

```
python walk.py <device>
```

#### `get_loader.py` — Extract boot loader

Extracts the DOS partition (boot loader) from a disc device to a file.

```
python get_loader.py <device> <output_file>
```

#### `put_loader.py` — Write boot loader

Writes a previously saved boot loader to the correct location on a disc,
and creates the MBR partition table with DOS and ADFS partitions.

```
python put_loader.py <device> <loader_file>
```

#### `add_loader.py` — Add Loader directory entry

Adds a `Loader` file entry to the root directory of a Filecore disc. The
Loader entry points to the DOS partition area so that RISC OS can see it
as a file.

```
python add_loader.py <device>
```

#### `claim_frags.py` — Claim loader fragments

Marks the disc area used by the boot loader as allocated in the Filecore
map, preventing the file system from overwriting it.

```
python claim_frags.py <device>
```

## Filecore Concepts

### E+ New Map Format

The E+ format (also known as "new map" or "big map") supports large discs
with the following key features:

- **Zones**: The disc is divided into zones, each described by one sector
  of the allocation map. Zone 0 also contains the disc record.

- **Fragments**: Disc space is allocated in fragments. Each fragment has an
  ID (of `idlen` bits) followed by data bits and a stop bit. A fragment ID
  of 0 indicates free space, 1 is used for disc defects, and 2 is reserved
  for the map itself.

- **LFAU (Largest File Allocation Unit)**: Each map bit represents this many
  bytes of disc space (`bytes_per_map_bit` or `bpmb`). Larger values mean
  less map overhead but more wasted space in small files.

- **Indirect Disc Addresses**: Files are referenced by fragment ID (upper
  bits) and sector offset (lower 8 bits), rather than by absolute disc
  address.

### Disc Layout

```
Offset 0x000: MBR / Partition Table (optional, for Pi cards)
Offset 0xC00: Boot Block (512 bytes)
              - Defect list (448 bytes)
              - Disc Record (60 bytes)
              - Non-ADFS flag (3 bytes)
              - Checksum (1 byte)
Variable:     Allocation Map (two identical copies, back-to-back)
Variable:     Root Directory (typically 2048 bytes)
Variable:     File data and subdirectories
```

## Requirements

- Python 3.6 or later

## Known Issues

- The tools assume standard 512-byte sector MBR layouts for partition
  table handling.
- `fcform.py` currently hard-codes the disc name to `"Turnips  "`.
