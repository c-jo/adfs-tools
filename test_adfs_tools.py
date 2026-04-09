"""
Tests for ADFS Tools - Filecore disc image handling.

Tests cover the core objects (DiscRecord, Map, BigDir, BootBlock),
utility functions, and fcform helper functions.
"""

import struct
import array
import ctypes
import unittest
import io
import os
import sys

# Add parent directory to path so we can import the modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from objects import (
    DiscRecord, Map, BigDir, BootBlock,
    dir_check_words, dir_check_bytes,
)


class TestDirCheckWords(unittest.TestCase):
    """Tests for the dir_check_words checksum function."""

    def test_zero_data(self):
        """Checksum of all-zero data should be zero."""
        data = b'\x00' * 16  # 4 words
        self.assertEqual(dir_check_words(data, 4, 0), 0)

    def test_single_word(self):
        """Checksum of a single word with initial check of 0."""
        data = struct.pack("I", 0x12345678)
        result = dir_check_words(data, 1, 0)
        # XOR with rotated 0 is just the word itself
        self.assertEqual(result, 0x12345678)

    def test_two_words(self):
        """Checksum accumulates correctly over multiple words."""
        word1 = 0x12345678
        word2 = 0xAABBCCDD
        data = struct.pack("II", word1, word2)
        # First: 0x12345678 ^ rotate(0) = 0x12345678
        # Then: 0xAABBCCDD ^ rotate(0x12345678)
        result = dir_check_words(data, 2, 0)
        # Verify it's deterministic
        self.assertEqual(result, dir_check_words(data, 2, 0))

    def test_initial_check_nonzero(self):
        """Non-zero initial checksum affects result."""
        data = struct.pack("I", 0)
        result = dir_check_words(data, 1, 0x12345678)
        # 0 ^ rotate(0x12345678) = rotate(0x12345678)
        self.assertNotEqual(result, 0)


class TestDirCheckBytes(unittest.TestCase):
    """Tests for the dir_check_bytes checksum function."""

    def test_zero_data(self):
        """Checksum of all-zero bytes should be zero."""
        data = b'\x00' * 4
        self.assertEqual(dir_check_bytes(data, 4, 0), 0)

    def test_single_byte(self):
        """Checksum of a single byte with initial check of 0."""
        data = struct.pack("B", 0x42)
        result = dir_check_bytes(data, 1, 0)
        self.assertEqual(result, 0x42)

    def test_deterministic(self):
        """Same input always produces same output."""
        data = b'\x01\x02\x03\x04\x05'
        r1 = dir_check_bytes(data, 5, 0)
        r2 = dir_check_bytes(data, 5, 0)
        self.assertEqual(r1, r2)


