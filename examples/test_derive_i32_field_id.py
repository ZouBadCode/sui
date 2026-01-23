#!/usr/bin/env python3
"""
Test script for derive_dynamic_field_id with I32 struct keys.

This script handles the custom I32 struct type used in your table:
    0x70285592c97965e811e0c6f98dccc3a9c2b4ad854b3594faab9597ada267b860::i32::I32

Usage:
    python test_derive_i32_field_id.py
"""

import hashlib
import struct
import json


def derive_dynamic_field_id_i32(
    parent_id: str,
    bits: int,
    key_type: str = "0x70285592c97965e811e0c6f98dccc3a9c2b4ad854b3594faab9597ada267b860::i32::I32",
) -> str:
    """
    Derive dynamic field ID when the key is the custom I32 struct.

    The I32 struct has a single field: bits (u32)

    Args:
        parent_id: Parent table ID
        bits: The u32 bits value from GraphQL (represents i32 as u32)
        key_type: Full type path of the I32 struct

    Returns:
        Field ID as hex string with 0x prefix
    """

    # 1. Intent byte for ChildObjectId
    intent_byte = bytes([1])

    # 2. Parent ID (32 bytes)
    parent_bytes = bytes.fromhex(parent_id.replace("0x", ""))
    if len(parent_bytes) != 32:
        parent_bytes = parent_bytes.rjust(32, b'\x00')

    # 3. Key bytes: BCS encoding of I32 struct { bits: u32 }
    # Just the u32 value in little-endian
    key_bytes = struct.pack('<I', bits)  # u32 little-endian (4 bytes)

    # 4. Key length as u64 little-endian
    key_length = struct.pack('<Q', len(key_bytes))

    # 5. Type tag: Struct variant
    type_tag_bytes = encode_struct_type_tag(key_type)

    # 6. Concatenate all
    data = intent_byte + parent_bytes + key_length + key_bytes + type_tag_bytes

    # 7. Hash with Blake2b-256
    hasher = hashlib.blake2b(digest_size=32)
    hasher.update(data)
    hash_result = hasher.digest()

    # 8. Field ID (first 32 bytes)
    field_id = hash_result[:32]
    return "0x" + field_id.hex()


def encode_struct_type_tag(struct_repr: str) -> bytes:
    """
    Encode a struct type tag as BCS bytes.

    Format: address::module::struct_name
    Example: 0x70285592c97965e811e0c6f98dccc3a9c2b4ad854b3594faab9597ada267b860::i32::I32

    BCS encoding for TypeTag::Struct:
    - 1 byte: variant (7 for Struct)
    - 32 bytes: address
    - uleb128 + bytes: module name
    - uleb128 + bytes: struct name
    - uleb128: type parameters length (0 for no params)
    """
    parts = struct_repr.split("::")
    if len(parts) != 3:
        raise ValueError(f"Invalid struct type format: {struct_repr}")

    addr_hex, module_name, struct_name = parts

    # Address (32 bytes)
    addr_bytes = bytes.fromhex(addr_hex.replace("0x", ""))
    if len(addr_bytes) != 32:
        addr_bytes = addr_bytes.rjust(32, b'\x00')

    # Module and struct names as UTF-8 bytes
    module_bytes = module_name.encode('utf-8')
    struct_bytes = struct_name.encode('utf-8')

    # BCS encoding:
    # - Variant 7 (Struct)
    # - Address
    # - Module name length (uleb128, but for small values just 1 byte)
    # - Module name bytes
    # - Struct name length
    # - Struct name bytes
    # - Type params length (0)
    return (
        bytes([7])  # Variant: Struct
        + addr_bytes
        + bytes([len(module_bytes)])  # Module length
        + module_bytes
        + bytes([len(struct_bytes)])  # Struct length
        + struct_bytes
        + bytes([0])  # No type parameters
    )


def bits_to_i32(bits: int) -> int:
    """Convert u32 bits representation to signed i32 value."""
    if bits >= 2**31:
        return bits - 2**32
    return bits


