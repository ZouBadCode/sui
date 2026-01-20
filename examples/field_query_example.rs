// Copyright (c) Mysten Labs, Inc.
// SPDX-License-Identifier: Apache-2.0

//! Example: Using custom_broadcaster subscription data to query dynamic field ranges from RocksDB
//!
//! This example demonstrates how to:
//! 1. Subscribe to custom_broadcaster for pool/account updates
//! 2. Extract parent_id (table_id) and current_index from subscription messages
//! 3. Query field data in a range (current_index ± 100000) using read_child_object
//! 4. Decode BCS values from the retrieved fields

use std::collections::HashMap;
use std::sync::Arc;

use sui_core::authority::AuthorityStore;
use sui_core::field_data_query::{
    decode_field_value, query_field_data_range, query_field_data_range_validated, FieldData,
};
use sui_types::base_types::{ObjectID, SequenceNumber};
use sui_types::object::Object;
use sui_types::storage::ChildObjectResolver;
use sui_types::TypeTag;

/// Example: Represents the data structure stored in your dynamic fields
/// Adjust this to match your actual field value structure
#[derive(Debug, serde::Deserialize, serde::Serialize)]
pub struct TickData {
    pub price: u64,
    pub volume: u64,
    pub timestamp: u64,
}

/// Example handler for custom_broadcaster subscription messages
///
/// When you receive a message from custom_broadcaster, you can extract:
/// - parent_id: The table object ID
/// - current_index: The tick index from the transaction
///
/// Then query the surrounding range of field data
pub async fn handle_broadcaster_message(
    store: Arc<AuthorityStore>,
    parent_id: ObjectID,      // table_id from your subscription
    current_index: u64,       // tick index from the transaction
    parent_version: SequenceNumber, // version of the parent table object
) -> Result<(), Box<dyn std::error::Error>> {
    println!(
        "Received update for table {} at index {}",
        parent_id, current_index
    );

    // Query ±100000 ticks around the current index
    let range = 100_000u64;
    let key_type = TypeTag::U64; // Assuming your keys are u64 indices

    // Method 1: Direct query using AuthorityPerpetualTables
    let field_data = query_field_data_range(
        store.perpetual_tables(),
        parent_id,
        current_index,
        range,
        parent_version,
        &key_type,
    )?;

    println!("Found {} fields in range", field_data.len());

    // Process each field
    for (index, data) in field_data.iter() {
        println!(
            "Index: {}, Field ID: {}, BCS size: {} bytes",
            index,
            data.field_id,
            data.bcs_bytes.len()
        );

        // Decode the BCS bytes into your data structure
        // Option 1: If the field stores the value directly
        match decode_field_value::<TickData>(&data.bcs_bytes) {
            Ok(tick_data) => {
                println!(
                    "  Decoded: price={}, volume={}, timestamp={}",
                    tick_data.price, tick_data.volume, tick_data.timestamp
                );
            }
            Err(e) => {
                println!("  Failed to decode tick data: {}", e);
            }
        }

        // Option 2: If the field is a Field<K, V> wrapper (dynamic field structure)
        // You need to decode the outer Field structure first
        #[derive(serde::Deserialize)]
        struct Field<K, V> {
            id: sui_types::base_types::UID,
            name: K,
            value: V,
        }

        match decode_field_value::<Field<u64, TickData>>(&data.bcs_bytes) {
            Ok(field) => {
                println!(
                    "  Field wrapper - name: {}, value: {:?}",
                    field.name, field.value
                );
            }
            Err(e) => {
                println!("  Not a Field wrapper or decode failed: {}", e);
            }
        }
    }

    Ok(())
}

/// Method 2: Using ChildObjectResolver for validated queries
pub fn query_with_validation(
    resolver: &impl ChildObjectResolver,
    parent_id: ObjectID,
    current_index: u64,
    parent_version: SequenceNumber,
) -> Result<HashMap<u64, FieldData>, Box<dyn std::error::Error>> {
    let range = 100_000u64;
    let key_type = TypeTag::U64;

    // This method validates parent-child ownership
    let results = query_field_data_range_validated(
        resolver,
        parent_id,
        current_index,
        range,
        parent_version,
        &key_type,
    )?;

    Ok(results)
}

/// Example: Batch processing of multiple indices
pub fn batch_query_specific_indices(
    store: &impl ChildObjectResolver,
    parent_id: ObjectID,
    indices: &[u64],
    parent_version: SequenceNumber,
) -> Result<HashMap<u64, Object>, Box<dyn std::error::Error>> {
    let mut results = HashMap::new();
    let key_type = TypeTag::U64;

    for &index in indices {
        let key_bytes = bcs::to_bytes(&index)?;
        let field_id = sui_types::dynamic_field::derive_dynamic_field_id(
            parent_id,
            &key_type,
            &key_bytes,
        )?;

        // Use read_child_object for parent-child validation
        if let Some(obj) = store.read_child_object(&parent_id, &field_id, parent_version)? {
            results.insert(index, obj);
        }
    }

    Ok(results)
}