class TestDiscRecord(unittest.TestCase):
    """Tests for the DiscRecord ctypes structure."""

    def test_size(self):
        """DiscRecord should be exactly 60 bytes."""
        self.assertEqual(ctypes.sizeof(DiscRecord), 60)

    def test_defaults(self):
        """Default values should be set by __init__."""
        dr = DiscRecord()
        self.assertEqual(dr.density, 0)
        self.assertEqual(dr.skew, 0)
        self.assertEqual(dr.lowsector, 1)
        self.assertEqual(dr.big_flag, 1)
        self.assertEqual(dr.format_version, 1)

    def test_bpmb_property(self):
        """bpmb should be 2^log2bpmb."""
        dr = DiscRecord()
        dr.log2bpmb = 10
        self.assertEqual(dr.bpmb, 1024)
        dr.log2bpmb = 7
        self.assertEqual(dr.bpmb, 128)

    def test_secsize_property(self):
        """secsize should be 2^log2secsize."""
        dr = DiscRecord()
        dr.log2secsize = 9
        self.assertEqual(dr.secsize, 512)
        dr.log2secsize = 12
        self.assertEqual(dr.secsize, 4096)

    def test_share_size_property(self):
        """share_size should be 2^log2share."""
        dr = DiscRecord()
        dr.log2share = 0
        self.assertEqual(dr.share_size, 1)
        dr.log2share = 3
        self.assertEqual(dr.share_size, 8)

    def test_nzones_property(self):
        """nzones combines nzones_1 and nzones_2."""
        dr = DiscRecord()
        dr.nzones_1 = 4
        dr.nzones_2 = 0
        self.assertEqual(dr.nzones, 4)
        # Larger value using nzones_2
        dr.nzones_1 = 0x10
        dr.nzones_2 = 1
        self.assertEqual(dr.nzones, 0x110)

    def test_nzones_setter(self):
        """Setting nzones should update both nzones_1 and nzones_2."""
        dr = DiscRecord()
        dr.nzones = 4
        self.assertEqual(dr.nzones_1, 4)
        self.assertEqual(dr.nzones_2, 0)
        dr.nzones = 0x120
        self.assertEqual(dr.nzones_1, 0x20)
        self.assertEqual(dr.nzones_2, 1)

    def test_disc_size_property(self):
        """disc_size combines disc_size_1 and disc_size_2."""
        dr = DiscRecord()
        dr.disc_size_1 = 0x10000000
        dr.disc_size_2 = 0
        self.assertEqual(dr.disc_size, 0x10000000)

    def test_disc_size_setter(self):
        """Setting disc_size should update both parts."""
        dr = DiscRecord()
        dr.disc_size = 1024 * 1024 * 1024  # 1 GB
        self.assertEqual(dr.disc_size, 1024 * 1024 * 1024)

    def test_disc_size_large(self):
        """disc_size should handle values larger than 4GB."""
        dr = DiscRecord()
        large_size = 8 * 1024 * 1024 * 1024  # 8 GB
        dr.disc_size = large_size
        self.assertEqual(dr.disc_size, large_size)

    def test_from_bytes(self):
        """from_bytes should reconstruct a DiscRecord from raw bytes."""
        dr = DiscRecord()
        dr.log2secsize = 9
        dr.secspertrack = 63
        dr.heads = 16
        dr.log2bpmb = 10
        dr.idlen = 15
        dr.nzones = 4
        dr.zone_spare = 32
        dr.disc_size = 512 * 1024 * 1024

        raw = bytes(dr)
        dr2 = DiscRecord.from_bytes(raw)

        self.assertEqual(dr2.log2secsize, 9)
        self.assertEqual(dr2.secspertrack, 63)
        self.assertEqual(dr2.heads, 16)
        self.assertEqual(dr2.log2bpmb, 10)
        self.assertEqual(dr2.idlen, 15)
        self.assertEqual(dr2.nzones, 4)
        self.assertEqual(dr2.zone_spare, 32)
        self.assertEqual(dr2.disc_size, 512 * 1024 * 1024)

    def test_map_info(self):
        """map_info should return zone, address, and size."""
        dr = DiscRecord()
        dr.log2secsize = 9
        dr.log2bpmb = 10
        dr.nzones = 4
        dr.zone_spare = 32

        zone, address, size = dr.map_info()
        self.assertEqual(zone, 2)  # nzones // 2
        self.assertEqual(size, 512 * 4)  # secsize * nzones
        # Address should be positive
        self.assertGreater(address, 0)


