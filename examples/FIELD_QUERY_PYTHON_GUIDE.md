# Python Field Query Testing Guide

## 概述 (Overview)

本指南說明如何使用 Python 測試 custom_broadcaster 的 dynamic field 範圍查詢功能。

This guide explains how to use Python to test the custom_broadcaster's dynamic field range query functionality.

## 前置要求 (Prerequisites)

### 安裝依賴 (Install Dependencies)

```bash
pip install websockets canoser pysui
```

### 確保 Sui 節點運行 (Ensure Sui Node is Running)

你的 Sui 節點必須啟用 custom_broadcaster，並且傳遞了 `store` 參數以支持查詢功能。

Your Sui node must have custom_broadcaster enabled with the `store` parameter for query support.

## 新增的 WebSocket API

### 1. 查詢 Field 範圍 (Query Field Range)

**請求格式**:
```json
{
  "type": "query_field_range",
  "table_id": "0x...",
  "current_index": 1000,
  "range": 100,
  "parent_version": null  // Optional, use latest if null
}
```

**參數說明**:
- `table_id`: 表對象的 ID (parent object ID)
- `current_index`: 中心索引
- `range`: 範圍大小 (查詢 current_index ± range)
- `parent_version`: 可選，父對象版本號（null 則使用最新版本）

**響應消息**:

1. **Field Data** (每個 field 一條消息):
```json
{
  "type": "field_data",
  "table_id": "0x...",
  "index": 950,
  "field_id": "0x...",
  "bcs_bytes": [1, 2, 3, ...],
  "version": 12345
}
```

2. **Query Complete** (查詢完成):
```json
{
  "type": "query_complete",
  "table_id": "0x...",
  "total_fields": 150
}
```

3. **Error** (錯誤):
```json
{
  "type": "error",
  "message": "Error description"
}
```

### 2. 訂閱 Pool (更新格式)

**請求格式** (已更新):
```json
{
  "type": "subscribe_pool",
  "pool_id": "0x..."
}
```

**舊格式仍然支持**:
```json
{
  "SubscribePool": "0x..."
}
```

## 使用測試腳本 (Using the Test Script)

### 基本用法 (Basic Usage)

```bash
python examples/test_field_query.py
```

### 測試腳本功能

測試腳本 `test_field_query.py` 包含兩個主要測試：

#### 測試 1: 直接範圍查詢
```python
query_request = {
    "type": "query_field_range",
    "table_id": "0x260d9bb579adc62ce0d2a094c39cd062cd0db1fc0fbbc7922e8dd88e39a0da4b",
    "current_index": 1000,
    "range": 100,  # Query index 900-1100
    "parent_version": None,
}
```

#### 測試 2: 訂閱並查詢 (Subscribe + Query)
當收到 pool 更新時自動觸發範圍查詢。

## 自定義測試 (Custom Testing)

### 修改你的現有 Python 代碼

你可以更新你現有的 `TableMonitor` 類來支持新的查詢功能：

```python
class TableMonitor:
    # ... existing code ...

    async def query_field_range(self, current_index: int, range_size: int = 100):
        """Query field data around current_index"""
        query = {
            "type": "query_field_range",
            "table_id": self.table_id,
            "current_index": current_index,
            "range": range_size,
            "parent_version": None,
        }

        await self.websocket.send(json.dumps(query))

        fields = []
        async for raw in self.websocket:
            msg = json.loads(raw)

            if msg.get("type") == "field_data":
                # Decode the BCS bytes
                bcs_bytes = bytes(msg["bcs_bytes"])
                decoded = self.decode_field_i32_tickinfo(bcs_bytes)
                fields.append({
                    "index": msg["index"],
                    "field_id": msg["field_id"],
                    "data": decoded,
                })

            elif msg.get("type") == "query_complete":
                print(f"Query complete: {msg['total_fields']} fields")
                break

            elif msg.get("type") == "error":
                print(f"Error: {msg['message']}")
                break

        return fields

    async def connect(self):
        async with websockets.connect(self.ws_url, ...) as websocket:
            self.websocket = websocket

            # Subscribe to pool
            await websocket.send(json.dumps({
                "type": "subscribe_pool",
                "pool_id": self.table_id,
            }))

            # Query initial field range
            fields = await self.query_field_range(current_index=1000, range_size=100)
            print(f"Got {len(fields)} fields")

            # Continue listening for updates...
```

