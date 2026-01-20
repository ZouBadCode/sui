#!/usr/bin/env python3
"""
Test script for custom_broadcaster field range query functionality.

This script demonstrates how to:
1. Subscribe to pool updates via custom_broadcaster
2. Query field data in a range around a current index
3. Decode BCS field data

Usage:
    python test_field_query.py
"""

import asyncio
import websockets
import json
import base64
import canoser
from pysui.sui.sui_bcs import bcs as sui_bcs
from typing import Any, Optional


# ----------------------------
# BCS Struct Definitions
# ----------------------------

class UID(canoser.Struct):
    _fields = [("id", sui_bcs.Address)]


class I32(canoser.Struct):
    _fields = [("bits", canoser.Uint32)]


class I64(canoser.Struct):
    _fields = [("bits", canoser.Uint64)]


class I128(canoser.Struct):
    _fields = [("bits", canoser.Uint128)]


class TickInfo(canoser.Struct):
    _fields = [
        ("fee_growth_outside_x", canoser.Uint128),
        ("fee_growth_outside_y", canoser.Uint128),
        ("liquidity_gross", canoser.Uint128),
        ("liquidity_net", I128),
        ("reward_growths_outside", [canoser.Uint128]),
        ("seconds_out_side", canoser.Uint64),
        ("seconds_per_liquidity_out_side", canoser.Uint128),
        ("tick_cumulative_out_side", I64),
    ]


class TableBCS(canoser.Struct):
    _fields = [("id", UID), ("size", canoser.Uint64)]


class FieldI32TickInfoBCS(canoser.Struct):
    _fields = [("id", UID), ("name", I32), ("value", TickInfo)]


# ----------------------------
# Monitor
# ----------------------------