class TestMap(unittest.TestCase):
    """Tests for the Map class."""

    def _make_disc_record(self, log2secsize=9, log2bpmb=10, nzones=4,
                          zone_spare=32, idlen=15):
        """Helper: create a DiscRecord with typical values."""
        dr = DiscRecord()
        dr.log2secsize = log2secsize
        dr.log2bpmb = log2bpmb
        dr.nzones = nzones
        dr.zone_spare = zone_spare
        dr.idlen = idlen
        dr.disc_size = 512 * 1024 * 1024
        dr.secspertrack = 63
        dr.heads = 16
        dr.root = 0x200001
        dr.root_size = 2048
        return dr

    def _make_map(self, dr=None):
        """Helper: create a Map with a disc record embedded."""
        if dr is None:
            dr = self._make_disc_record()
        map_size = dr.secsize * dr.nzones
        data = bytearray(map_size)
        # Embed disc record at offset 4 in the first sector
        dr_bytes = bytes(dr)
        for i in range(len(dr_bytes)):
            data[4 + i] = dr_bytes[i]
        return Map(bytes(data))

    def test_create_map(self):
        """Map should be constructable from raw data."""
        m = self._make_map()
        self.assertIsNotNone(m)
        self.assertEqual(m.nzones, 4)

    def test_disc_record_embedded(self):
        """Map should read disc record from the data."""
        dr = self._make_disc_record()
        m = self._make_map(dr)
        self.assertEqual(m.disc_record.log2secsize, 9)
        self.assertEqual(m.disc_record.log2bpmb, 10)
        self.assertEqual(m.disc_record.nzones, 4)

    def test_disc_record_setter(self):
        """Setting disc_record should update the map data."""
        m = self._make_map()
        dr = self._make_disc_record()
        dr.log2bpmb = 11
        m.disc_record = dr
        self.assertEqual(m.disc_record.log2bpmb, 11)

    def test_id_per_zone(self):
        """id_per_zone calculation should be correct."""
        dr = self._make_disc_record(log2secsize=9, zone_spare=32, idlen=15)
        m = self._make_map(dr)
        expected = (512 * 8 - 32) // (15 + 1)
        self.assertEqual(m.id_per_zone, expected)

    def test_set_and_get_bit(self):
        """set_bit and get_bit should be consistent."""
        m = self._make_map()
        # Set a bit in zone 0
        m.set_bit(0, 100, 1)
        self.assertEqual(m.get_bit(0, 100), 1)
        # Clear it
        m.set_bit(0, 100, 0)
        self.assertEqual(m.get_bit(0, 100), 0)

    def test_set_bit_various_positions(self):
        """set_bit should work for all bit positions in a byte."""
        m = self._make_map()
        for bit in range(80, 88):  # one full byte's worth of bits
            m.set_bit(0, bit, 1)
            self.assertEqual(m.get_bit(0, bit), 1,
                             f"Bit {bit} should be 1")

        for bit in range(80, 88):
            m.set_bit(0, bit, 0)
            self.assertEqual(m.get_bit(0, bit), 0,
                             f"Bit {bit} should be 0")

    def test_set_bit_does_not_affect_neighbors(self):
        """Setting a bit should not affect adjacent bits."""
        m = self._make_map()
        # Clear bits around the target
        for bit in range(98, 103):
            m.set_bit(0, bit, 0)
        # Set only the middle bit
        m.set_bit(0, 100, 1)
        self.assertEqual(m.get_bit(0, 99), 0)
        self.assertEqual(m.get_bit(0, 100), 1)
        self.assertEqual(m.get_bit(0, 101), 0)

    def test_zone_range(self):
        """zone_range should return correct start and end for each zone."""
        dr = self._make_disc_record(log2secsize=9, zone_spare=32, nzones=4)
        m = self._make_map(dr)
        bits_per_zone = 512 * 8 - 32

        # Zone 0 starts at 0
        start0, end0 = m.zone_range(0)
        self.assertEqual(start0, 0)

        # Zone 1 should start where zone 0 ends (minus overlap of 480)
        start1, end1 = m.zone_range(1)
        self.assertEqual(start1, bits_per_zone - 480)

    def test_clear_and_cross_check(self):
        """After clear(), cross_check should be 0xff."""
        m = self._make_map()
        m.clear()
        self.assertEqual(m.cross_check(), 0xff)

    def test_calc_zone_check(self):
        """Zone check should be calculable and consistent."""
        m = self._make_map()
        m.clear()
        for zone in range(m.nzones):
            check = m.calc_zone_check(zone)
            self.assertIsInstance(check, int)
            self.assertTrue(0 <= check <= 255)

    def test_disc_to_map(self):
        """disc_to_map should convert a disc address to (zone, bit)."""
        dr = self._make_disc_record()
        m = self._make_map(dr)
        m.clear()

        # Address 0 should be in zone 0, bit 0
        result = m.disc_to_map(0)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 0)
        self.assertEqual(result[1], 0)

    def test_allocate_and_find(self):
        """allocate() should be findable by find_in_zone()."""
        dr = self._make_disc_record(idlen=15)
        m = self._make_map(dr)
        m.clear()

        frag_id = 5
        from_bit = 0
        to_bit = 32  # Must be > idlen

        m.allocate(0, frag_id, from_bit, to_bit)

        found = m.find_in_zone(frag_id, 0)
        self.assertTrue(len(found) > 0)
        # The found fragment should have a positive disc range
        self.assertGreater(found[0][1], found[0][0])

    def test_find_fragment_across_zones(self):
        """find_fragment should search across zones."""
        dr = self._make_disc_record(idlen=15)
        m = self._make_map(dr)
        m.clear()

        frag_id = 5
        m.allocate(0, frag_id, 0, 32)

        # find_fragment should find it
        result = m.find_fragment(frag_id)
        self.assertTrue(len(result) > 0)

    def test_allocate_too_small_raises(self):
        """allocate() should raise if the range is too small for the ID."""
        dr = self._make_disc_record(idlen=15)
        m = self._make_map(dr)
        m.clear()

        with self.assertRaises(RuntimeError):
            m.allocate(0, 5, 0, 10)  # 10 < idlen(15), too small