def i32_to_bits(value: int) -> int:
    """Convert signed i32 value to u32 bits representation."""
    if value < 0:
        return value + 2**32
    return value


def verify_with_detail(parent_id: str, bits: int, key_type: str):
    """Show detailed breakdown of the derivation."""
    print("=" * 80)
    print("Detailed Field ID Derivation")
    print("=" * 80)

    # Show i32 interpretation
    i32_value = bits_to_i32(bits)
    print(f"\nInput:")
    print(f"  Parent ID:  {parent_id}")
    print(f"  Bits (u32): {bits}")
    print(f"  As i32:     {i32_value}")
    print(f"  Key Type:   {key_type}")

    # 1. Intent byte
    intent_byte = bytes([1])
    print(f"\n1. Intent Byte (ChildObjectId):")
    print(f"   {intent_byte.hex()}")

    # 2. Parent
    parent_bytes = bytes.fromhex(parent_id.replace("0x", ""))
    if len(parent_bytes) != 32:
        parent_bytes = parent_bytes.rjust(32, b'\x00')
    print(f"\n2. Parent ID (32 bytes):")
    print(f"   {parent_bytes.hex()}")

    # 3. Key bytes
    key_bytes = struct.pack('<I', bits)
    print(f"\n3. Key Bytes (I32 struct with u32 field):")
    print(f"   {key_bytes.hex()} (bits={bits}, i32={i32_value})")
    print(f"   Length: {len(key_bytes)} bytes")

    # 4. Key length
    key_length = struct.pack('<Q', len(key_bytes))
    print(f"\n4. Key Length (u64 LE):")
    print(f"   {key_length.hex()} (length={len(key_bytes)})")

    # 5. Type tag
    type_tag_bytes = encode_struct_type_tag(key_type)
    print(f"\n5. Type Tag (Struct):")
    print(f"   {type_tag_bytes.hex()}")
    print(f"   Length: {len(type_tag_bytes)} bytes")
    print(f"   Breakdown:")
    print(f"     Variant:     {type_tag_bytes[0]:02x} (7 = Struct)")
    print(f"     Address:     {type_tag_bytes[1:33].hex()}")
    print(f"     Module len:  {type_tag_bytes[33]:02x}")
    print(f"     Module:      {type_tag_bytes[34:37]} ({type_tag_bytes[34:37].decode()})")
    print(f"     Struct len:  {type_tag_bytes[37]:02x}")
    print(f"     Struct:      {type_tag_bytes[38:41]} ({type_tag_bytes[38:41].decode()})")
    print(f"     Type params: {type_tag_bytes[41]:02x} (0 = none)")

    # 6. Full input
    data = intent_byte + parent_bytes + key_length + key_bytes + type_tag_bytes
    print(f"\n6. Full Hash Input ({len(data)} bytes):")
    print(f"   {data.hex()}")

    # 7. Hash
    hasher = hashlib.blake2b(digest_size=32)
    hasher.update(data)
    hash_result = hasher.digest()
    print(f"\n7. Blake2b-256 Hash Output:")
    print(f"   {hash_result.hex()}")

    # 8. Field ID
    field_id = "0x" + hash_result[:32].hex()
    print(f"\n8. Field ID:")
    print(f"   {field_id}")
    print()


def test_graphql_examples():
    """Test with actual examples from GraphQL data."""
    print("\n" + "=" * 80)
    print("Testing with GraphQL Data Examples")
    print("=" * 80)
    print()

    parent_id = "0x260d9bb579adc62ce0d2a094c39cd062cd0db1fc0fbbc7922e8dd88e39a0da4b"
    key_type = "0x70285592c97965e811e0c6f98dccc3a9c2b4ad854b3594faab9597ada267b860::i32::I32"

    # Examples from your GraphQL data
    test_cases = [
        (4294966990, "Should be tick index -306"),
        (26, "Should be tick index 26"),
        (4294523660, "Should be tick index -443636"),
        (17406, "Should be tick index 17406"),
        (4294967276, "Should be tick index -20"),
        (19464, "Should be tick index 19464"),
        (4294967270, "Should be tick index -26"),
        (57042, "Should be tick index 57042"),
        (58, "Should be tick index 58"),
        (443636, "Should be tick index 443636"),
    ]

    print(f"Parent ID: {parent_id}")
    print(f"Key Type:  {key_type}")
    print()

    results = []
    for bits, description in test_cases:
        field_id = derive_dynamic_field_id_i32(parent_id, bits, key_type)
        i32_value = bits_to_i32(bits)
        results.append((bits, i32_value, field_id))
        print(f"Bits: {bits:10d} (i32: {i32_value:7d}) -> {field_id}")

    print("\n" + "=" * 80)
    return results


