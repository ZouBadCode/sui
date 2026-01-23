#!/usr/bin/env python3
"""
Simple script to test derive_dynamic_field_id calculation.

This script replicates the Rust derive_dynamic_field_id logic to verify
that field IDs are derived correctly.

Usage:
    python test_derive_field_id.py
"""

import hashlib
import struct


def derive_dynamic_field_id(parent_id: str, index: int, key_type: str = "u64") -> str:
    """
    Derive dynamic field ID using the same algorithm as Rust.

    Algorithm:
        hash(HashingIntentScope::ChildObjectId || parent_id || key_length || key_bytes || key_type_tag)

    Args:
        parent_id: Parent object ID (hex string with or without 0x prefix)
        index: The index value (u64)
        key_type: Type of the key (default: "u64")

    Returns:
        Field ID as hex string with 0x prefix
    """

    # 1. HashingIntentScope::ChildObjectId = 1
    intent_byte = bytes([1])

    # 2. Parent ID (32 bytes)
    parent_bytes = bytes.fromhex(parent_id.replace("0x", ""))
    if len(parent_bytes) != 32:
        # Pad with zeros if needed
        parent_bytes = parent_bytes.rjust(32, b'\x00')

    # 3. Serialize index as BCS u64 (little-endian 8 bytes)
    key_bytes = struct.pack('<Q', index)  # u64 little-endian

    # 4. Key length as u64 little-endian
    key_length = struct.pack('<Q', len(key_bytes))

    # 5. Type tag for u64
    # TypeTag::U64 in BCS format
    # In Sui, TypeTag is an enum where U64 = 2
    # BCS encoding: variant index (1 byte) = 2
    type_tag_bytes = bytes([2])

    # 6. Concatenate all parts
    data = intent_byte + parent_bytes + key_length + key_bytes + type_tag_bytes

    # 7. Hash with Blake2b-256
    hasher = hashlib.blake2b(digest_size=32)
    hasher.update(data)
    hash_result = hasher.digest()

    # 8. Take first 32 bytes (already 32 bytes from blake2b-256)
    field_id = hash_result[:32]

    return "0x" + field_id.hex()


def test_examples():
    """Test with example values"""

    print("=" * 70)
    print("Dynamic Field ID Derivation Tester")
    print("=" * 70)
    print()

    # Example 1: Your table ID
    parent_id = "0x260d9bb579adc62ce0d2a094c39cd062cd0db1fc0fbbc7922e8dd88e39a0da4b"

    test_cases = [
        (parent_id, 0),
        (parent_id, 1),
        (parent_id, 100),
        (parent_id, 1000),
        (parent_id, 10000),
    ]

    for parent, index in test_cases:
        field_id = derive_dynamic_field_id(parent, index)
        print(f"Parent ID: {parent}")
        print(f"Index:     {index}")
        print(f"Field ID:  {field_id}")
        print()


def interactive_mode():
    """Interactive mode for custom testing"""

    print("\n" + "=" * 70)
    print("Interactive Mode")
    print("=" * 70)
    print()

    while True:
        try:
            print("Enter parent ID (or 'q' to quit):")
            parent_input = input("> ").strip()

            if parent_input.lower() == 'q':
                break

            # Use default if empty
            if not parent_input:
                parent_input = "0x260d9bb579adc62ce0d2a094c39cd062cd0db1fc0fbbc7922e8dd88e39a0da4b"
                print(f"Using default: {parent_input}")

            print("\nEnter index (u64 number):")
            index_input = input("> ").strip()
            index = int(index_input)

            field_id = derive_dynamic_field_id(parent_input, index)

            print("\n" + "-" * 70)
            print(f"✅ Result:")
            print(f"   Parent ID: {parent_input}")
            print(f"   Index:     {index}")
            print(f"   Field ID:  {field_id}")
            print("-" * 70)
            print()

        except ValueError as e:
            print(f"❌ Error: Invalid input - {e}")
            print()
        except KeyboardInterrupt:
            print("\n\nExiting...")
            break


def batch_test_range(parent_id: str, start: int, end: int, step: int = 1):
    """
    Generate field IDs for a range of indices.
    Useful for batch testing.
    """
    print("\n" + "=" * 70)
    print(f"Batch Test: Indices {start} to {end} (step={step})")
    print("=" * 70)
    print()

    results = []
    for index in range(start, end + 1, step):
        field_id = derive_dynamic_field_id(parent_id, index)
        results.append((index, field_id))

        if len(results) <= 10:  # Show first 10
            print(f"Index {index:6d}: {field_id}")

    if len(results) > 10:
        print(f"... (showing first 10 of {len(results)} results)")

    print()
    return results


def verify_with_bcs_detail(parent_id: str, index: int):
    """
    Show detailed breakdown of BCS encoding for verification.
    """
    print("\n" + "=" * 70)
    print("Detailed BCS Breakdown")
    print("=" * 70)
    print()

    # 1. Intent byte
    intent_byte = bytes([1])
    print(f"1. Intent Byte (ChildObjectId):     {intent_byte.hex()}")

    # 2. Parent ID
    parent_bytes = bytes.fromhex(parent_id.replace("0x", ""))
    if len(parent_bytes) != 32:
        parent_bytes = parent_bytes.rjust(32, b'\x00')
    print(f"2. Parent ID (32 bytes):            {parent_bytes.hex()}")

    # 3. Key bytes (index as u64 little-endian)
    key_bytes = struct.pack('<Q', index)
    print(f"3. Key Bytes (u64 LE):              {key_bytes.hex()} (value={index})")

    # 4. Key length
    key_length = struct.pack('<Q', len(key_bytes))
    print(f"4. Key Length (u64 LE):             {key_length.hex()} (length={len(key_bytes)})")

    # 5. Type tag
    type_tag_bytes = bytes([2])
    print(f"5. Type Tag (U64):                  {type_tag_bytes.hex()}")

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
    print(f"\n8. Field ID (first 32 bytes):")
    print(f"   {field_id}")
    print()


if __name__ == "__main__":
    import sys

    print("""
╔════════════════════════════════════════════════════════════════════╗
║         Dynamic Field ID Derivation Test Script                   ║
║                                                                    ║
║  This script replicates the Rust derive_dynamic_field_id logic    ║
║  to verify that field IDs are calculated correctly.               ║
╚════════════════════════════════════════════════════════════════════╝
    """)

    # Run examples
    test_examples()

    # Show detailed breakdown for one example
    print("\n" + "=" * 70)
    print("Showing detailed breakdown for index 1000:")
    parent_id = "0x260d9bb579adc62ce0d2a094c39cd062cd0db1fc0fbbc7922e8dd88e39a0da4b"
    verify_with_bcs_detail(parent_id, 1000)

    # Batch test
    if len(sys.argv) > 1 and sys.argv[1] == "--batch":
        batch_test_range(parent_id, 900, 1100, step=10)

    # Interactive mode
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        interactive_mode()
    else:
        print("\nTip: Run with --interactive for custom testing")
        print("     Run with --batch for range testing")
        print()