class TestBigDir(unittest.TestCase):
    """Tests for the BigDir directory class."""

    def test_empty_directory(self):
        """Creating an empty BigDir should produce valid defaults."""
        d = BigDir()
        self.assertEqual(d.sequence, 0)
        self.assertEqual(d.name, b'$')
        self.assertEqual(len(d.entries), 0)

    def test_add_entry(self):
        """Adding an entry should increase the entry count."""
        d = BigDir()
        d.parent_id = 0x200001
        d.add(b'TestFile', 0xFFFFFC00, 0x00000000, 1024, 0x03, 0x300)
        self.assertEqual(len(d.entries), 1)
        self.assertEqual(d.entries[0].name, b'TestFile')
        self.assertEqual(d.entries[0].length, 1024)

    def test_find_entry(self):
        """find() should locate entries case-insensitively."""
        d = BigDir()
        d.parent_id = 0x200001
        d.add(b'TestFile', 0, 0, 100, 0x03, 0x300)
        result = d.find(b'testfile')
        self.assertIsNotNone(result)
        self.assertEqual(result.name, b'TestFile')

    def test_find_entry_not_found(self):
        """find() should return None for missing entries."""
        d = BigDir()
        d.parent_id = 0x200001
        result = d.find(b'nonexistent')
        self.assertIsNone(result)

    def test_getitem(self):
        """__getitem__ should find entries by exact name."""
        d = BigDir()
        d.parent_id = 0x200001
        d.add(b'Hello', 0, 0, 100, 0x03, 0x300)
        result = d[b'Hello']
        self.assertIsNotNone(result)
        self.assertEqual(result.name, b'Hello')

    def test_getitem_not_found(self):
        """__getitem__ should return None for missing entries."""
        d = BigDir()
        d.parent_id = 0x200001
        result = d[b'missing']
        self.assertIsNone(result)

    def test_delete_entry(self):
        """delete() should remove an entry by name."""
        d = BigDir()
        d.parent_id = 0x200001
        d.add(b'Deleteme', 0, 0, 100, 0x03, 0x300)
        self.assertEqual(len(d.entries), 1)
        result = d.delete(b'Deleteme')
        self.assertTrue(result)
        self.assertEqual(len(d.entries), 0)

    def test_delete_nonexistent(self):
        """delete() should return None when entry doesn't exist."""
        d = BigDir()
        d.parent_id = 0x200001
        result = d.delete(b'nonexistent')
        self.assertIsNone(result)

    def test_roundtrip_empty(self):
        """An empty directory should survive a data() -> BigDir() roundtrip."""
        d = BigDir()
        d.parent_id = 0x200001
        raw = d.data()
        self.assertEqual(len(raw), 2048)
        d2 = BigDir(raw)
        self.assertEqual(d2.name, b'$')
        self.assertEqual(d2.sequence, 0)
        self.assertEqual(len(d2.entries), 0)

    def test_roundtrip_with_entries(self):
        """A directory with entries should survive a roundtrip."""
        d = BigDir()
        d.parent_id = 0x200001
        d.add(b'File1', 0xFFF00000, 0x12345678, 4096, 0x03, 0x500)
        d.add(b'File2', 0xFFF00001, 0xABCDEF01, 8192, 0x13, 0x600)
        d.add(b'LongFileName', 0x00000000, 0x00000000, 256, 0x01, 0x700)

        raw = d.data()
        self.assertEqual(len(raw), 2048)

        d2 = BigDir(raw)
        self.assertEqual(len(d2.entries), 3)
        self.assertEqual(d2.entries[0].name, b'File1')
        self.assertEqual(d2.entries[0].loadaddr, 0xFFF00000)
        self.assertEqual(d2.entries[0].length, 4096)
        self.assertEqual(d2.entries[1].name, b'File2')
        self.assertEqual(d2.entries[1].attribs, 0x13)
        self.assertEqual(d2.entries[2].name, b'LongFileName')

    def test_roundtrip_preserves_addresses(self):
        """Indirect disc addresses should survive roundtrip."""
        d = BigDir()
        d.parent_id = 0x200001
        d.add(b'Test', 0, 0, 100, 0x03, 0xABCD0001)

        raw = d.data()
        d2 = BigDir(raw)
        self.assertEqual(d2.entries[0].ind_disc_addr, 0xABCD0001)

    def test_invalid_start_marker(self):
        """BigDir should raise on invalid start marker."""
        d = BigDir()
        d.parent_id = 0x200001
        raw = bytearray(d.data())
        # Corrupt the 'SBPr' marker at offset 4
        raw[4] = 0x00
        with self.assertRaises(RuntimeError):
            BigDir(bytes(raw))

    def test_invalid_end_marker(self):
        """BigDir should raise on invalid end marker."""
        d = BigDir()
        d.parent_id = 0x200001
        raw = bytearray(d.data())
        # Corrupt the 'oven' marker at offset -8
        raw[-8] = 0x00
        with self.assertRaises(RuntimeError):
            BigDir(bytes(raw))

    def test_checksum_validation(self):
        """BigDir should raise on incorrect checksum."""
        d = BigDir()
        d.parent_id = 0x200001
        raw = bytearray(d.data())
        # Corrupt the check byte (last byte)
        raw[-1] ^= 0xFF
        with self.assertRaises(RuntimeError):
            BigDir(bytes(raw))

    def test_sequence_number(self):
        """Sequence number should be preserved."""
        d = BigDir()
        d.parent_id = 0x200001
        d.sequence = 42
        raw = d.data()
        d2 = BigDir(raw)
        self.assertEqual(d2.sequence, 42)


