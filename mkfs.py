#! /usr/bin/python
from itertools import product

from objects import DiscRecord
import struct

ZONE0BITS = 60*8 # Bits used in Zone 0
IDLEN_MAX = 21
MAPSIZE_MAX = 32*1024*1024 # 32MB

"""
#define LOG2SECTORSIZE 10
#define LOG2BPMB_MIN  (7)
#define LOG2BPMB_MAX  (12)
#define ZONESPARE_MIN (32)
#define ZONESPARE_MAX (64)
#define ZONES_MIN     (1)
#define ZONES_MAX     (127)
#define IDLEN_MIN     (LOG2SECTORSIZE + 3)
#define IDLEN_MAX   (19)

#define NEWDIR_SIZE 0x800
"""

####
#disc_sectors = 234441648
#log2_secsize = 9
####
disc_sectors = 1953525168>>3 # Convert to 4K
log2_secsize = 12
####

def make_shape(sectors):
    """Generate a CHS shape for a given number of sectors."""
    best_wasted = 0xffffffff
    best = None
    for secs,heads in product(range(63,15,-1), range(255,15,-1)):
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
    idpz = bpzm / (idlen+1) # IDs per Zone

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
        for idlen in range(log2_secsize, IDLEN_MAX+1):
            if check_alloc(sectors, log2ss, zones, zonespare, log2bpmb, idlen):
                return (zones, zonespare, log2bpmb, idlen)


print("Disc has {} sectors of {} bytes - Capacity {:.1f} GB".format(
     disc_sectors, 1<<log2_secsize,
     (disc_sectors << log2_secsize)/1000/1000/1000))

allocs = []

# Find what log2 bpmb / zones combinations we can use
for log2bpmb in range(7,26):
    # Roughly how many zones we need
    map_bits_needed = (disc_sectors << log2_secsize) // (1 << log2bpmb)
    zones_guess = map_bits_needed // (1 << log2_secsize) // 8
    if zones_guess << log2_secsize > MAPSIZE_MAX:
        continue

    for zones in range(zones_guess, zones_guess + 10 + zones_guess // 20): 
        alloc = find_alloc(disc_sectors, log2_secsize, zones, log2bpmb)
        if alloc:
            allocs.append(alloc)
            break

for alloc in allocs:
     print("LFAU: {}K, map size: {}K ({} zones)".format((1<<alloc[2])/1024, (alloc[0]<<log2_secsize)/1024, alloc[0]))

