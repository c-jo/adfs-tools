#! /usr/bin/python

import sys
import struct
import ctypes
import argparse

from array import array
from objects import DiscRecord, Map, BigDir, BootBlock, BOOT_BLOCK_ADDRESS
from itertools import product
from device import DiscImage, HDFImage, TestDevice
from utils import get_map

ZONE0BITS = 60*8 # Bits used in Zone 0
IDLEN_MAX = 21
MAPSIZE_MAX = 128*1024*1024


def make_shape(sectors):
    """Generate a CHS shape for a given number of sectors."""
    best_wasted = 0xffffffff
    best = None
    for secs,heads in product(range(63,15,-1), range(255,15,-1)):
        cyls = sectors // (secs*heads)
        if cyls > 65535:
            continue
        wasted = sectors % (secs*heads)
        if (wasted < best_wasted):
            best_wasted = wasted
            best = (secs,heads,sectors//(secs*heads))
    return best

def check_alloc(sectors, log2ss, zones, zonespare, log2bpmb, idlen):
    """Checks if the given allocation is valid."""
    disc_allocs = (sectors << log2ss) // (1 << log2bpmb)
    bpzm = 8 * (1 << log2ss) - zonespare # Bits per zone map
    map_allocs = (bpzm * zones) - ZONE0BITS
    idpz = bpzm // (idlen+1) # IDs per Zone

    if map_allocs < disc_allocs:
        return False # Map doens't cover disc

    if (1 << idlen) < idpz * zones:
        return False # Not enough IDs

    excess_allocs = map_allocs - disc_allocs
    if 0 < excess_allocs <= idlen:
        return False # Can't make excess into a fragment

    lz_allocs = disc_allocs - (map_allocs - bpzm)
    if lz_allocs <= idlen:
        return False # Can't make last bit of last zone into a fragment

    return True

def find_alloc(sectors, log2ss, zones, log2bpmb):
    """Find an allocation for the given zones/log2bpmb, or 
       None if one cannot be found."""
    for zonespare in range(32,64): # 32 to ZoneBits%-Zone0Bits%-8*8
        for idlen in range(log2ss, IDLEN_MAX+1):
            if check_alloc(sectors, log2ss, zones, zonespare, log2bpmb, idlen):
                return (zones, zonespare, log2bpmb, idlen)


def write_format(disc, dr):
    """Write a Filecore format to disc.

    dr must have all geometry and allocation fields set: log2secsize,
    disc_size, secspertrack, heads, nzones, zone_spare, log2bpmb, idlen,
    log2share, disc_name.  This function calculates and sets dr.root and
    dr.root_size, then writes the boot block, both map copies and the
    root directory.

    Returns a dict with keys map_address, map_size, root_address.
    """
    map_zone, map_address, map_size = dr.map_info()

    fs_map = Map(b'\0' * map_size)
    fs_map.disc_record = dr
    fs_map.clear()

    map_start = fs_map.disc_to_map(map_address)
    map_end   = fs_map.disc_to_map(map_address + (map_size * 2) - 1) # Two copies

    if map_start[0] != map_end[0]:
        raise RuntimeError("Map spans multiple zones ({} to {}).".format(map_start[0], map_end[0]))

    # Root goes immediately after both map copies, sector-aligned and
    # beyond the last map bit used by the map itself.
    root_address = map_address + (map_size * 2)
    while root_address % dr.secsize != 0 or fs_map.disc_to_map(root_address)[1] <= map_end[1]:
        root_address += 1

    root_zone, root_offset = fs_map.disc_to_map(root_address)
    ids_per_zone = (dr.secsize * 8 - dr.zone_spare) // (dr.idlen + 1)
    root_frag_id = root_zone * ids_per_zone
    root_map_bits = max(dr.idlen, 2048 // dr.bpmb)

    dr.root = (root_frag_id << 8) + 1
    dr.root_size = 2048
    fs_map.disc_record = dr

    fs_map.allocate(0, 2, 0, dr.idlen)
    fs_map.allocate(map_zone, 2, map_start[1], map_end[1])
    fs_map.allocate(root_zone, root_frag_id, root_offset, root_offset + root_map_bits)

    last_zone, overhang_start = fs_map.disc_to_map(dr.disc_size)
    fs_map.allocate(last_zone, 1, overhang_start, dr.secsize * 8 - dr.zone_spare - 1)

    root = BigDir()
    root.parent_id = dr.root

    bootrec = BootBlock(dr)

    disc.write_at(BOOT_BLOCK_ADDRESS, bytes(bootrec))
    disc.write_at(map_address, fs_map.data)
    disc.write_at(map_address + map_size, fs_map.data)
    disc.write_at(root_address, root.data())

    return dict(map_address=map_address, map_size=map_size, root_address=root_address)


def find_allocs(sectors, log2_secsize):
    """Return a dict mapping bpmb (bytes) -> alloc tuple for all valid allocations."""
    allocs = {}
    for log2bpmb in range(7, 26):
        map_bits_needed = (sectors << log2_secsize) // (1 << log2bpmb)
        zones_guess = map_bits_needed // (1 << log2_secsize) // 8
        if zones_guess << log2_secsize > MAPSIZE_MAX:
            continue
        for zones in range(zones_guess, zones_guess + 10 + zones_guess // 20):
            alloc = find_alloc(sectors, log2_secsize, zones, log2bpmb)
            if alloc:
                allocs[1 << log2bpmb] = alloc
                break
    return allocs


def format_disc(disc, sectors, log2_secsize, lfau_kb=None, disc_name="Turnips", bootable=False):
    """Format a Filecore disc from scratch.

    Calculates CHS shape and finds valid allocation parameters, then calls
    write_format.  If lfau_kb is None, prompts interactively.
    Returns the allocs dict (bpmb -> alloc tuple).
    """
    dr = DiscRecord()
    dr.log2secsize = log2_secsize
    dr.disc_size = sectors << log2_secsize
    dr.secspertrack, dr.heads, cylinders = make_shape(sectors)
    dr.log2share = 0
    dr.disc_name = disc_name
    dr.bootoption = 2 if bootable else 0

    print("Disc has {} sectors of {} bytes - Capacity {:.1f} GB".format(
        sectors, 1 << log2_secsize,
        (sectors << log2_secsize) / 1e9))
    print("Using shape {} sectors, {} heads, {} cylinders.".format(
        dr.secspertrack, dr.heads, cylinders))

    allocs = find_allocs(sectors, log2_secsize)

    alloc = allocs.get(lfau_kb * 1024) if lfau_kb else None
    if not alloc:
        for bpmb, a in allocs.items():
            print("LFAU: {}K, map size: {}K ({} zones)".format(
                bpmb // 1024, (a[0] << log2_secsize) // 1024, a[0]))
        alloc = allocs[1024 * int(input("LFAU (in K): "))]

    dr.nzones, dr.zone_spare, dr.log2bpmb, dr.idlen = alloc

    map_zone, map_address, map_size = dr.map_info()
    print("Map zone: {}, address: {}, size: {} ({} map bits)".format(
        map_zone, map_address, map_size, map_size // dr.bpmb))

    info = write_format(disc, dr)

    print("Root address: {}".format(info['root_address']))
    return allocs


def _open_image(path):
    """Open a disc image, choosing DiscImage or HDFImage by file extension."""
    if path.lower().endswith('.hdf'):
        return HDFImage(path, 'rb')
    return DiscImage(path, 'rb')


def _compare_with_image(image_path):
    """Format into a TestDevice and compare byte-by-byte with a reference image.

    Disc geometry and allocation parameters are read from the DiscRecord
    stored in the reference image's boot block.  Only the sectors written
    by write_format are compared (boot block, both map copies, root dir).
    """
    ref = _open_image(image_path)
    ref_map = get_map(ref)

    ref_dr = ref_map.disc_record

    sectors = ref_dr.disc_size >> ref_dr.log2secsize
    sector_size = ref_dr.secsize

    print("Reference: {}".format(image_path))
    print("  {} sectors, {}-byte sectors, nzones={}, bpmb={}, idlen={}, zone_spare={}".format(
        sectors, sector_size,
        ref_dr.nzones, ref_dr.bpmb, ref_dr.idlen, ref_dr.zone_spare))
    print("  disc_name={!r}, root=0x{:08x}, root_size={}".format(
        ref_dr.disc_name, ref_dr.root, ref_dr.root_size))

    # Build a fresh DiscRecord with geometry + allocation from the reference.
    # disc_name is copied so name differences don't obscure structural ones.
    dr = DiscRecord()
    dr.log2secsize = ref_dr.log2secsize
    dr.secspertrack = ref_dr.secspertrack
    dr.heads = ref_dr.heads
    dr.idlen = ref_dr.idlen
    dr.log2bpmb = ref_dr.log2bpmb
    dr.nzones = ref_dr.nzones
    dr.zone_spare = ref_dr.zone_spare
    dr.disc_size = ref_dr.disc_size
    dr.disc_id = ref_dr.disc_id
    dr.disc_name = ref_dr.disc_name
    dr.disctype = ref_dr.disctype
    dr.log2share = ref_dr.log2share
    dr.bootoption = ref_dr.bootoption

    test_dev = TestDevice(sectors, sector_size)
    info = write_format(test_dev, dr)

    map_address = info['map_address']
    map_size = info['map_size']
    root_address = info['root_address']

    regions = [
        (BOOT_BLOCK_ADDRESS, 512,          "boot_block"),
        (map_address,        map_size,     "map_copy_1"),
        (map_address + map_size, map_size, "map_copy_2"),
        (root_address,       2048,         "root_dir"  ),
    ]

    def region_label(addr):
        for start, length, name in regions:
            if start <= addr < start + length:
                return "{} +0x{:04x}".format(name, addr - start)
        return "0x{:08x}".format(addr)

    # Byte offsets to ignore in the boot block:
    # - disc record identity fields (disc_id, disc_name, disctype): not set by a
    #   fresh format and may differ from reference
    # - defects[2..111]: disc-specific; we only verify defects[0] and [1]
    # - checksum: will differ if any of the above are different
    _bb_dr_base = ctypes.sizeof(BootBlock) - ctypes.sizeof(DiscRecord) - 4
    def _bb_dr_field_range(name):
        off = getattr(DiscRecord, name).offset
        size = getattr(DiscRecord, name).size
        base = BOOT_BLOCK_ADDRESS + _bb_dr_base
        return range(base + off, base + off + size)
    _defect_entry_size = ctypes.sizeof(ctypes.c_uint32)
    _ignored_addrs = set()
    for _f in ('disc_id', '_disc_name', 'disctype'):
        _ignored_addrs.update(_bb_dr_field_range(_f))
    # defects[2] onwards (defects array starts at offset 0 in BootBlock)
    _ignored_addrs.update(range(BOOT_BLOCK_ADDRESS + 2 * _defect_entry_size,
                                BOOT_BLOCK_ADDRESS + 112 * _defect_entry_size))
    # checksum (last byte of boot block)
    _ignored_addrs.add(BOOT_BLOCK_ADDRESS + ctypes.sizeof(BootBlock) - 1)

    total_diffs = 0
    for (address, data) in test_dev._writes:
        ref_data = bytes(ref.read_at(address, len(data)))
        if data == ref_data:
            continue
        for i, (b_wrote, b_ref) in enumerate(zip(data, ref_data)):
            if b_wrote != b_ref:
                if address + i in _ignored_addrs:
                    continue
                print("0x{:08x} [{}]: wrote=0x{:02x} ref=0x{:02x}".format(
                    address + i, region_label(address + i), b_wrote, b_ref))
                total_diffs += 1

    if total_diffs == 0:
        print("No differences found.")
    else:
        print("\n{} byte(s) differ.".format(total_diffs))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("device", nargs='?',
                        help="Output device or image file (not used with --compare)")
    parser.add_argument("sectors", type=int, nargs='?',
                        help="Total number of sectors on the disc")
    parser.add_argument("--4k", dest="bigsecs", action="store_true",
                        help="Use 4096-byte sectors instead of 512")
    parser.add_argument("--lfau", type=int, metavar="K",
                        help="LFAU size in kilobytes")
    parser.add_argument("--compare", metavar="IMAGE",
                        help="Compare TestDevice output against a reference image "
                             "instead of writing to a real device")
    parser.add_argument("--bootable", action="store_true",
                        help="Set bootoption=2 (auto-boot) in the disc record")

    args = parser.parse_args()

    if args.compare:
        _compare_with_image(args.compare)
    else:
        if not args.device or args.sectors is None:
            parser.error("device and sectors are required unless --compare is used")
        log2_secsize = 12 if args.bigsecs else 9
        disc = DiscImage(args.device, 'w+b')
        format_disc(disc, args.sectors, log2_secsize, args.lfau, bootable=args.bootable)