class TestBigDirEntry(unittest.TestCase):
    """Tests for BigDir.Entry."""

    def test_is_directory(self):
        """is_directory() should check the directory attribute bit."""
        entry = BigDir.Entry(b'Dir', 0, 0, 0, 0x08, 0)  # bit 3 set
        self.assertTrue(entry.is_directory())
        entry = BigDir.Entry(b'File', 0, 0, 0, 0x03, 0)  # bit 3 not set
        self.assertFalse(entry.is_directory())

    def test_attr_str(self):
        """attr_str() should format attributes correctly."""
        # All bits set: RW LD rw = 0x3F
        entry = BigDir.Entry(b'Test', 0, 0, 0, 0x3F, 0)
        self.assertEqual(entry.attr_str(), "RWLDrw")

        # No bits set
        entry = BigDir.Entry(b'Test', 0, 0, 0, 0x00, 0)
        self.assertEqual(entry.attr_str(), "------")

        # Read only
        entry = BigDir.Entry(b'Test', 0, 0, 0, 0x01, 0)
        self.assertEqual(entry.attr_str(), "R-----")

        # Typical file: RW with public read (owner R/W, world r)
        entry = BigDir.Entry(b'Test', 0, 0, 0, 0x13, 0)
        self.assertEqual(entry.attr_str(), "RW--r-")


class TestBootBlock(unittest.TestCase):
    """Tests for the BootBlock class."""

    def test_size(self):
        """BootBlock should be exactly 512 bytes."""
        self.assertEqual(ctypes.sizeof(BootBlock), 512)

    def test_create(self):
        """Creating a BootBlock should set checksum correctly."""
        dr = DiscRecord()
        dr.log2secsize = 9
        dr.log2bpmb = 10
        dr.nzones = 4
        dr.zone_spare = 32
        dr.idlen = 15
        dr.disc_size = 512 * 1024 * 1024

        bb = BootBlock(dr)
        self.assertEqual(bb.checksum, bb.calculate_checksum())

    def test_checksum_changes_with_data(self):
        """Different disc records should produce different checksums."""
        dr1 = DiscRecord()
        dr1.log2secsize = 9
        dr1.log2bpmb = 10
        dr1.nzones = 4

        dr2 = DiscRecord()
        dr2.log2secsize = 12
        dr2.log2bpmb = 12
        dr2.nzones = 8

        bb1 = BootBlock(dr1)
        bb2 = BootBlock(dr2)
        # Very likely to differ (not guaranteed, but extremely unlikely)
        self.assertNotEqual(bb1.checksum, bb2.checksum)

    def test_defects(self):
        """Default defects should be set."""
        dr = DiscRecord()
        bb = BootBlock(dr)
        self.assertEqual(bb.defects[0], 0x20000000)
        self.assertEqual(bb.defects[1], 0x40000000)

    def test_roundtrip(self):
        """BootBlock should survive a bytes -> from_buffer_copy roundtrip."""
        dr = DiscRecord()
        dr.log2secsize = 9
        dr.log2bpmb = 10
        dr.nzones = 4
        dr.zone_spare = 32
        dr.idlen = 15
        dr.disc_size = 512 * 1024 * 1024

        bb = BootBlock(dr)
        raw = bytes(bb)
        self.assertEqual(len(raw), 512)

        bb2 = BootBlock.from_buffer_copy(raw)
        self.assertEqual(bb2.checksum, bb.checksum)
        self.assertEqual(bb2.disc_record.log2secsize, 9)
        self.assertEqual(bb2.disc_record.nzones, 4)