## 整合示例 (Integration Example)

### 從訂閱到查詢的完整流程

```python
async def monitor_and_query(table_id: str):
    async with websockets.connect("ws://localhost:9002/ws") as ws:
        # 1. Subscribe to pool updates
        await ws.send(json.dumps({
            "type": "subscribe_pool",
            "pool_id": table_id,
        }))

        async for message in ws:
            msg = json.loads(message)

            # 2. When we get a pool update
            if msg.get("type") == "pool_update":
                pool_id = msg["pool_id"]

                # 3. Extract current state (if available in update)
                # For this example, we use a fixed index
                current_index = 1000

                # 4. Query surrounding field data
                await ws.send(json.dumps({
                    "type": "query_field_range",
                    "table_id": pool_id,
                    "current_index": current_index,
                    "range": 100,
                    "parent_version": None,
                }))

                # 5. Collect query results
                field_count = 0
                async for msg2 in ws:
                    msg2 = json.loads(msg2)

                    if msg2.get("type") == "field_data":
                        field_count += 1
                        # Process field data
                        bcs_bytes = bytes(msg2["bcs_bytes"])
                        # ... decode and use ...

                    elif msg2.get("type") == "query_complete":
                        print(f"Received {field_count} fields")
                        break  # Go back to listening for updates
```

## 性能考慮 (Performance Considerations)

### 範圍大小 (Range Size)

- **小範圍** (< 1000): 快速響應，適合實時查詢
- **中範圍** (1000-10000): 可能需要幾秒鐘
- **大範圍** (> 10000): 可能較慢，考慮分批查詢

### 優化建議

1. **分批查詢**: 將大範圍分成多個小查詢
```python
async def query_large_range(ws, table_id, start, end, batch_size=1000):
    all_fields = []

    for current in range(start, end, batch_size):
        await ws.send(json.dumps({
            "type": "query_field_range",
            "table_id": table_id,
            "current_index": current + batch_size // 2,
            "range": batch_size // 2,
            "parent_version": None,
        }))

        # Collect batch results
        # ...

    return all_fields
```

2. **使用 parent_version**: 指定版本確保一致性
```python
{
    "type": "query_field_range",
    "table_id": "0x...",
    "current_index": 1000,
    "range": 100,
    "parent_version": 12345,  // Use specific version
}
```

## 錯誤處理 (Error Handling)

### 常見錯誤

1. **"Field query not supported: store not available"**
   - 原因: Sui 節點未傳遞 store 給 custom_broadcaster
   - 解決: 確認節點配置正確

2. **"Query failed: ..."**
   - 原因: RocksDB 查詢錯誤
   - 解決: 檢查 table_id 和 parent_version 是否正確

3. **超時 (Timeout)**
   - 原因: 範圍太大或網絡問題
   - 解決: 減小範圍或增加超時設置

## 測試清單 (Testing Checklist)

- [ ] 測試小範圍查詢 (range < 100)
- [ ] 測試中等範圍查詢 (range = 1000)
- [ ] 測試大範圍查詢 (range > 10000)
- [ ] 測試指定 parent_version
- [ ] 測試錯誤處理
- [ ] 測試訂閱 + 查詢流程
- [ ] 測試 BCS 解碼正確性
- [ ] 測試並發查詢

## 完整 Python 示例

參見 `examples/test_field_query.py` 獲取完整的測試示例。

## 故障排查 (Troubleshooting)

### WebSocket 連接失敗

```python
# 增加重試機制
async def connect_with_retry(url, max_retries=5):
    for i in range(max_retries):
        try:
            return await websockets.connect(url)
        except Exception as e:
            if i == max_retries - 1:
                raise
            await asyncio.sleep(2 ** i)  # Exponential backoff
```

### BCS 解碼失敗

```python
def safe_decode(bcs_bytes):
    try:
        return FieldI32TickInfoBCS.deserialize(bcs_bytes, check=False)
    except Exception as e:
        print(f"Decode failed: {e}")
        print(f"BCS bytes (hex): {bcs_bytes.hex()}")
        return None
```

## 相關資源 (Related Resources)

- 核心實現: `crates/sui-core/src/field_data_query.rs`
- WebSocket 服務: `crates/sui-core/src/custom_broadcaster.rs`
- 完整文檔: `FIELD_QUERY_GUIDE.md`
- 測試腳本: `examples/test_field_query.py`
