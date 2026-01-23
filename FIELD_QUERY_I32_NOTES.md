# I32 Struct Field Query Notes

## 重要發現 (Important Discovery)

你的 dynamic field 表使用的是 **自定義 I32 結構體** 作為 key，而不是簡單的 `u64`。

Your dynamic field table uses a **custom I32 struct** as the key type, not a simple `u64`.

## Key Type 差異 (Key Type Difference)

### 原本假設 (Original Assumption)
```rust
// ❌ 錯誤
TypeTag::U64
```

### 實際類型 (Actual Type)
```rust
// ✅ 正確
TypeTag::Struct(Box::new(StructTag {
    address: 0x70285592c97965e811e0c6f98dccc3a9c2b4ad854b3594faab9597ada267b860,
    module: "i32",
    name: "I32",
    type_params: vec![],
}))
```

## I32 結構定義 (I32 Struct Definition)

```move
module 0x70285592c97965e811e0c6f98dccc3a9c2b4ad854b3594faab9597ada267b860::i32 {
    struct I32 has copy, drop, store {
        bits: u32  // 用 u32 表示 i32 的原始位
    }
}
```

## BCS 編碼差異 (BCS Encoding Differences)

### U64 Key (8 bytes)
```
Key bytes:  e803000000000000  (1000 as u64 LE)
Key length: 0800000000000000  (8)
Type tag:   02                (variant 2 = U64)
```

### I32 Struct Key (4 bytes)
```
Key bytes:  cefeffff          (4294966990 as u32 LE = -306 as i32)
Key length: 0400000000000000  (4)
Type tag:   0770285592c97965e811e0c6f98dccc3a9c2b4ad854b3594faab9597ada267b860036933320349333200
            ↑  ↑                                                               ↑     ↑     ↑
          variant address (32 bytes)                                         i32   I32   empty
           (7)                                                              (3 bytes) (3 bytes) vec
```

## 如何更新 Rust 代碼 (How to Update Rust Code)

### 更新 field_data_query.rs

```rust
// 在函數簽名中添加 key_type 參數
pub fn query_field_data_range(
    store: &AuthorityPerpetualTables,
    table_id: ObjectID,
    current_index: u64,
    range: u64,
    parent_version: SequenceNumber,
    key_type: &TypeTag,  // 允許調用者指定類型
) -> SuiResult<HashMap<u64, FieldData>>

// 使用傳入的 key_type
let field_id = derive_dynamic_field_id(
    table_id,
    key_type,  // 使用參數，而不是硬編碼 &TypeTag::U64
    &key_bytes,
)?;
```

### 更新 custom_broadcaster.rs

```rust
use sui_types::base_types::{ObjectID, SequenceNumber};
use sui_types::{StructTag, TypeTag};
use move_core_types::{account_address::AccountAddress, identifier::Identifier};

async fn handle_field_range_query(
    socket: &mut WebSocket,
    state: &Arc<AppState>,
    table_id: ObjectID,
    current_index: u64,
    range: u64,
    parent_version: Option<u64>,
) {
    // 構建 I32 struct type tag
    let i32_struct = StructTag {
        address: AccountAddress::from_hex_literal(
            "0x70285592c97965e811e0c6f98dccc3a9c2b4ad854b3594faab9597ada267b860"
        ).expect("Valid address"),
        module: Identifier::new("i32").expect("Valid module name"),
        name: Identifier::new("I32").expect("Valid struct name"),
        type_params: vec![],
    };
    let key_type = TypeTag::Struct(Box::new(i32_struct));

    // 使用 I32 struct type tag 查詢
    match query_field_data_range(
        &store.perpetual_tables,
        table_id,
        current_index,
        range,
        version,
        &key_type,  // 傳遞 I32 struct type
    ) {
        // ... 處理結果
    }
}
```

### Key Bytes 編碼

```rust
// 對於 I32 struct，key 是 u32 (4 bytes)
let index_u32 = current_index as u32;  // 或從 i32 轉換
let key_bytes = bcs::to_bytes(&index_u32)?;  // 4 bytes: u32 LE

// 而不是:
// let key_bytes = bcs::to_bytes(&(current_index as u64))?;  // 8 bytes
```