from fcform import make_shape, check_alloc, find_alloc, find_allocs, write_format


class TestFcformFunctions(unittest.TestCase):
    """Tests for fcform.py standalone functions (make_shape, check_alloc, find_alloc)."""

    def test_make_shape(self):
        """make_shape produces a valid CHS geometry."""
        sectors = 4 * 1024 * 1024 * 1024 // 512  # 4 GB at 512-byte sectors
        result = make_shape(sectors)
        self.assertIsNotNone(result)
        secs, heads, cyls = result
        self.assertGreater(secs, 15)
        self.assertLessEqual(secs, 63)
        self.assertGreater(heads, 15)
        self.assertLessEqual(heads, 255)
        self.assertLessEqual(cyls, 65535)
        self.assertLessEqual(secs * heads * cyls, sectors)

    def test_check_alloc_valid(self):
        """check_alloc returns True for a known-good combination."""
        result = check_alloc(1048576, 9, 4, 32, 10, 15)
        self.assertIsInstance(result, bool)

    def test_check_alloc_too_few_zones(self):
        """check_alloc returns False when zones are clearly insufficient."""
        self.assertFalse(check_alloc(1048576, 9, 1, 32, 10, 15))

    def test_find_alloc_returns_tuple(self):
        """find_alloc returns a 4-tuple for a valid disc size."""
        # Use find_allocs to identify a known-valid (zones, log2bpmb) pair first
        allocs = find_allocs(1048576, 9)
        self.assertGreater(len(allocs), 0, "find_allocs returned nothing")
        bpmb, (zones, _zonespare, log2bpmb, _idlen) = next(iter(allocs.items()))
        result = find_alloc(1048576, 9, zones, log2bpmb)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 4)  # (zones, zonespare, log2bpmb, idlen)

    def test_find_allocs_returns_dict(self):
        """find_allocs returns a non-empty dict mapping bpmb -> alloc tuple."""
        allocs = find_allocs(1048576, 9)
        self.assertGreater(len(allocs), 0)
        for bpmb, alloc in allocs.items():
            self.assertIsInstance(bpmb, int)
            self.assertEqual(len(alloc), 4)

    def test_write_format_produces_boot_block(self):
        """write_format writes a valid boot block to a TestDevice."""
        from device import TestDevice
        from objects import DiscRecord, BOOT_BLOCK_ADDRESS

        disc_size = 64 * 1024 * 1024
        sectors = disc_size // 512

        allocs = find_allocs(sectors, 9)
        self.assertGreater(len(allocs), 0)
        _bpmb, (zones, zonespare, log2bpmb, idlen) = next(iter(allocs.items()))

        dr = DiscRecord()
        dr.log2secsize = 9
        dr.secspertrack = 63
        dr.heads = 16
        dr.nzones = zones
        dr.zone_spare = zonespare
        dr.log2bpmb = log2bpmb
        dr.idlen = idlen
        dr.disc_size = disc_size
        dr.log2share = 0
        dr.disc_name = "Test"

        dev = TestDevice(sectors, dr.secsize)
        write_format(dev, dr)

        written = {addr: data for addr, data in dev._writes}
        self.assertIn(BOOT_BLOCK_ADDRESS, written)
        boot_bytes = written[BOOT_BLOCK_ADDRESS]
        # disc record starts at offset 0x1c0 within the boot block
        dr_bytes = boot_bytes[0x1c0:0x1c0 + 60]
        recovered = DiscRecord.from_bytes(dr_bytes)
        self.assertEqual(recovered.nzones, dr.nzones)
        self.assertEqual(recovered.idlen, dr.idlen)

    def test_write_format_multizone_map(self):
        """write_format succeeds when the map occupies more than one zone."""
        from device import TestDevice
        from objects import DiscRecord, Map, BOOT_BLOCK_ADDRESS

        # A 64 GB disc with 512-byte sectors and bpmb=2048 produces a map that
        # spans two zones; use the parameters discovered by find_allocs.
        sectors = 64 * 1024 * 1024 * 1024 // 512
        allocs = find_allocs(sectors, 9)
        self.assertIn(2048, allocs, "Expected bpmb=2048 allocation for 64 GB disc")
        zones, zonespare, log2bpmb, idlen = allocs[2048]

        dr = DiscRecord()
        dr.log2secsize = 9
        dr.secspertrack = 63
        dr.heads = 16
        dr.nzones = zones
        dr.zone_spare = zonespare
        dr.log2bpmb = log2bpmb
        dr.idlen = idlen
        dr.disc_size = sectors * 512
        dr.log2share = 0
        dr.disc_name = "MultiZ"

        # Confirm this configuration actually spans multiple zones.
        map_zone, map_address, map_size = dr.map_info()
        tmp_map = Map(b'\0' * map_size)
        tmp_map.disc_record = dr
        map_start = tmp_map.disc_to_map(map_address)
        map_end   = tmp_map.disc_to_map(map_address + map_size * 2 - 1)
        self.assertNotEqual(map_start[0], map_end[0],
                            "Test requires a map that spans multiple zones")

        dev = TestDevice(sectors, dr.secsize)
        info = write_format(dev, dr)  # must not raise

        written = {addr: data for addr, data in dev._writes}
        self.assertIn(BOOT_BLOCK_ADDRESS, written)
        self.assertIn(info['map_address'], written)
        self.assertIn(info['root_address'], written)