def interactive_test():
    """Interactive mode for testing."""
    print("\n" + "=" * 80)
    print("Interactive Testing Mode")
    print("=" * 80)
    print()

    parent_id = "0x260d9bb579adc62ce0d2a094c39cd062cd0db1fc0fbbc7922e8dd88e39a0da4b"
    key_type = "0x70285592c97965e811e0c6f98dccc3a9c2b4ad854b3594faab9597ada267b860::i32::I32"

    while True:
        try:
            print("\nEnter bits value (u32) or i32 value prefixed with 'i' (e.g., 'i-306'), or 'q' to quit:")
            user_input = input("> ").strip()

            if user_input.lower() == 'q':
                break

            # Parse input
            if user_input.startswith('i'):
                # Input is i32 value
                i32_value = int(user_input[1:])
                bits = i32_to_bits(i32_value)
                print(f"Converting i32 {i32_value} to bits: {bits}")
            else:
                # Input is bits (u32)
                bits = int(user_input)
                i32_value = bits_to_i32(bits)

            # Derive field ID
            field_id = derive_dynamic_field_id_i32(parent_id, bits, key_type)

            print("\n" + "-" * 80)
            print(f"✅ Result:")
            print(f"   Bits (u32): {bits}")
            print(f"   As i32:     {i32_value}")
            print(f"   Field ID:   {field_id}")
            print("-" * 80)

        except ValueError as e:
            print(f"❌ Error: Invalid input - {e}")
        except KeyboardInterrupt:
            print("\n\nExiting...")
            break


def export_results_json(results, filename="field_ids.json"):
    """Export results to JSON file."""
    data = {
        "parent_id": "0x260d9bb579adc62ce0d2a094c39cd062cd0db1fc0fbbc7922e8dd88e39a0da4b",
        "key_type": "0x70285592c97965e811e0c6f98dccc3a9c2b4ad854b3594faab9597ada267b860::i32::I32",
        "fields": [
            {
                "bits": bits,
                "i32_value": i32_value,
                "field_id": field_id
            }
            for bits, i32_value, field_id in results
        ]
    }

    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\n✅ Results exported to {filename}")


if __name__ == "__main__":
    import sys

    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║            I32 Struct Dynamic Field ID Derivation Tester                     ║
║                                                                              ║
║  This script tests derive_dynamic_field_id with custom I32 struct keys.     ║
║  Type: 0x7028...::i32::I32                                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)

    # Test with GraphQL examples
    results = test_graphql_examples()

    # Show detailed breakdown for one example
    print("\n" + "=" * 80)
    print("Detailed Breakdown for bits=4294966990 (i32=-306)")
    print("=" * 80)
    parent_id = "0x260d9bb579adc62ce0d2a094c39cd062cd0db1fc0fbbc7922e8dd88e39a0da4b"
    key_type = "0x70285592c97965e811e0c6f98dccc3a9c2b4ad854b3594faab9597ada267b860::i32::I32"
    verify_with_detail(parent_id, 4294966990, key_type)

    # Export to JSON
    if "--export" in sys.argv:
        export_results_json(results)

    # Interactive mode
    if "--interactive" in sys.argv:
        interactive_test()
    else:
        print("\nTip: Run with --interactive for custom testing")
        print("     Run with --export to save results to JSON")
        print()