class FieldQueryTester:
    def __init__(self, ws_url: str, table_id: str):
        self.ws_url = ws_url
        self.table_id = table_id

    def decode_field_i32_tickinfo(self, bcs_bytes: bytes) -> dict:
        """Decode Field<i32, TickInfo> BCS bytes"""
        field = FieldI32TickInfoBCS.deserialize(bcs_bytes, check=False)
        i32_bits = int(field.name.bits)
        i32_value = i32_bits - 2**32 if i32_bits >= 2**31 else i32_bits
        return {
            "id": field.id.id.to_address_str(),
            "name": i32_value,
            "value": self._tickinfo_to_dict(field.value),
        }

    def _tickinfo_to_dict(self, tick: TickInfo) -> dict:
        """Convert TickInfo to dict"""
        return {
            "fee_growth_outside_x": int(tick.fee_growth_outside_x),
            "fee_growth_outside_y": int(tick.fee_growth_outside_y),
            "liquidity_gross": int(tick.liquidity_gross),
            "liquidity_net_bits": int(tick.liquidity_net.bits),
            "reward_growths_outside": [int(x) for x in tick.reward_growths_outside],
            "seconds_out_side": int(tick.seconds_out_side),
            "seconds_per_liquidity_out_side": int(tick.seconds_per_liquidity_out_side),
            "tick_cumulative_out_side_bits": int(tick.tick_cumulative_out_side.bits),
        }

    async def test_field_range_query(self):
        """Test the new field range query functionality"""
        async with websockets.connect(
            self.ws_url,
            ping_interval=None,
            ping_timeout=20,
            close_timeout=10,
            max_size=10 * 1024 * 1024,
        ) as websocket:

            print(f"\n{'='*60}")
            print("🔍 Testing Field Range Query")
            print(f"{'='*60}\n")

            # Query field range: table_id, current_index, range
            query_request = {
                "type": "query_field_range",
                "table_id": self.table_id,
                "current_index": 1000,  # Query around index 1000
                "range": 100,            # ±100 range
                "parent_version": None,  # Use latest version
            }

            print(f"📤 Sending query request:")
            print(f"   Table ID: {self.table_id}")
            print(f"   Current Index: {query_request['current_index']}")
            print(f"   Range: ±{query_request['range']}")
            print(f"   Expected index range: {query_request['current_index'] - query_request['range']} to {query_request['current_index'] + query_request['range']}")
            print()

            await websocket.send(json.dumps(query_request))

            field_count = 0
            received_indices = []

            # Receive responses
            print("📥 Receiving field data...\n")
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except Exception as e:
                    print(f"⚠️  JSON parse error: {e}")
                    continue

                msg_type = msg.get("type")

                if msg_type == "field_data":
                    # New message format from our updated API
                    field_count += 1
                    index = msg.get("index")
                    field_id = msg.get("field_id")
                    bcs_bytes = bytes(msg.get("bcs_bytes", []))
                    version = msg.get("version")

                    received_indices.append(index)

                    # Decode the field
                    try:
                        decoded = self.decode_field_i32_tickinfo(bcs_bytes)
                        tick_index = decoded["name"]
                        liquidity = decoded["value"]["liquidity_gross"]

                        if field_count <= 5:  # Show first 5 fields in detail
                            print(f"✅ Field #{field_count}:")
                            print(f"   Index: {index}")
                            print(f"   Field ID: {field_id}")
                            print(f"   Version: {version}")
                            print(f"   Tick: {tick_index}")
                            print(f"   Liquidity Gross: {liquidity}")
                            print()
                        elif field_count % 20 == 0:  # Progress indicator
                            print(f"   ... received {field_count} fields ...")

                    except Exception as e:
                        print(f"⚠️  Decode error for index {index}: {e}")

                elif msg_type == "query_complete":
                    # Query completed
                    total = msg.get("total_fields")
                    print(f"\n{'='*60}")
                    print(f"✅ Query completed!")
                    print(f"   Total fields received: {total}")
                    print(f"   Actual messages received: {field_count}")

                    if received_indices:
                        print(f"   Index range: {min(received_indices)} to {max(received_indices)}")

                    print(f"{'='*60}\n")
                    break

                elif msg_type == "error":
                    error_msg = msg.get("message", "Unknown error")
                    print(f"\n❌ Error: {error_msg}\n")
                    break

                else:
                    print(f"⚠️  Unknown message type: {msg_type}")

    async def test_subscribe_and_query(self):
        """Test subscribing to updates and then querying on updates"""
        async with websockets.connect(
            self.ws_url,
            ping_interval=None,
            ping_timeout=20,
            close_timeout=10,
            max_size=10 * 1024 * 1024,
        ) as websocket:

            print(f"\n{'='*60}")
            print("🔔 Testing Subscribe + Query on Update")
            print(f"{'='*60}\n")

            # Subscribe to pool updates
            subscribe_request = {
                "type": "subscribe_pool",
                "pool_id": self.table_id,
            }

            print(f"📤 Subscribing to pool: {self.table_id}\n")
            await websocket.send(json.dumps(subscribe_request))

            print("⏳ Waiting for pool updates...")
            print("   (This will trigger a field range query when an update is received)\n")

            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except Exception as e:
                    print(f"⚠️  JSON parse error: {e}")
                    continue

                msg_type = msg.get("type")

                if msg_type == "pool_update":
                    pool_id = msg.get("pool_id")
                    digest = msg.get("digest")

                    print(f"🔔 Pool Update Received!")
                    print(f"   Pool ID: {pool_id}")
                    print(f"   Digest: {digest}")
                    print()

                    # Now query the field range
                    # In a real scenario, you would extract current_index from the pool update
                    print("📤 Triggering field range query based on update...\n")

                    query_request = {
                        "type": "query_field_range",
                        "table_id": pool_id,
                        "current_index": 1000,
                        "range": 50,
                        "parent_version": None,
                    }

                    await websocket.send(json.dumps(query_request))

                    # Wait for query results
                    field_count = 0
                    async for raw2 in websocket:
                        try:
                            msg2 = json.loads(raw2)
                        except:
                            continue

                        msg_type2 = msg2.get("type")

                        if msg_type2 == "field_data":
                            field_count += 1
                            if field_count <= 3:
                                print(f"   Field {field_count}: index={msg2.get('index')}")

                        elif msg_type2 == "query_complete":
                            total = msg2.get("total_fields")
                            print(f"\n✅ Query completed! Received {total} fields\n")
                            return  # Exit after first query

                        elif msg_type2 == "pool_update":
                            # Another update arrived, process it later
                            break

    async def run_tests(self):
        """Run all tests"""
        print("\n" + "="*60)
        print("🚀 Field Query Test Suite")
        print("="*60)

        # Test 1: Direct field range query
        try:
            await self.test_field_range_query()
        except Exception as e:
            print(f"❌ Test 1 failed: {e}\n")

        # Test 2: Subscribe and query (commented out as it waits for updates)
        # Uncomment to test real-time subscriptions
        # try:
        #     await self.test_subscribe_and_query()
        # except Exception as e:
        #     print(f"❌ Test 2 failed: {e}\n")


async def main():
    """Main entry point"""

    # Configuration
    WS_URL = "ws://3.114.103.176:9002/ws"
    TABLE_ID = "0x260d9bb579adc62ce0d2a094c39cd062cd0db1fc0fbbc7922e8dd88e39a0da4b"

    tester = FieldQueryTester(ws_url=WS_URL, table_id=TABLE_ID)
    await tester.run_tests()

    print("\n✅ All tests completed!\n")


if __name__ == "__main__":
    asyncio.run(main())