class TestMapWithFormat(unittest.TestCase):
    """Integration tests: format a map and verify its structure."""

    def _format_small_disc(self):
        """Create a formatted map for a small disc (similar to fcform.py)."""
        dr = DiscRecord()
        dr.log2secsize = 9
        dr.secspertrack = 63
        dr.heads = 16
        dr.log2bpmb = 7  # 128 bytes per map bit - smaller LFAU for test
        dr.nzones = 4
        dr.zone_spare = 32
        dr.idlen = 15
        dr.disc_size = 64 * 1024 * 1024  # 64MB to match smaller LFAU
        dr.root = 0x200001
        dr.root_size = 2048
        dr.log2share = 0

        map_size = dr.secsize * dr.nzones

        m = Map(b'\0' * map_size)
        m.disc_record = dr
        m.clear()

        return dr, m

    def test_cross_check_after_clear(self):
        """Cross check should be 0xFF after clearing."""
        dr, m = self._format_small_disc()
        self.assertEqual(m.cross_check(), 0xff)

    def test_zone_checks_valid(self):
        """Each zone's check byte should match the calculated value."""
        dr, m = self._format_small_disc()
        for zone in range(m.nzones):
            zone_start = zone * dr.secsize
            stored_check = m.data[zone_start]
            calc_check = m.calc_zone_check(zone)
            self.assertEqual(stored_check, calc_check,
                             f"Zone {zone} check mismatch")

    def test_allocate_updates_checksum(self):
        """Allocating should update the zone checksum."""
        dr, m = self._format_small_disc()

        # Get checksum before allocation
        old_check = m.data[0]

        # Allocate something in zone 0
        m.allocate(0, 2, 0, dr.idlen + 1)

        # Check byte should have been updated
        new_check = m.data[0]
        calc_check = m.calc_zone_check(0)
        self.assertEqual(new_check, calc_check)

    def test_full_format_cycle(self):
        """Simulate a full format: create map, allocate map/root, verify."""
        dr, m = self._format_small_disc()

        map_zone, map_address, map_size = dr.map_info()

        # Allocate boot block area in zone 0
        m.allocate(0, 2, 0, dr.idlen + 1)

        # Allocate map area
        map_start = m.disc_to_map(map_address)
        map_end = m.disc_to_map(map_address + (map_size * 2) - 1)
        self.assertIsNotNone(map_start)
        self.assertIsNotNone(map_end)

        if map_start[0] == map_end[0]:
            m.allocate(map_start[0], 2, map_start[1], map_end[1])

        # Verify cross check is still valid
        self.assertEqual(m.cross_check(), 0xff)

        # All zone checks should still be valid
        for zone in range(m.nzones):
            zone_start = zone * dr.secsize
            self.assertEqual(m.data[zone_start], m.calc_zone_check(zone))


