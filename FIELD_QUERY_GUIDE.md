# Dynamic Field Query Guide

## 概述 (Overview)

本指南說明如何通過 custom_broadcaster 訂閱獲取 parent_id 和 current_index，然後使用 `read_child_object` 在 RocksDB 中查詢指定範圍內的 dynamic field BCS 值。

This guide explains how to subscribe to custom_broadcaster to get parent_id and current_index, then use `read_child_object` to query dynamic field BCS values within a specified range from RocksDB.

## 核心組件 (Core Components)

### 1. Custom Broadcaster (WebSocket 訂閱)

Custom broadcaster 提供實時交易輸出的 WebSocket 訂閱服務：

**位置**: `crates/sui-core/src/custom_broadcaster.rs`

**訂閱類型**:
```rust
enum SubscriptionMessage {
    SubscribePool(ObjectID),      // 訂閱特定池子
    SubscribeAccount(SuiAddress),  // 訂閱特定賬戶
    SubscribeAll,                  // 訂閱所有交易
}
```

**連接示例**:
```rust
// WebSocket URL
let url = "ws://localhost:9001";  // 默認端口

// 發送訂閱請求
let subscribe = SubscriptionMessage::SubscribePool(table_id);
let msg = serde_json::to_string(&subscribe)?;
websocket.send(msg).await?;
```

### 2. Dynamic Field ID 派生

Dynamic field 的 ObjectID 通過確定性哈希算法計算：

**公式**: `hash(parent || len(key) || key || key_type_tag)`

**位置**: `crates/sui-types/src/dynamic_field.rs:269-300`

**使用示例**:
```rust
use sui_types::dynamic_field::derive_dynamic_field_id;
use sui_types::TypeTag;

let table_id = ObjectID::from_hex_literal("0x...").unwrap();
let index = 12345u64;
let key_bytes = bcs::to_bytes(&index)?;
let key_type = TypeTag::U64;

let field_id = derive_dynamic_field_id(
    table_id,
    &key_type,
    &key_bytes,
)?;
```

### 3. RocksDB 查詢 (read_child_object)

**位置**: `crates/sui-core/src/execution_cache.rs:727-750`

**功能**:
- 驗證 parent-child 所有權關係
- 使用版本上界查找對象
- 返回符合條件的對象

**實現原理**:
```rust
// 1. 使用反向迭代器查找 ≤ parent_version 的最高版本
let child_object = find_object_lt_or_eq_version(child_id, parent_version)?;

// 2. 驗證所有權
if child_object.owner != Owner::ObjectOwner(parent.into()) {
    return Err(InvalidChildObjectAccess);
}

// 3. 返回對象
Ok(Some(child_object))
```

## 實現步驟 (Implementation Steps)

### 步驟 1: 訂閱 Custom Broadcaster

```rust
use tokio_tungstenite::connect_async;
use futures_util::{SinkExt, StreamExt};

async fn subscribe_to_pool(pool_id: ObjectID) -> Result<(), Error> {
    // 連接 WebSocket
    let (ws_stream, _) = connect_async("ws://localhost:9001").await?;
    let (mut write, mut read) = ws_stream.split();

    // 發送訂閱消息
    let subscribe = SubscriptionMessage::SubscribePool(pool_id);
    write.send(Message::Text(serde_json::to_string(&subscribe)?)).await?;

    // 接收更新
    while let Some(msg) = read.next().await {
        if let Message::Text(text) = msg? {
            handle_update(&text).await?;
        }
    }

    Ok(())
}
```

### 步驟 2: 解析訂閱消息

從 custom_broadcaster 收到的消息包含：
- `pool_id` 或 `parent_id`: 表對象 ID
- `current_tick` 或 `current_index`: 當前索引
- `version`: 父對象版本號

```rust
#[derive(serde::Deserialize)]
struct PoolUpdate {
    pool_id: ObjectID,
    current_tick: u64,
    version: SequenceNumber,
}

async fn handle_update(text: &str) -> Result<(), Error> {
    let update: PoolUpdate = serde_json::from_str(text)?;

    // 使用收到的信息查詢 field data
    query_field_range(
        update.pool_id,
        update.current_tick,
        update.version
    ).await?;

    Ok(())
}
```