/// Example: Extract BCS bytes for a single index
pub fn get_field_bcs_at_index(
    store: &impl ChildObjectResolver,
    table_id: ObjectID,
    index: u64,
    parent_version: SequenceNumber,
) -> Result<Option<Vec<u8>>, Box<dyn std::error::Error>> {
    let key_bytes = bcs::to_bytes(&index)?;
    let key_type = TypeTag::U64;

    let field_id = sui_types::dynamic_field::derive_dynamic_field_id(
        table_id,
        &key_type,
        &key_bytes,
    )?;

    if let Some(obj) = store.read_child_object(&table_id, &field_id, parent_version)? {
        if let Some(move_obj) = obj.data.try_as_move() {
            return Ok(Some(move_obj.contents().to_vec()));
        }
    }

    Ok(None)
}

/// WebSocket subscriber example for custom_broadcaster
///
/// This shows how to integrate with the custom_broadcaster to get real-time updates
#[cfg(feature = "websocket-example")]
pub mod websocket_example {
    use super::*;
    use futures_util::{SinkExt, StreamExt};
    use tokio_tungstenite::{connect_async, tungstenite::protocol::Message};

    #[derive(serde::Deserialize, serde::Serialize)]
    pub enum SubscriptionMessage {
        SubscribePool(ObjectID),
        SubscribeAccount(sui_types::base_types::SuiAddress),
        SubscribeAll,
    }

    #[derive(Debug, serde::Deserialize)]
    pub struct PoolUpdate {
        pub pool_id: ObjectID,
        pub current_tick: u64,
        pub version: SequenceNumber,
        // ... other fields
    }

    pub async fn subscribe_and_query(
        broadcaster_url: &str,
        pool_id: ObjectID,
        store: Arc<AuthorityStore>,
    ) -> Result<(), Box<dyn std::error::Error>> {
        // Connect to the custom_broadcaster WebSocket
        let (ws_stream, _) = connect_async(broadcaster_url).await?;
        let (mut write, mut read) = ws_stream.split();

        // Subscribe to the specific pool
        let subscribe_msg = SubscriptionMessage::SubscribePool(pool_id);
        let msg_json = serde_json::to_string(&subscribe_msg)?;
        write.send(Message::Text(msg_json)).await?;

        println!("Subscribed to pool: {}", pool_id);

        // Listen for updates
        while let Some(msg) = read.next().await {
            let msg = msg?;
            if let Message::Text(text) = msg {
                // Parse the pool update message
                if let Ok(update) = serde_json::from_str::<PoolUpdate>(&text) {
                    println!(
                        "Pool update: pool={}, tick={}, version={}",
                        update.pool_id, update.current_tick, update.version
                    );

                    // Query field data around the current tick
                    match handle_broadcaster_message(
                        store.clone(),
                        update.pool_id,
                        update.current_tick,
                        update.version,
                    )
                    .await
                    {
                        Ok(_) => println!("Successfully queried and processed field data"),
                        Err(e) => eprintln!("Error processing field data: {}", e),
                    }
                }
            }
        }

        Ok(())
    }
}

/// Performance optimization: Parallel query with tokio
pub async fn parallel_query_range(
    store: Arc<AuthorityStore>,
    parent_id: ObjectID,
    current_index: u64,
    range: u64,
    parent_version: SequenceNumber,
) -> Result<HashMap<u64, FieldData>, Box<dyn std::error::Error>> {
    let lower_index = current_index.saturating_sub(range);
    let upper_index = current_index.saturating_add(range);
    let key_type = TypeTag::U64;

    // Split the range into chunks for parallel processing
    let chunk_size = 10_000u64;
    let mut tasks = vec![];

    for chunk_start in (lower_index..=upper_index).step_by(chunk_size as usize) {
        let chunk_end = (chunk_start + chunk_size - 1).min(upper_index);
        let store_clone = store.clone();

        let task = tokio::spawn(async move {
            let mut chunk_results = HashMap::new();

            for index in chunk_start..=chunk_end {
                let key_bytes = bcs::to_bytes(&index)?;
                let field_id = sui_types::dynamic_field::derive_dynamic_field_id(
                    parent_id,
                    &key_type,
                    &key_bytes,
                )?;

                if let Some(obj) =
                    store_clone
                        .perpetual_tables()
                        .find_object_lt_or_eq_version(field_id, parent_version)?
                {
                    if let Some(move_obj) = obj.data.try_as_move() {
                        let field_data = FieldData {
                            index,
                            field_id,
                            bcs_bytes: move_obj.contents().to_vec(),
                            version: obj.version(),
                        };
                        chunk_results.insert(index, field_data);
                    }
                }
            }

            Ok::<_, Box<dyn std::error::Error + Send + Sync>>(chunk_results)
        });

        tasks.push(task);
    }

    // Collect results from all chunks
    let mut all_results = HashMap::new();
    for task in tasks {
        let chunk_results = task.await??;
        all_results.extend(chunk_results);
    }

    Ok(all_results)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tick_data_serialization() {
        let tick = TickData {
            price: 1_000_000,
            volume: 5_000,
            timestamp: 1234567890,
        };

        let bcs_bytes = bcs::to_bytes(&tick).unwrap();
        let decoded: TickData = decode_field_value(&bcs_bytes).unwrap();

        assert_eq!(decoded.price, tick.price);
        assert_eq!(decoded.volume, tick.volume);
        assert_eq!(decoded.timestamp, tick.timestamp);
    }
}