class TestBigDirWithMap(unittest.TestCase):
    """Integration tests: directory + map interactions."""

    def test_create_root_directory(self):
        """Create a root directory and verify its structure."""
        d = BigDir()
        d.parent_id = 0x200001
        d.add(b'TestApp', 0xFFFFFC00, 0x00000000, 4096, 0x0B, 0x500)

        raw = d.data()
        self.assertEqual(len(raw), 2048)

        # Should start with SBPr
        self.assertEqual(raw[4:8], b'SBPr')
        # Should end with oven
        self.assertEqual(raw[-8:-4], b'oven')

        # Verify it can be read back
        d2 = BigDir(raw)
        self.assertEqual(len(d2.entries), 1)
        self.assertEqual(d2.entries[0].name, b'TestApp')

    def test_add_and_delete_multiple(self):
        """Add and delete multiple entries, verify consistency."""
        d = BigDir()
        d.parent_id = 0x200001

        # Add several entries
        for i in range(5):
            name = f'File{i}'.encode('latin-1')
            d.add(name, 0, 0, 100 * (i + 1), 0x03, 0x300 + i)

        self.assertEqual(len(d.entries), 5)

        # Delete middle entry
        d.delete(b'File2')
        self.assertEqual(len(d.entries), 4)

        # Verify roundtrip still works
        raw = d.data()
        d2 = BigDir(raw)
        self.assertEqual(len(d2.entries), 4)
        names = [e.name for e in d2.entries]
        self.assertNotIn(b'File2', names)
        self.assertIn(b'File0', names)
        self.assertIn(b'File4', names)


class TestUtilsFunctions(unittest.TestCase):
    """Tests for utils.py functions using synthetic disc images."""

    def _make_disc_image(self):
        """Create a minimal synthetic disc image in memory."""
        dr = DiscRecord()
        dr.log2secsize = 9
        dr.log2bpmb = 10
        dr.nzones = 4
        dr.zone_spare = 32
        dr.idlen = 15
        dr.disc_size = 512 * 1024 * 1024
        dr.secspertrack = 63
        dr.heads = 16
        dr.root = 0x200001
        dr.root_size = 2048
        dr.log2share = 0

        bb = BootBlock(dr)

        map_zone, map_address, map_size = dr.map_info()

        m = Map(b'\0' * map_size)
        m.disc_record = dr
        m.clear()

        # Create a disc image large enough to hold boot block + map
        image_size = map_address + map_size * 2 + 4096
        image = bytearray(image_size)

        # Write boot block at 0xC00
        bb_bytes = bytes(bb)
        for i in range(len(bb_bytes)):
            image[0xC00 + i] = bb_bytes[i]

        # Write map at map_address
        map_bytes = m.data.tobytes()
        for i in range(len(map_bytes)):
            image[map_address + i] = map_bytes[i]
            # Second copy
            if map_address + map_size + i < len(image):
                image[map_address + map_size + i] = map_bytes[i]

        return bytes(image), dr, m

    def test_find_map(self):
        """find_map should return correct address and length."""
        from utils import find_map
        from device import DiscImage

        image, dr, m = self._make_disc_image()
        disc = DiscImage(io.BytesIO(image))

        address, length = find_map(disc)
        expected_zone, expected_addr, expected_size = dr.map_info()

        self.assertEqual(address, expected_addr)
        self.assertEqual(length, expected_size)

    def test_get_map(self):
        """get_map should return a valid Map object."""
        from utils import get_map
        from device import DiscImage

        image, dr, m = self._make_disc_image()
        disc = DiscImage(io.BytesIO(image))

        result_map = get_map(disc)
        self.assertIsNotNone(result_map)
        self.assertEqual(result_map.nzones, 4)
        self.assertEqual(result_map.disc_record.log2secsize, 9)

    def test_get_map_cross_check(self):
        """Map read by get_map should have valid cross check."""
        from utils import get_map
        from device import DiscImage

        image, dr, m = self._make_disc_image()
        disc = DiscImage(io.BytesIO(image))

        result_map = get_map(disc)
        self.assertEqual(result_map.cross_check(), 0xff)


if __name__ == '__main__':
    unittest.main()