### 步驟 3: 查詢範圍內的 Field Data

使用提供的 `field_data_query` 模塊：

```rust
use sui_core::field_data_query::{query_field_data_range, decode_field_value};

async fn query_field_range(
    table_id: ObjectID,
    current_index: u64,
    parent_version: SequenceNumber,
) -> Result<(), Error> {
    // 獲取 store 引用
    let store = get_authority_store()?;

    // 查詢 ±100000 範圍
    let field_data = query_field_data_range(
        store.perpetual_tables(),
        table_id,
        current_index,
        100_000,  // range
        parent_version,
        &TypeTag::U64,
    )?;

    // 處理結果
    for (index, data) in field_data {
        println!("Index: {}, Field ID: {}", index, data.field_id);
        println!("BCS bytes (hex): {}", hex::encode(&data.bcs_bytes));

        // 解碼 BCS 值
        let value: YourDataType = decode_field_value(&data.bcs_bytes)?;
        println!("Decoded value: {:?}", value);
    }

    Ok(())
}
```

### 步驟 4: 定義並解碼數據結構

根據你的 Move 合約定義對應的 Rust 結構：

```rust
// 如果 field 存儲簡單值
#[derive(serde::Deserialize, Debug)]
struct TickData {
    price: u64,
    volume: u64,
    timestamp: u64,
}

// 如果 field 是 Field<K, V> 包裝
#[derive(serde::Deserialize)]
struct Field<K, V> {
    id: sui_types::base_types::UID,
    name: K,
    value: V,
}

// 解碼示例
let tick: TickData = decode_field_value(&bcs_bytes)?;
// 或
let field: Field<u64, TickData> = decode_field_value(&bcs_bytes)?;
```

## API 參考 (API Reference)

### `query_field_data_range`

查詢指定範圍內的 field data（基礎版本）。

```rust
pub fn query_field_data_range(
    store: &AuthorityPerpetualTables,
    table_id: ObjectID,
    current_index: u64,
    range: u64,                    // ±range 範圍
    parent_version: SequenceNumber,
    key_type: &TypeTag,            // 鍵類型（如 TypeTag::U64）
) -> SuiResult<HashMap<u64, FieldData>>
```

### `query_field_data_range_validated`

查詢指定範圍內的 field data（帶父子關係驗證）。

```rust
pub fn query_field_data_range_validated(
    resolver: &impl ChildObjectResolver,
    table_id: ObjectID,
    current_index: u64,
    range: u64,
    parent_version: SequenceNumber,
    key_type: &TypeTag,
) -> SuiResult<HashMap<u64, FieldData>>
```

### `query_field_data_range_sparse`

稀疏數據優化版本，在連續未命中時提前終止。

```rust
pub fn query_field_data_range_sparse(
    store: &AuthorityPerpetualTables,
    table_id: ObjectID,
    current_index: u64,
    range: u64,
    parent_version: SequenceNumber,
    key_type: &TypeTag,
    max_consecutive_misses: usize,  // 最大連續未命中次數
) -> SuiResult<HashMap<u64, FieldData>>
```

### `decode_field_value`

解碼 BCS 字節為具體類型。

```rust
pub fn decode_field_value<'de, T: Deserialize<'de>>(
    bcs_bytes: &'de [u8],
) -> Result<T, bcs::Error>
```

## 完整示例 (Complete Example)

參見 `examples/field_query_example.rs` 獲取完整的實現示例，包括：

1. WebSocket 訂閱集成
2. 消息處理
3. 範圍查詢
4. BCS 解碼
5. 並行查詢優化

## 性能優化建議 (Performance Optimization)

### 1. 批量查詢

將大範圍分割成小塊並行查詢：