## WebSocket API 更新建議

### 添加 key_type 參數到請求

```json
{
  "type": "query_field_range",
  "table_id": "0x...",
  "current_index": 1000,
  "range": 100,
  "parent_version": null,
  "key_type": "i32"  // 新增：指定 key 類型
}
```

或者更靈活的方式：

```json
{
  "type": "query_field_range",
  "table_id": "0x...",
  "current_index": 1000,
  "range": 100,
  "parent_version": null,
  "key_type": {
    "struct": {
      "address": "0x70285592...",
      "module": "i32",
      "name": "I32"
    }
  }
}
```

## 測試驗證 (Testing & Verification)

### Python 測試腳本

```bash
# 測試 I32 struct field ID derivation
python3 examples/test_derive_i32_field_id.py

# 交互模式
python3 examples/test_derive_i32_field_id.py --interactive

# 導出結果
python3 examples/test_derive_i32_field_id.py --export
```

### 驗證 Field ID

使用 GraphQL 查詢實際的 field，然後用 Python 腳本計算 field ID，對比是否一致：

```python
from test_derive_i32_field_id import derive_dynamic_field_id_i32

parent_id = "0x260d9bb579adc62ce0d2a094c39cd062cd0db1fc0fbbc7922e8dd88e39a0da4b"
bits = 4294966990  # 從 GraphQL name.json.bits 獲取

calculated_field_id = derive_dynamic_field_id_i32(parent_id, bits)
print(f"Calculated Field ID: {calculated_field_id}")

# 然後在 Sui Explorer 或 GraphQL 中查詢這個 field_id
# 驗證它是否指向正確的 field object
```

## GraphQL 查詢對應關係

```graphql
{
  address(address: "0x260d9bb579adc62ce0d2a094c39cd062cd0db1fc0fbbc7922e8dd88e39a0da4b") {
    dynamicFields {
      nodes {
        name {
          type {
            repr  # "0x7028...::i32::I32"
          }
          json {
            bits  # 4294966990 (u32 representing i32=-306)
          }
        }
      }
    }
  }
}
```

對應到 Rust 查詢：

```rust
// name.json.bits -> current_index (as u32)
let index_u32 = 4294966990u32;  // 從 GraphQL bits 字段
let key_bytes = bcs::to_bytes(&index_u32)?;

// name.type.repr -> key_type
let key_type = TypeTag::Struct(Box::new(parse_struct_tag(
    "0x70285592c97965e811e0c6f98dccc3a9c2b4ad854b3594faab9597ada267b860::i32::I32"
)?));

// 查詢
let field_id = derive_dynamic_field_id(parent_id, &key_type, &key_bytes)?;
```

## i32 <-> u32 轉換 (i32 <-> u32 Conversion)

```rust
// i32 -> u32 bits
fn i32_to_bits(value: i32) -> u32 {
    value as u32
}

// u32 bits -> i32
fn bits_to_i32(bits: u32) -> i32 {
    bits as i32
}

// 例子:
let i32_value = -306i32;
let bits = i32_to_bits(i32_value);  // 4294966990
assert_eq!(bits, 4294966990);

let recovered = bits_to_i32(bits);
assert_eq!(recovered, -306);
```

## 下一步 (Next Steps)

1. ✅ 更新 `field_data_query.rs` 接受 `key_type` 參數
2. ✅ 更新 `custom_broadcaster.rs` 使用 I32 struct type
3. ✅ 添加 key_type 到 WebSocket API 請求
4. ✅ 測試完整的查詢流程
5. ✅ 更新文檔和示例

## 參考文件 (Reference Files)

- Python 測試: `examples/test_derive_i32_field_id.py`
- Rust 實現: `crates/sui-core/src/field_data_query.rs`
- WebSocket API: `crates/sui-core/src/custom_broadcaster.rs`
- 類型定義: `crates/sui-types/src/dynamic_field.rs`