```rust
use tokio::task::spawn;

async fn parallel_query(
    store: Arc<AuthorityStore>,
    table_id: ObjectID,
    current_index: u64,
) -> Result<HashMap<u64, FieldData>, Error> {
    let mut tasks = vec![];

    // 分成 10 個並行任務
    for i in 0..10 {
        let chunk_start = current_index - 100_000 + i * 20_000;
        let chunk_end = chunk_start + 20_000;
        let store = store.clone();

        tasks.push(spawn(async move {
            query_chunk(store, table_id, chunk_start, chunk_end).await
        }));
    }

    // 收集結果
    let results = futures::future::join_all(tasks).await;
    // ... 合併結果
}
```

### 2. 稀疏數據處理

如果數據稀疏，使用 `query_field_data_range_sparse` 並設置合理的 `max_consecutive_misses`：

```rust
let field_data = query_field_data_range_sparse(
    store.perpetual_tables(),
    table_id,
    current_index,
    100_000,
    parent_version,
    &TypeTag::U64,
    1000,  // 連續 1000 次未命中後停止
)?;
```

### 3. 緩存常用結果

對於頻繁訪問的索引，考慮添加緩存層：

```rust
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;

struct FieldCache {
    cache: Arc<RwLock<HashMap<(ObjectID, u64), Vec<u8>>>>,
}

impl FieldCache {
    async fn get_or_fetch(
        &self,
        table_id: ObjectID,
        index: u64,
        store: &impl ChildObjectResolver,
        parent_version: SequenceNumber,
    ) -> Option<Vec<u8>> {
        // 檢查緩存
        {
            let cache = self.cache.read().await;
            if let Some(bcs_bytes) = cache.get(&(table_id, index)) {
                return Some(bcs_bytes.clone());
            }
        }

        // 從 RocksDB 獲取
        let bcs_bytes = fetch_field_bcs(store, table_id, index, parent_version).ok()??;

        // 更新緩存
        {
            let mut cache = self.cache.write().await;
            cache.insert((table_id, index), bcs_bytes.clone());
        }

        Some(bcs_bytes)
    }
}
```

## 錯誤處理 (Error Handling)

### 常見錯誤及解決方法

1. **InvalidChildObjectAccess**: 對象的 owner 不是指定的 parent
   - 檢查 parent_id 是否正確
   - 確認 field 確實屬於該 table

2. **對象不存在**: `find_object_lt_or_eq_version` 返回 None
   - 該索引的 field 可能未創建
   - parent_version 可能太舊

3. **BCS 解碼失敗**: `decode_field_value` 返回錯誤
   - 檢查 Rust 結構定義是否與 Move 類型匹配
   - 確認字段順序和類型一致

4. **WebSocket 連接斷開**:
   - 實現自動重連機制
   - 使用心跳保持連接

```rust
async fn subscribe_with_retry(pool_id: ObjectID) -> Result<(), Error> {
    loop {
        match subscribe_to_pool(pool_id).await {
            Ok(_) => break,
            Err(e) => {
                eprintln!("Connection error: {}, retrying in 5s...", e);
                tokio::time::sleep(Duration::from_secs(5)).await;
            }
        }
    }
    Ok(())
}
```

## 關鍵要點 (Key Takeaways)

1. **Field ID 是哈希值**：不能通過範圍掃描，必須逐個計算每個索引的 field ID
2. **版本管理**：使用 parent_version 作為上界確保一致性
3. **所有權驗證**：`read_child_object` 自動驗證 parent-child 關係
4. **BCS 編碼**：Rust 結構必須與 Move 類型精確匹配
5. **性能考慮**：大範圍查詢應該並行處理或使用稀疏優化

## 相關文件 (Related Files)

- 核心實現: `crates/sui-core/src/field_data_query.rs`
- 使用示例: `examples/field_query_example.rs`
- Custom Broadcaster: `crates/sui-core/src/custom_broadcaster.rs`
- Dynamic Field 類型: `crates/sui-types/src/dynamic_field.rs`
- RocksDB 存儲: `crates/sui-core/src/authority/authority_store_tables.rs`

## 測試 (Testing)

運行測試以驗證實現：

```bash
# 測試 field_data_query 模塊
cargo nextest run -p sui-core --lib field_data_query

# 測試示例
cargo test -p sui --example field_query_example
```
