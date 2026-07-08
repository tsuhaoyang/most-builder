# 萃取證據：Workbench／三層組裝／WI Set API 完整合約（自 v3 程式碼直接萃取）

> 產出方式：2026-07-05 由查證 agent 直讀 `ddm-v3/apps/api/app/api/routes/{most,most_workbench_v3,wi_set_builder}.py` 與 models 萃取；**未參考 v3 markdown 文件**。此為 analysis/features 各規格的證據底稿（唯讀）。

## EXECUTABLE CONTRACT SPECIFICATION

Based on my thorough read-only analysis of routes/most.py, routes/most_workbench_v3.py, routes/wi_set_builder.py, and their supporting models/services, here is the complete structured specification:

---

# PART A: ENDPOINT SPECIFICATIONS

## routes/most.py

### GET /most/dictionary/active
- **權限**: get_current_user (any logged-in user)
- **目的**: Retrieve active MiniMOST dictionary version metadata
- **Request**: None (path/query params: none)
- **Response**:
  - `id`: string (UUID)
  - `version_name`: string
  - `is_active`: boolean
  - `source_filename`: string | null
  - `created_at`: ISO 8601 datetime | null
- **行為步驟**:
  1. Query DictionaryVersion with is_active=True
  2. If not found → raise 404 "系統尚未載入內建 MiniMOST 字典"
  3. Return dict version object
- **錯誤**:
  - 404: DictionaryVersion not found (detail: "系統尚未載入內建 MiniMOST 字典")
- **副作用**: None (read-only)

---

### GET /most/dictionary/workbench-options
- **權限**: get_current_user
- **目的**: Retrieve full dictionary structure with slot controls for workbench UI
- **Request**: None
- **Response**: Nested structure:
  - `dictionary_version_id`: string
  - `sequence_models`: array of:
    - `id`: string
    - `code`: string (GENERAL_MOVE / CONTROLLED_MOVE)
    - `name_zh`: string
    - `sequence_pattern`: string (e.g., "A B G A B P A")
    - `slots`: array of:
      - `id`: string
      - `slot_key`: string (A1, A2, A3, B1, B2, G, P, M, X, I)
      - `parameter_code`: string
      - `display_name_zh`: string
      - `slot_order`: int
      - `controls`: dict[control_key → array of]:
        - `id`: string
        - `option_code`: string
        - `control_key`: string
        - `display_text_zh`: string
        - `sentence_text_zh`: string
        - `helper_text_zh`: string | null
        - `tmu_value`: float
        - `fixed_seconds`: float | null
        - `seconds_source`: string | null
        - `display_rule`: string | null
- **行為步驟**:
  1. Get active DictionaryVersion (→ 404 if not found)
  2. Call _build_workbench_options(db, version.id)
  3. Query SequenceModels, ParameterSlots, ParameterOptions (active only)
  4. Build nested control structure by control_key
  5. Return dict with models + slots + controls
- **錯誤**:
  - 404: DictionaryVersion not found
- **副作用**: None

---

### POST /most/nl-draft
- **權限**: get_current_user
- **目的**: AI-assisted natural-language draft parsing (prefill only, not final calc)
- **Request**:
  - `text`: string, required, min_length=1, max_length=200
- **Response**:
  - `raw_text`: string
  - `suggested_sequence_model`: string (GENERAL_MOVE / CONTROLLED_MOVE)
  - `confidence`: float (0–1)
  - `context_fields`: ContextFieldsSchema | null
  - `slot_suggestions`: dict[slot_key → SlotSuggestion | null]:
    - `option_code`: string
    - `display_text_zh`: string
    - `sentence_text_zh`: string
    - `tmu_value`: float
    - `confidence`: float
    - `source`: string
    - `badge`: string
    - `control_key`: string | null (optional)
    - `modifiers`: array (optional, for P)
    - `seconds_source`: string | null (optional)
    - `fixed_seconds`: float | null (optional)
  - `missing_fields`: array[string]
  - `warnings`: array[string]
- **行為步驟**:
  1. Call parse_natural_language_draft(text, db_session)
  2. Serialize slot_suggestions into JSON-serializable dicts
  3. Return structured draft with confidence + context hints
- **錯誤**:
  - 422: Validation errors (e.g., text too long or empty)
- **副作用**: None

---

### POST /most/calculate-row
- **權限**: get_current_user
- **目的**: Stateless preview calculation (no DB save) of a single MI row
- **Request**: CalculateRowRequest
  - `action_type`: string (GENERAL_MOVE / CONTROLLED_MOVE)
  - `hand_type`: string, default="right" (left/right/both)
  - `slot_selections`: array[SlotSelectionSchema]
    - `slot_key`: string
    - `parameter_code`: string
    - `selections`: dict (control_key → option object or list)
  - `frequency`: float, default=1.0, gt=0
  - `is_simo`: boolean, default=False
  - `context_fields`: ContextFieldsSchema | null
    - `from_location`: string, default=""
    - `target_object`: string, default=""
    - `component`: string, default=""
    - `to_location`: string, default=""
    - `where_location`: string, default=""
  - `show_hand_in_sentence`: boolean, default=True
- **Response**:
  - `base_tmu`: float
  - `frequency`: float
  - `effective_tmu`: float
  - `effective_seconds`: float
  - `is_simo`: boolean
  - `total_contribution_tmu`: float
  - `total_contribution_seconds`: float
  - `slot_details`: array of:
    - `slot_key`: string
    - `parameter_code`: string
    - `tmu`: float
    - `sentence`: string
  - `system_generated_sentence_zh`: string (full composed sentence)
  - `slot_sentence_fragments`: string (concatenated slot fragments only)
- **行為步驟**:
  1. validate_frequency(frequency) → 422 if error
  2. For each slot_selection:
     - validate_selections(param_code, slot_key, selections) → 422 if errors
     - calculate_slot_tmu(param_code, slot_key, selections)
     - generate_slot_sentence(param_code, slot_key, selections)
     - Append to slot_calcs list
  3. calculate_row(slot_calcs, frequency, is_simo)
  4. _compose_full_sentence(action_type, hand_type, slot_calcs, context_dict, show_hand)
  5. Return calculation result
- **錯誤**:
  - 422: Frequency invalid or slot validation failed (detail: error msg)
- **副作用**: None

---

### POST /most/sequences (Create Sequence Item)
- **權限**: require_analyst_or_admin
- **目的**: Save a calculated MI row as a MostSequenceItem
- **Request**: SequenceCreateRequest
  - `action_type`: string
  - `hand_type`: string, default="right"
  - `sequence_pattern`: string
  - `slot_selections`: array[SlotSelectionSchema]
  - `frequency`: float, default=1.0, gt=0
  - `is_simo`: boolean, default=False
  - `simo_with_row_id`: string | null
  - `context_fields`: ContextFieldsSchema | null
  - `user_edited_sentence_zh`: string | null (manual override)
  - `manual_edit_note`: string | null
  - `show_hand_in_sentence`: boolean, default=True
- **Response**: (via _seq_response)
  - `id`: string
  - `action_type`: string
  - `hand_type`: string
  - `sequence_pattern`: string
  - `selected_slots_json`: dict (payload with slot_selections + context_fields)
  - `calculation_snapshot`: dict (frozen calc: slot_calculations, row_result, sentences, etc.)
  - `system_generated_sentence_zh`: string
  - `user_edited_sentence_zh`: string
  - `is_manual_edited`: boolean
  - `manual_edit_note`: string | null
  - `tmu`: float
  - `frequency`: float
  - `effective_tmu`: float
  - `is_simo`: boolean
  - `total_contribution_tmu`: float
  - `ct_seconds`: float
  - `effective_seconds`: float
  - `total_contribution_seconds`: float
  - `created_at`: ISO 8601
  - `created_by_user_id`: string
- **行為步驟**:
  1. Get active DictionaryVersion (→ 404)
  2. validate_frequency(frequency) → 422
  3. For each slot: validate + calculate_slot_tmu + generate_slot_sentence → 422 if errors
  4. calculate_row(slot_calcs, frequency, is_simo)
  5. Compose full sentence via _compose_full_sentence
  6. Store selected_slots_json = {slot_selections: [...], context_fields: {...}}
  7. Create calculation_snapshot = {slot_calculations, row_result, slot_sentence_fragments, generated_mi_sentence, context_fields}
  8. is_manual_edited = (user_edited_sentence_zh provided AND differs from generated)
  9. Create MostSequenceItem with all calculated fields
  10. db.add + db.commit + db.refresh
  11. Return _seq_response
- **錯誤**:
  - 404: DictionaryVersion not found
  - 422: Frequency invalid or slot validation failed
- **副作用**: 
  - DB write: MostSequenceItem created
  - Audit: created_at, updated_at set to now
  - User association: created_by_user_id = current_user.id

---

### GET /most/sequences
- **權限**: get_current_user
- **目的**: List all sequence items created by current user
- **Request**: None
- **Response**: array of _seq_response objects
- **行為步驟**:
  1. Query MostSequenceItem filtered by created_by_user_id = current_user.id
  2. Order by created_at ascending
  3. Return array of _seq_response(item)
- **錯誤**: None
- **副作用**: None

---

### GET /most/sequences/{sequence_id}
- **權限**: get_current_user
- **目的**: Retrieve a single sequence item by ID
- **Request**: sequence_id (path param)
- **Response**: _seq_response object
- **行為步驟**:
  1. Query MostSequenceItem by id
  2. If not found → 404
  3. Return _seq_response(item)
- **錯誤**:
  - 404: sequence_id not found (detail: "序列模型不存在")
- **副作用**: None

---

### PATCH /most/sequences/{sequence_id}
- **權限**: require_analyst_or_admin
- **目的**: Update a sequence item (sentence, frequency, SIMO status)
- **Request**: SequenceUpdateRequest
  - `user_edited_sentence_zh`: string | null
  - `manual_edit_note`: string | null
  - `is_manual_edited`: boolean | null
  - `frequency`: float | null
  - `is_simo`: boolean | null
- **Response**: _seq_response object (updated)
- **行為步驟**:
  1. Query MostSequenceItem by id → 404 if not found
  2. Check ownership: creator_id == current_user.id OR "admin" in user.role_names → 403 if denied
  3. If user_edited_sentence_zh provided: update + set is_manual_edited=True
  4. If manual_edit_note provided: update
  5. If is_manual_edited provided: update directly
  6. If frequency changed: validate_frequency → 422, then recalculate effective_tmu, effective_seconds, contribution fields
  7. If is_simo changed: recalculate contribution fields (set to 0 if SIMO)
  8. Set updated_at = now
  9. db.commit
  10. Return _seq_response
- **錯誤**:
  - 404: sequence_id not found
  - 403: User not owner and not admin
  - 422: Frequency invalid
- **副作用**:
  - DB write: MostSequenceItem updated
  - If frequency or SIMO changed: re-derive effective TMU/seconds

---

### DELETE /most/sequences/{sequence_id}
- **權限**: require_analyst_or_admin
- **目的**: Delete a sequence item
- **Request**: sequence_id (path)
- **Response**: `{"message": "已刪除"}`
- **行為步驟**:
  1. Query by id → 404
  2. Check ownership → 403
  3. db.delete(item)
  4. db.commit
  5. Return success message
- **錯誤**:
  - 404: Not found
  - 403: Ownership check failed
- **副作用**: DB delete, cascade deletes on MostMiStatementSequence links

---

### POST /most/mi-statements (Create MI Statement)
- **權限**: require_analyst_or_admin
- **目的**: Save a named MI statement from multiple sequence items (rows)
- **Request**: MiStatementCreateRequest
  - `name`: string
  - `sequence_item_ids`: array[string]
  - `user_edited_sentence_zh`: string | null
  - `manual_edit_note`: string | null
- **Response**: _mi_response object
- **行為步驟**:
  1. Get active DictionaryVersion → 404
  2. Query MostSequenceItems by ids → 400 if count mismatch
  3. Build rows list = [{effective_tmu, is_simo, total_contribution_tmu}, ...]
  4. Collect sentences from items → join with "；"
  5. calculate_analysis_total(rows) → {total_tmu, total_seconds, ...}
  6. is_manual_edited = (user_edited_sentence_zh provided AND differs from system_sentence)
  7. Create MostMiStatement
  8. db.add + db.flush
  9. For each sequence_item_id: create MostMiStatementSequence link with sequence_order = index
  10. db.flush
  11. Call _ensure_statement_items(statement, db) → lazily create WI-owned child snapshots
  12. Call _recalc_statement_totals(statement, db) → recompute from snapshots
  13. db.commit + db.refresh
  14. Return _mi_response(statement, db)
- **錯誤**:
  - 404: DictionaryVersion not found
  - 400: Some sequence_item_ids don't exist
- **副作用**:
  - DB write: MostMiStatement, MostMiStatementSequence, MostMiStatementItem (backfilled)
  - Totals: total_tmu, total_seconds calculated from children

---

### GET /most/mi-statements
- **權限**: get_current_user
- **目的**: List all MI statements created by current user
- **Request**: None
- **Response**: array of _mi_response objects
- **行為步驟**:
  1. Query MostMiStatement by created_by_user_id
  2. Order by created_at descending
  3. Return array of _mi_response(statement, db)
- **錯誤**: None
- **副作用**: None

---

### GET /most/mi-statements/{statement_id}
- **權限**: get_current_user
- **目的**: Retrieve a single MI statement
- **Request**: statement_id (path)
- **Response**: _mi_response object
- **行為步驟**:
  1. Query by id → 404
  2. Return _mi_response
- **錯誤**:
  - 404: statement_id not found (detail: "MI 語句不存在")
- **副作用**: None

---

### PATCH /most/mi-statements/{statement_id}
- **權限**: require_analyst_or_admin
- **目的**: Update MI statement metadata (name, sentence, edit note)
- **Request**: MiStatementUpdateRequest
  - `name`: string | null
  - `user_edited_sentence_zh`: string | null
  - `manual_edit_note`: string | null
  - `is_manual_edited`: boolean | null
- **Response**: _mi_response object
- **行為步驟**:
  1. Query by id → 404
  2. Check ownership → 403
  3. Update provided fields
  4. If user_edited_sentence_zh: set is_manual_edited=True
  5. Set updated_at = now
  6. db.commit
  7. Return _mi_response
- **錯誤**:
  - 404: Not found
  - 403: Ownership check failed
- **副作用**: DB update

---

### DELETE /most/mi-statements/{statement_id}
- **權限**: require_analyst_or_admin
- **目的**: Delete an MI statement and all its child items
- **Request**: statement_id
- **Response**: `{"message": "已刪除"}`
- **行為步驟**:
  1. Query by id → 404
  2. Check ownership → 403
  3. db.delete(statement)
  4. db.commit (cascade deletes children)
  5. Return success
- **錯誤**:
  - 404: Not found
  - 403: Ownership check failed
- **副作用**: DB delete with cascade

---

### PUT /most/mi-statements/{statement_id}/items/reorder
- **權限**: require_analyst_or_admin
- **目的**: Reorder WI child action snapshots within a MI statement
- **Request**: MiStatementItemReorderRequest
  - `item_ids`: array[string] (new order of MostMiStatementItem ids)
- **Response**: _mi_response object (updated)
- **行為步驟**:
  1. Query statement by id + ownership check → 404/403
  2. Call _ensure_statement_items(statement, db) → ensure backfill
  3. Query MostMiStatementItems by statement_id → build item map
  4. For each (order, item_id) in enumerate(item_ids):
     - If item exists: set order_index = order, updated_at = now
  5. Call _recalc_statement_totals(statement, db)
  6. db.commit + db.refresh
  7. Return _mi_response
- **錯誤**:
  - 404: statement not found
  - 403: Not owner
- **副作用**:
  - DB update: MostMiStatementItem.order_index reordered
  - Totals: recalculated from items

---

### PUT /most/mi-statements/{statement_id}/items/{item_id}
- **權限**: require_analyst_or_admin
- **目的**: Edit a WI child action snapshot (recalculate TMU/CT authoritatively)
- **Request**: MiStatementItemUpdateRequest
  - `action_type`: string | null
  - `hand_type`: string | null
  - `slot_selections`: array[SlotSelectionSchema] | null
  - `context_fields`: ContextFieldsSchema | null
  - `frequency`: float | null
  - `is_simo`: boolean | null
  - `show_hand_in_sentence`: boolean | null
  - `user_edited_sentence_zh`: string | null
- **Response**: _mi_response object
- **行為步驟**:
  1. Query statement + item by ids, check ownership → 404/403
  2. Call _ensure_statement_items(statement, db)
  3. Merge provided fields with existing: action_type = body.action_type or item.action_type, etc.
  4. validate_frequency(frequency) → 422
  5. If slot_selections provided: extract slot_sel_dicts; else: load from item.slot_selections_json
  6. If context_fields provided: extract; else: load from item.context_fields_json
  7. Call _compute_item_snapshot(action_type, hand_type, slot_sel_dicts, frequency, is_simo, ctx_dict, show_hand)
     - Runs full MiniMOST calculation engine (validate → calculate_slot_tmu → generate_slot_sentence → calculate_row)
     - Returns (row_result, generated_sentence, calculation_snapshot)
     - Raises 422 on validation error
  8. Update item fields: action_type, hand_type, show_hand_in_sentence, sentence_zh, slot_selections_json, context_fields_json, calculation_snapshot_json, base_tmu, frequency, effective_tmu, ct_seconds, is_simo, total_contribution fields, is_modified_from_source=True, updated_at=now
  9. Call _recalc_statement_totals(statement, db)
  10. db.commit + db.refresh
  11. Return _mi_response
- **錯誤**:
  - 404: statement or item not found
  - 403: Not owner
  - 422: Frequency invalid or slot validation failed
- **副作用**:
  - DB update: MostMiStatementItem recalculated + marked as modified
  - Parent totals: recalculated

---

### DELETE /most/mi-statements/{statement_id}/items/{item_id}
- **權限**: require_analyst_or_admin
- **目的**: Delete a WI child action snapshot (does not touch source action row)
- **Request**: statement_id, item_id (paths)
- **Response**: _mi_response object
- **行為步驟**:
  1. Query statement + item, check ownership → 404/403
  2. Call _ensure_statement_items(statement, db)
  3. db.delete(item)
  4. db.flush
  5. Query remaining MostMiStatementItems ordered by order_index
  6. Re-pack order_index to be contiguous (0, 1, 2, ...)
  7. Call _recalc_statement_totals(statement, db)
  8. db.commit + db.refresh
  9. Return _mi_response
- **錯誤**:
  - 404: statement or item not found
  - 403: Not owner
- **副作用**:
  - DB delete: MostMiStatementItem deleted
  - Reorder: remaining items' order_index repacked
  - Parent totals: recalculated

---

### PUT /most/admin/dictionary/options/{option_id}
- **權限**: require_admin
- **目的**: Admin-only: update a dictionary option (TMU, text, etc.)
- **Request**: body (dict with allowed fields)
  - `tmu_value`: float | null
  - `display_text_zh`: string | null
  - `sentence_text_zh`: string | null
  - `helper_text_zh`: string | null
  - `fixed_seconds`: float | null
  - `is_active`: boolean | null
- **Response**: `{"message": "已更新", "id": option_id}`
- **行為步驟**:
  1. Query ParameterOption by id → 404
  2. For each key in body:
     - If key in allowed_fields: setattr(option, key, value)
  3. db.commit
  4. Return success
- **錯誤**:
  - 404: option_id not found (detail: "選項不存在")
- **副作用**: DB update ParameterOption

---

## routes/most_workbench_v3.py

### POST /most/action-modules (Create Action Module Template)
- **權限**: require_analyst_or_admin
- **目的**: Create a reusable action module template in the pool
- **Request**: ActionModuleCreateRequest
  - `action_type`: string (GENERAL_MOVE / CONTROLLED_MOVE)
  - `hand_type`: string, default="right"
  - `slot_selections`: array[SlotSelectionSchema]
  - `context_fields`: ContextFieldsSchema | null
  - `frequency`: float, default=1.0, gt=0
  - `is_simo`: boolean, default=False
  - `source`: string, default="manual" (manual/ai/copied)
  - `show_hand_in_sentence`: boolean, default=True
- **Response**: _module_response object
  - `id`, `action_type`, `hand_type`, `generated_sentence_zh`, `context_fields`, `slot_selections`, `calculation_snapshot`, `base_tmu`, `frequency`, `effective_tmu`, `ct_seconds`, `is_simo`, `contribution_tmu`, `contribution_seconds`, `source`, `order_index`, `dictionary_version_id`, `created_at`, `updated_at`, `created_by_user_id`
- **行為步驟**:
  1. Get active DictionaryVersion → 404
  2. validate_frequency(frequency) → 422
  3. Call _calculate_module(body.slot_selections, frequency, is_simo)
     - For each slot: validate_selections → 422, calculate_slot_tmu, generate_slot_sentence
     - calculate_row(slot_calcs, frequency, is_simo)
     - Returns (slot_calcs, row_result)
  4. Extract context_fields if provided
  5. Call _compose_sentence(action_type, hand_type, slot_calcs, ctx_dict, show_hand_in_sentence)
  6. Find max order_index for current_user, set next_order = max+1 (or 0)
  7. Create ActionModuleTemplate with all calculated fields
  8. db.add + db.commit + db.refresh
  9. Return _module_response
- **錯誤**:
  - 404: DictionaryVersion not found
  - 422: Frequency invalid or slot validation failed
- **副作用**:
  - DB write: ActionModuleTemplate created
  - order_index: auto-assigned as max+1

---

### GET /most/action-modules
- **權限**: get_current_user
- **目的**: List action module templates for current user
- **Request**: None
- **Response**: array of _module_response objects
- **行為步驟**:
  1. Query ActionModuleTemplate by created_by_user_id
  2. Order by order_index ascending
  3. Return array of _module_response
- **錯誤**: None
- **副作用**: None

---

### GET /most/action-modules/{module_id}
- **權限**: get_current_user
- **目的**: Retrieve a single action module
- **Request**: module_id (path)
- **Response**: _module_response object
- **行為步驟**:
  1. Query ActionModuleTemplate by id → 404
  2. Return _module_response
- **錯誤**:
  - 404: module_id not found (detail: "動作模組不存在")
- **副作用**: None

---

### PUT /most/action-modules/{module_id}
- **權限**: require_analyst_or_admin
- **目的**: Full recalculation update of an action module
- **Request**: ActionModuleUpdateRequest
  - `action_type`: string | null
  - `hand_type`: string | null
  - `slot_selections`: array[SlotSelectionSchema] | null (triggers full recalc if provided)
  - `context_fields`: ContextFieldsSchema | null
  - `frequency`: float | null
  - `is_simo`: boolean | null
  - `order_index`: int | null
- **Response**: _module_response object (updated)
- **行為步驟**:
  1. Query by id → 404
  2. Check ownership → 403
  3. If order_index provided: set it
  4. **Branch A: slot_selections provided (full recalc)**
     - action_type = body.action_type or module.action_type, etc. (merge)
     - validate_frequency → 422
     - Call _calculate_module(body.slot_selections, frequency, is_simo)
     - Extract context_fields (from body or load from module)
     - Call _compose_sentence
     - Update all fields: action_type, hand_type, generated_sentence_zh, context_fields_json, slot_selections_json, calculation_snapshot_json, base_tmu, frequency, effective_tmu, ct_seconds, is_simo, contribution fields
  5. **Branch B: slot_selections not provided (partial update)**
     - If action_type or hand_type: update
     - If frequency or is_simo changed:
       - validate_frequency → 422
       - base = Decimal(module.base_tmu)
       - effective = base × Decimal(freq), quantize to 0.001
       - effective_seconds = effective × 0.036
       - Update frequency, effective_tmu, ct_seconds, is_simo, contribution fields (0 if SIMO, else effective)
  6. Set updated_at = now
  7. db.commit
  8. Return _module_response
- **錯誤**:
  - 404: module not found
  - 403: Not owner
  - 422: Frequency invalid or slot validation failed
- **副作用**:
  - DB update: ActionModuleTemplate recalculated

---

### DELETE /most/action-modules/{module_id}
- **權限**: require_analyst_or_admin
- **目的**: Delete an action module template
- **Request**: module_id
- **Response**: `{"message": "已刪除"}`
- **行為步驟**:
  1. Query by id → 404
  2. Check ownership → 403
  3. db.delete(module)
  4. db.commit
  5. Return success
- **錯誤**:
  - 404: Not found
  - 403: Not owner
- **副作用**: DB delete

---

### POST /most/action-modules/{module_id}/clone
- **權限**: require_analyst_or_admin
- **目的**: Clone an action module template
- **Request**: None (module_id in path)
- **Response**: _module_response object (new clone)
- **行為步驟**:
  1. Query source by id → 404
  2. Find max order_index for current_user, set next_order = max+1
  3. Create new ActionModuleTemplate (copy all fields from source, new id, new created_at/updated_at, created_by_user_id = current_user, source="copied", order_index=next_order)
  4. db.add + db.commit + db.refresh
  5. Return _module_response
- **錯誤**:
  - 404: source module not found
- **副作用**: DB write: ActionModuleTemplate cloned

---

### POST /most/action-modules/reorder
- **權限**: require_analyst_or_admin
- **目的**: Batch reorder action modules
- **Request**: ActionModuleBatchReorderRequest
  - `ordered_ids`: array[string]
- **Response**: `{"message": "已重新排序"}`
- **行為步驟**:
  1. For each (idx, module_id) in enumerate(ordered_ids):
     - Query ActionModuleTemplate by (id AND created_by_user_id == current_user)
     - If found: set order_index = idx
  2. db.commit
  3. Return success
- **錯誤**: None (silently skips missing/unauthorized items)
- **副作用**: DB update: ActionModuleTemplate.order_index for each item in list

---

### POST /most/wi-templates (Create WI Template)
- **權限**: require_analyst_or_admin
- **目的**: Create a WI template by snapshotting action modules
- **Request**: WITemplateCreateRequest
  - `wi_name`: string
  - `wi_code`: string | null
  - `description`: string | null
  - `tags`: array[string], default=[]
  - `module_ids`: array[string] (ActionModuleTemplate IDs to snapshot)
- **Response**: _wi_template_response object
- **行為步驟**:
  1. Get active DictionaryVersion → 404
  2. Query ActionModuleTemplates by ids → 400 if count mismatch
  3. Create WITemplate with wi_code, wi_name, description, tags_json
  4. db.add + db.flush
  5. total_tmu = 0.0
  6. For each (order, module_id) in enumerate(module_ids):
     - Get source module from map
     - Create WITemplateItem (snapshot all fields from module: action_type, hand_type, generated_sentence_zh, context_fields_json, slot_selections_json, calculation_snapshot_json, base_tmu, frequency, effective_tmu, ct_seconds, is_simo, contribution_tmu, contribution_seconds, order_index=order)
     - db.add
     - total_tmu += source.contribution_tmu
  7. Set wt.total_tmu, wt.total_seconds = total_tmu × 0.036, wt.module_count = len(module_ids)
  8. db.commit + db.refresh
  9. Return _wi_template_response
- **錯誤**:
  - 404: DictionaryVersion not found
  - 400: Some module_ids don't exist
- **副作用**:
  - DB write: WITemplate, WITemplateItem records created

---

### GET /most/wi-templates
- **權限**: get_current_user
- **目的**: List WI templates for current user
- **Request**: None
- **Response**: array of _wi_template_response objects
- **行為步驟**:
  1. Query WITemplate by created_by_user_id
  2. Order by created_at descending
  3. Return array of _wi_template_response
- **錯誤**: None
- **副作用**: None

---

### GET /most/wi-templates/{template_id}
- **權限**: get_current_user
- **目的**: Retrieve a single WI template
- **Request**: template_id (path)
- **Response**: _wi_template_response object
- **行為步驟**:
  1. Query by id → 404
  2. Return _wi_template_response
- **錯誤**:
  - 404: template_id not found (detail: "WI 模板不存在")
- **副作用**: None

---

### PATCH /most/wi-templates/{template_id}
- **權限**: require_analyst_or_admin
- **目的**: Update WI template metadata
- **Request**: WITemplateUpdateRequest
  - `wi_name`: string | null
  - `wi_code`: string | null
  - `description`: string | null
  - `tags`: array[string] | null
- **Response**: _wi_template_response object
- **行為步驟**:
  1. Query by id → 404
  2. Check ownership → 403
  3. Update provided fields
  4. Set updated_at = now
  5. db.commit
  6. Return _wi_template_response
- **錯誤**:
  - 404: Not found
  - 403: Not owner
- **副作用**: DB update

---

### PUT /most/wi-templates/{template_id}/items/{item_id}
- **權限**: require_analyst_or_admin
- **目的**: Update a single action module instance within a WI template (recalculate)
- **Request**: WITemplateItemUpdateRequest
  - `action_type`: string | null
  - `hand_type`: string | null
  - `slot_selections`: array[SlotSelectionSchema] | null
  - `context_fields`: ContextFieldsSchema | null
  - `frequency`: float | null
  - `is_simo`: boolean | null
- **Response**: _wi_template_response object (parent template updated)
- **行為步驟**:
  1. Query wt by template_id → 404
  2. Check ownership → 403
  3. Query item by (id, wi_template_id) → 404
  4. **Branch A: slot_selections provided (full recalc)**
     - Merge action_type, hand_type, frequency, is_simo with existing defaults
     - Call _calculate_module(body.slot_selections, frequency, is_simo)
     - Extract context_fields (from body or existing)
     - Call _compose_sentence
     - Update item: action_type, hand_type, generated_sentence_zh, context_fields_json, slot_selections_json, calculation_snapshot_json, base_tmu, frequency, effective_tmu, ct_seconds, is_simo, contribution fields
  5. **Branch B: slot_selections not provided (partial update)**
     - If frequency or is_simo changed:
       - base = Decimal(item.base_tmu)
       - effective = base × Decimal(freq), quantize
       - effective_seconds = effective × 0.036
       - Update frequency, effective_tmu, ct_seconds, is_simo, contribution fields
  6. Set item.updated_at = now
  7. Query all WITemplateItems for wt.id
  8. Recalculate wt.total_tmu = sum(contribution_tmu), wt.total_seconds, wt.module_count
  9. Set wt.updated_at = now
  10. db.commit
  11. Return _wi_template_response
- **錯誤**:
  - 404: template or item not found
  - 403: Not owner
  - 422: Frequency invalid or slot validation failed
- **副作用**:
  - DB update: WITemplateItem recalculated
  - Parent totals: wt.total_tmu/total_seconds recalculated

---

### POST /most/wi-templates/{template_id}/items/reorder
- **權限**: require_analyst_or_admin
- **目的**: Reorder action module items within a WI template
- **Request**: WITemplateReorderItemsRequest
  - `ordered_item_ids`: array[string]
- **Response**: `{"message": "已重新排序"}`
- **行為步驟**:
  1. Query wt by template_id → 404
  2. For each (idx, item_id) in enumerate(ordered_item_ids):
     - Query WITemplateItem by (id, wi_template_id)
     - If found: set order_index = idx
  3. db.commit
  4. Return success
- **錯誤**:
  - 404: template not found
- **副作用**: DB update: WITemplateItem.order_index

---

### DELETE /most/wi-templates/{template_id}
- **權限**: require_analyst_or_admin
- **目的**: Delete a WI template and all its items
- **Request**: template_id
- **Response**: `{"message": "已刪除"}`
- **行為步驟**:
  1. Query by id → 404
  2. Check ownership → 403
  3. db.delete(wt) (cascade deletes items)
  4. db.commit
  5. Return success
- **錯誤**:
  - 404: Not found
  - 403: Not owner
- **副作用**: DB delete with cascade

---

### POST /most/wi-templates/{template_id}/clone
- **權限**: require_analyst_or_admin
- **目的**: Clone a WI template with all its items
- **Request**: None
- **Response**: _wi_template_response object (new clone)
- **行為步驟**:
  1. Query source by id → 404
  2. Create new WITemplate (copy fields, new id, wi_name = "{source.wi_name} (複製)", wi_code = "{source.wi_code}-copy" if code exists else None, etc.)
  3. db.add + db.flush
  4. For each item in source.items:
     - Create WITemplateItem (snapshot all fields, new id, wi_template_id=clone.id)
     - db.add
  5. db.commit + db.refresh
  6. Return _wi_template_response
- **錯誤**:
  - 404: source not found
- **副作用**: DB write: WITemplate and WITemplateItems cloned

---

### POST /most/process-routes (Create Process Route)
- **權限**: require_analyst_or_admin
- **目的**: Create a process route by snapshotting WI templates
- **Request**: ProcessRouteCreateRequest
  - `process_name`: string
  - `process_code`: string | null
  - `description`: string | null
  - `tags`: array[string], default=[]
  - `wi_template_ids`: array[string] (WITemplate IDs to snapshot)
- **Response**: _process_route_response object
- **行為步驟**:
  1. Query WITemplates by ids → 400 if count mismatch
  2. Create ProcessRoute (process_code, process_name, description, tags_json)
  3. db.add + db.flush
  4. total_tmu = 0.0, total_modules = 0
  5. For each (order, wt_id) in enumerate(wi_template_ids):
     - Get source WITemplate from map
     - Build items_snapshot = array of {id, source_module_id, action_type, hand_type, ..., order_index}
     - Create ProcessRouteItem (wi_name, wi_code, description, module_instances_json=JSON(items_snapshot), total_tmu, total_seconds, module_count, order_index=order)
     - db.add
     - total_tmu += source.total_tmu
     - total_modules += source.module_count
  6. Set pr.total_tmu, pr.total_seconds, pr.wi_count, pr.module_count
  7. db.commit + db.refresh
  8. Return _process_route_response
- **錯誤**:
  - 400: Some wi_template_ids don't exist
- **副作用**:
  - DB write: ProcessRoute, ProcessRouteItem records created

---

### GET /most/process-routes
- **權限**: get_current_user
- **目的**: List process routes for current user
- **Request**: None
- **Response**: array of _process_route_response objects
- **行為步驟**:
  1. Query ProcessRoute by created_by_user_id
  2. Order by created_at descending
  3. Return array of _process_route_response
- **錯誤**: None
- **副作用**: None

---

### GET /most/process-routes/{route_id}
- **權限**: get_current_user
- **目的**: Retrieve a single process route
- **Request**: route_id (path)
- **Response**: _process_route_response object
- **行為步驟**:
  1. Query by id → 404
  2. Return _process_route_response
- **錯誤**:
  - 404: route_id not found (detail: "作業流程不存在")
- **副作用**: None

---

### PATCH /most/process-routes/{route_id}
- **權限**: require_analyst_or_admin
- **目的**: Update process route metadata
- **Request**: ProcessRouteUpdateRequest
  - `process_name`: string | null
  - `process_code`: string | null
  - `description`: string | null
  - `tags`: array[string] | null
- **Response**: _process_route_response object
- **行為步驟**:
  1. Query by id → 404
  2. Check ownership → 403
  3. Update provided fields
  4. Set updated_at = now
  5. db.commit
  6. Return _process_route_response
- **錯誤**:
  - 404: Not found
  - 403: Not owner
- **副作用**: DB update

---

### POST /most/process-routes/{route_id}/items/reorder
- **權限**: require_analyst_or_admin
- **目的**: Reorder WI instances within a process route
- **Request**: ProcessRouteReorderRequest
  - `ordered_item_ids`: array[string]
- **Response**: `{"message": "已重新排序"}`
- **行為步驟**:
  1. Query pr by route_id → 404
  2. For each (idx, item_id) in enumerate(ordered_item_ids):
     - Query ProcessRouteItem by (id, process_route_id)
     - If found: set order_index = idx
  3. db.commit
  4. Return success
- **錯誤**:
  - 404: route not found
- **副作用**: DB update: ProcessRouteItem.order_index

---

### DELETE /most/process-routes/{route_id}
- **權限**: require_analyst_or_admin
- **目的**: Delete a process route and all its items
- **Request**: route_id
- **Response**: `{"message": "已刪除"}`
- **行為步驟**:
  1. Query by id → 404
  2. Check ownership → 403
  3. db.delete(pr) (cascade deletes items)
  4. db.commit
  5. Return success
- **錯誤**:
  - 404: Not found
  - 403: Not owner
- **副作用**: DB delete with cascade

---

### POST /most/process-routes/{route_id}/clone
- **權限**: require_analyst_or_admin
- **目的**: Clone a process route with all WI instances
- **Request**: None
- **Response**: _process_route_response object (new clone)
- **行為步驟**:
  1. Query source by id → 404
  2. Create new ProcessRoute (copy fields, new id, process_name = "{source.process_name} (複製)", process_code = "{source.process_code}-copy" if code exists else None, etc.)
  3. db.add + db.flush
  4. For each item in source.wi_instances:
     - Create ProcessRouteItem (copy all fields, new id, process_route_id=clone.id)
     - db.add
  5. db.commit + db.refresh
  6. Return _process_route_response
- **錯誤**:
  - 404: source not found
- **副作用**: DB write: ProcessRoute and ProcessRouteItems cloned

---

### POST /most/process-routes/{route_id}/items/{item_id}/apply-to-template
- **權限**: require_analyst_or_admin
- **目的**: Apply a process WI instance's changes back to the WI Pool template (reverse sync)
- **Request**: (body: ApplyBackToTemplateRequest, empty)
- **Response**: _wi_template_response object (updated template)
- **行為步驟**:
  1. Query pr by route_id → 404
  2. Query item by (item_id, process_route_id) → 404
  3. If not item.source_wi_template_id: 400 "此項目無關聯 WI 模板"
  4. Query wt by source_wi_template_id → 404
  5. Check ownership of wt → 403
  6. Extract module_instances from item.module_instances_json
  7. Query and delete all existing WITemplateItems for wt.id
  8. For each module_instance in module_instances:
     - Create new WITemplateItem (extract all fields from MI: action_type, hand_type, generated_sentence_zh, context_fields, slot_selections, calculation_snapshot, base_tmu, frequency, effective_tmu, ct_seconds, is_simo, contribution fields, order_index)
     - db.add
  9. Update wt: wi_name = item.wi_name, total_tmu = item.total_tmu, total_seconds = item.total_seconds, module_count = item.module_count, updated_at = now
  10. db.commit
  11. Return _wi_template_response
- **錯誤**:
  - 404: route not found, item not found, or linked template not found
  - 400: item has no source_wi_template_id
  - 403: Not owner of WI template
- **副作用**:
  - DB update: WITemplate and WITemplateItems replaced from process instance snapshot

---

## routes/wi_set_builder.py

### GET /most/wi-library
- **權限**: get_current_user
- **目的**: List old MOST workbench MI Statements (WI 大綱) as the WI Pool source for backward compatibility
- **Request**: 
  - `q`: string | None (Query param, keyword search)
- **Response**: array of:
  - `id`: string (MostMiStatement.id)
  - `source`: string ("MOST_LEGACY_WI_OUTLINE")
  - `wi_code`: string | null (always None)
  - `wi_name`: string (MostMiStatement.name)
  - `wi_sentence`: string (user_edited or system_generated)
  - `description`: string (same as wi_sentence)
  - `action_count`: int (number of child sequences)
  - `total_tmu`: float
  - `total_seconds`: float
  - `child_actions`: array of:
    - `sentence`: string
    - `base_tmu`: float
    - `frequency`: float
    - `effective_tmu`: float
    - `ct_seconds`: float
    - `is_simo`: boolean
  - `created_at`: ISO 8601
- **行為步驟**:
  1. Query MostMiStatement
  2. If q provided: keyword search via OR on (name, system_sentence, user_sentence, OR child sequence sentences)
  3. Order by created_at descending
  4. For each statement:
     - Load MostMiStatementSequence links ordered by sequence_order
     - Load linked MostSequenceItems in order
     - Build child_actions array from sequences
     - Compose response object
  5. Return array
- **錯誤**: None
- **副作用**: None (read-only)

---

### GET /most/wi-set-projects
- **權限**: get_current_user
- **目的**: List all WI Set Projects (global, not user-filtered)
- **Request**: None
- **Response**: array of _serialize_project objects
  - `id`, `project_code`, `project_name`, `site`, `bu`, `process`, `family`, `model`, `description`, `status`, `total_wi_count`, `total_action_count`, `total_tmu`, `total_seconds`, `items` (array of _serialize_item), `created_at`, `updated_at`, `created_by_user_id`
- **行為步驟**:
  1. Query WISetProject (no user filter)
  2. Order by updated_at descending
  3. Return array of _serialize_project
- **錯誤**: None
- **副作用**: None

---

### POST /most/wi-set-projects (Create WI Set Project)
- **權限**: require_analyst_or_admin
- **目的**: Create a new WI Set Project
- **Request**: WISetProjectCreateRequest
  - `project_code`: string | null
  - `project_name`: string
  - `site`: string
  - `bu`: string
  - `process`: string
  - `family`: string
  - `model`: string
  - `description`: string | null
  - `status`: string, default="draft" (draft/active/archived)
- **Response**: _serialize_project object
- **行為步驟**:
  1. Create WISetProject with all fields
  2. Set created_by_user_id = current_user.id
  3. Set created_at, updated_at = now
  4. db.add + db.commit + db.refresh
  5. Return _serialize_project
- **錯誤**: None
- **副作用**: DB write: WISetProject created

---

### GET /most/wi-set-projects/{project_id}
- **權限**: get_current_user
- **目的**: Retrieve a WI Set Project with all its items
- **Request**: project_id (path)
- **Response**: _serialize_project object
- **行為步驟**:
  1. Query by id → 404
  2. Return _serialize_project
- **錯誤**:
  - 404: project_id not found (detail: "專案不存在")
- **副作用**: None

---

### PUT /most/wi-set-projects/{project_id}
- **權限**: require_analyst_or_admin
- **目的**: Update WI Set Project metadata
- **Request**: WISetProjectUpdateRequest
  - `project_code`, `project_name`, `site`, `bu`, `process`, `family`, `model`, `description`, `status`: all optional strings
- **Response**: _serialize_project object
- **行為步驟**:
  1. Query by id → 404
  2. For each field in [project_code, project_name, site, bu, process, family, model, description, status]:
     - If provided in request: update
  3. Set updated_at = now
  4. db.commit + db.refresh
  5. Return _serialize_project
- **錯誤**:
  - 404: project not found
- **副作用**: DB update

---

### DELETE /most/wi-set-projects/{project_id}
- **權限**: require_analyst_or_admin
- **目的**: Delete a WI Set Project and all its items
- **Request**: project_id
- **Response**: `{"ok": true}`
- **行為步驟**:
  1. Query by id → 404
  2. db.delete(project) (cascade deletes items)
  3. db.commit
  4. Return success
- **錯誤**:
  - 404: project not found
- **副作用**: DB delete with cascade

---

### POST /most/wi-set-projects/{project_id}/items
- **權限**: require_analyst_or_admin
- **目的**: Add old MOST MI Statement (WI 大綱) snapshots to a project
- **Request**: AddItemsRequest
  - `wi_ids`: array[string] (MostMiStatement IDs)
- **Response**: _serialize_project object (updated)
- **行為步驟**:
  1. Query project by id → 404
  2. Find max order_index from project.items (default -1)
  3. now = datetime.now(timezone.utc)
  4. For each wi_id in wi_ids:
     - Query MostMiStatement by id (skip if not found)
     - Increment max_order
     - Load MostMiStatementSequence links in order
     - Load linked MostSequenceItems
     - Build child_actions array with full details (id, action_type, hand_type, sentence, base_tmu, frequency, effective_tmu, ct_seconds, is_simo, total_contribution_tmu, total_contribution_seconds)
     - Build wi_snapshot_json = JSON({source, mi_statement_id, wi_name, wi_sentence, total_tmu, total_seconds, action_count, child_actions})
     - Create WISetProjectItem (id, project_id, source_wi_id, order_index, wi_code_snapshot=None, wi_name_snapshot, wi_sentence_snapshot, action_count_snapshot, total_tmu_snapshot, total_seconds_snapshot, wi_snapshot_json)
     - db.add
  5. db.flush + db.refresh(project)
  6. Call _recalculate_project_totals(project):
     - total_wi_count = len(items)
     - total_action_count = sum(action_count_snapshot)
     - total_tmu = sum(total_tmu_snapshot)
     - total_seconds = sum(total_seconds_snapshot)
     - updated_at = now
  7. db.commit + db.refresh
  8. Return _serialize_project
- **錯誤**:
  - 404: project not found
- **副作用**:
  - DB write: WISetProjectItem records created
  - Parent totals: recalculated

---

### PUT /most/wi-set-projects/{project_id}/items/reorder
- **權限**: require_analyst_or_admin
- **目的**: Reorder WI items within a project
- **Request**: ReorderItemsRequest
  - `ordered_item_ids`: array[string]
- **Response**: _serialize_project object
- **行為步驟**:
  1. Query project by id → 404
  2. Build item_map from project.items
  3. For each (idx, item_id) in enumerate(ordered_item_ids):
     - If item_id in item_map: set order_index = idx, updated_at = now
  4. Set project.updated_at = now
  5. db.commit + db.refresh
  6. Return _serialize_project
- **錯誤**:
  - 404: project not found
- **副作用**: DB update: WISetProjectItem.order_index + project.updated_at

---

### DELETE /most/wi-set-projects/{project_id}/items/{item_id}
- **權限**: require_analyst_or_admin
- **目的**: Remove a WI item from a project
- **Request**: project_id, item_id (paths)
- **Response**: _serialize_project object
- **行為步驟**:
  1. Query item by (id, project_id) → 404
  2. db.delete(item)
  3. db.flush
  4. Query project by project_id (should exist, already fetched)
  5. Call _recalculate_project_totals(project)
  6. db.commit + db.refresh
  7. Return _serialize_project
- **錯誤**:
  - 404: item not found
- **副作用**:
  - DB delete: WISetProjectItem deleted
  - Parent totals: recalculated

---

### POST /most/wi-set-projects/{project_id}/duplicate
- **權限**: require_analyst_or_admin
- **目的**: Duplicate a WI Set Project with all its items
- **Request**: None
- **Response**: _serialize_project object (new)
- **行為步驟**:
  1. Query source by id → 404
  2. now = datetime.now(timezone.utc)
  3. Create new WISetProject:
     - id = uuid
     - created_by_user_id = current_user.id
     - project_code = "{source.project_code}-copy" if code exists else None
     - project_name = "{source.project_name} (副本)"
     - site, bu, process, family, model, description = copy from source
     - status = "draft"
     - total_wi_count, total_action_count, total_tmu, total_seconds = copy from source
     - created_at, updated_at = now
  4. db.add
  5. For each item in source.items:
     - Create new WISetProjectItem (copy all fields including wi_snapshot_json, new id, project_id=new_project.id)
     - db.add
  6. db.commit + db.refresh
  7. Return _serialize_project
- **錯誤**:
  - 404: source not found
- **副作用**: DB write: WISetProject and WISetProjectItems cloned

---

# PART B: TABLE SCHEMA SPECIFICATIONS

## MostSequenceItem
- `id`: String(36), PK, UUID
- `dictionary_version_id`: String(36), FK, not nullable
- `created_by_user_id`: String(36), FK, not nullable
- `action_type`: String(50), not nullable (GENERAL_MOVE / CONTROLLED_MOVE)
- `sequence_model_code`: String(50), not nullable
- `hand_type`: String(20), not nullable (left/right/both)
- `sequence_pattern`: String(50), not nullable (e.g., "A B G A B P A")
- `selected_slots_json`: Text, not nullable (JSON: {slot_selections, context_fields})
- `calculation_snapshot_json`: Text, nullable (JSON: frozen calc result)
- `system_generated_sentence_zh`: Text, nullable
- `user_edited_sentence_zh`: Text, nullable
- `is_manual_edited`: Boolean, default=False, not nullable
- `manual_edit_note`: Text, nullable
- `tmu`: Float, default=0.0, not nullable (base_tmu, sum of slot TMUs)
- `frequency`: Float, default=1.0, not nullable (must be > 0)
- `effective_tmu`: Float, default=0.0, not nullable (tmu × frequency)
- `is_simo`: Boolean, default=False, not nullable
- `simo_with_row_id`: String(36), nullable (optional ref to another row)
- `total_contribution_tmu`: Float, default=0.0, not nullable (0 if SIMO, else effective_tmu)
- `ct_seconds`: Float, default=0.0, not nullable (effective_tmu × 0.036)
- `effective_seconds`: Float, default=0.0, not nullable (same as ct_seconds)
- `total_contribution_seconds`: Float, default=0.0, not nullable (0 if SIMO)
- `created_at`: DateTime(timezone=True), default=_utcnow, not nullable
- `updated_at`: DateTime(timezone=True), default=_utcnow, not nullable

---

## MostMiStatement
- `id`: String(36), PK, UUID
- `name`: String(200), not nullable
- `dictionary_version_id`: String(36), FK, not nullable
- `created_by_user_id`: String(36), FK, not nullable
- `system_generated_sentence_zh`: Text, nullable
- `user_edited_sentence_zh`: Text, nullable
- `is_manual_edited`: Boolean, default=False, not nullable
- `manual_edit_note`: Text, nullable
- `total_tmu`: Float, default=0.0, not nullable (sum of child contribution_tmu, excl SIMO)
- `total_seconds`: Float, default=0.0, not nullable (total_tmu × 0.036)
- `created_at`: DateTime(timezone=True), default=_utcnow, not nullable
- `updated_at`: DateTime(timezone=True), default=_utcnow, not nullable

---

## MostMiStatementSequence
- `id`: String(36), PK, UUID
- `mi_statement_id`: String(36), FK (ondelete=CASCADE), not nullable
- `sequence_item_id`: String(36), FK (ondelete=CASCADE), not nullable
- `sequence_order`: Integer, default=0, not nullable (ordering link)

---

## MostMiStatementItem
- `id`: String(36), PK, UUID
- `statement_id`: String(36), FK (ondelete=CASCADE), not nullable
- `source_sequence_id`: String(36), nullable (provenance only, not a live link)
- `order_index`: Integer, default=0, not nullable
- `action_type`: String(50), not nullable (GENERAL_MOVE / CONTROLLED_MOVE)
- `hand_type`: String(20), default="right", not nullable
- `sentence_zh`: Text, nullable
- `slot_selections_json`: Text, not nullable (JSON: SlotSelectionInput[])
- `context_fields_json`: Text, nullable (JSON: ContextFields)
- `calculation_snapshot_json`: Text, nullable (JSON: frozen calc)
- `base_tmu`: Float, default=0.0, not nullable
- `frequency`: Float, default=1.0, not nullable
- `effective_tmu`: Float, default=0.0, not nullable
- `ct_seconds`: Float, default=0.0, not nullable
- `is_simo`: Boolean, default=False, not nullable
- `total_contribution_tmu`: Float, default=0.0, not nullable
- `total_contribution_seconds`: Float, default=0.0, not nullable
- `show_hand_in_sentence`: Boolean, default=True, not nullable
- `is_modified_from_source`: Boolean, default=False, not nullable
- `created_at`: DateTime(timezone=True), default=_utcnow, not nullable
- `updated_at`: DateTime(timezone=True), default=_utcnow, not nullable

---

## ActionModuleTemplate
- `id`: String(36), PK, UUID
- `dictionary_version_id`: String(36), FK, not nullable
- `created_by_user_id`: String(36), FK, not nullable
- `action_type`: String(50), not nullable (GENERAL_MOVE / CONTROLLED_MOVE)
- `hand_type`: String(20), default="right", not nullable
- `generated_sentence_zh`: Text, nullable
- `context_fields_json`: Text, nullable (JSON: ContextFields)
- `slot_selections_json`: Text, not nullable (JSON: SlotSelectionInput[])
- `calculation_snapshot_json`: Text, nullable (JSON: {slot_calculations, row_result})
- `base_tmu`: Float, default=0.0, not nullable
- `frequency`: Float, default=1.0, not nullable
- `effective_tmu`: Float, default=0.0, not nullable
- `ct_seconds`: Float, default=0.0, not nullable
- `is_simo`: Boolean, default=False, not nullable
- `contribution_tmu`: Float, default=0.0, not nullable (0 if SIMO, else effective)
- `contribution_seconds`: Float, default=0.0, not nullable (0 if SIMO, else effective_seconds)
- `source`: String(20), default="manual", not nullable (manual/ai/copied)
- `order_index`: Integer, default=0, not nullable
- `created_at`: DateTime(timezone=True), default=_utcnow, not nullable
- `updated_at`: DateTime(timezone=True), default=_utcnow, not nullable

---

## WITemplate
- `id`: String(36), PK, UUID
- `dictionary_version_id`: String(36), FK, not nullable
- `created_by_user_id`: String(36), FK, not nullable
- `wi_code`: String(50), nullable
- `wi_name`: String(200), not nullable
- `description`: Text, nullable
- `tags_json`: Text, nullable (JSON: string[])
- `total_tmu`: Float, default=0.0, not nullable (sum of item contribution_tmu)
- `total_seconds`: Float, default=0.0, not nullable (total_tmu × 0.036)
- `module_count`: Integer, default=0, not nullable
- `created_at`: DateTime(timezone=True), default=_utcnow, not nullable
- `updated_at`: DateTime(timezone=True), default=_utcnow, not nullable

---

## WITemplateItem
- `id`: String(36), PK, UUID
- `wi_template_id`: String(36), FK (ondelete=CASCADE), not nullable
- `source_module_id`: String(36), nullable (optional ref to ActionModuleTemplate)
- `action_type`: String(50), not nullable
- `hand_type`: String(20), default="right", not nullable
- `generated_sentence_zh`: Text, nullable
- `context_fields_json`: Text, nullable (JSON: ContextFields)
- `slot_selections_json`: Text, not nullable (JSON: SlotSelectionInput[])
- `calculation_snapshot_json`: Text, nullable (JSON: frozen calc)
- `base_tmu`: Float, default=0.0, not nullable
- `frequency`: Float, default=1.0, not nullable
- `effective_tmu`: Float, default=0.0, not nullable
- `ct_seconds`: Float, default=0.0, not nullable
- `is_simo`: Boolean, default=False, not nullable
- `contribution_tmu`: Float, default=0.0, not nullable
- `contribution_seconds`: Float, default=0.0, not nullable
- `order_index`: Integer, default=0, not nullable
- `created_at`: DateTime(timezone=True), default=_utcnow, not nullable
- `updated_at`: DateTime(timezone=True), default=_utcnow, not nullable

---

## ProcessRoute
- `id`: String(36), PK, UUID
- `created_by_user_id`: String(36), FK, not nullable
- `process_code`: String(50), nullable
- `process_name`: String(200), not nullable
- `description`: Text, nullable
- `tags_json`: Text, nullable (JSON: string[])
- `total_tmu`: Float, default=0.0, not nullable (sum of WI items' total_tmu)
- `total_seconds`: Float, default=0.0, not nullable (total_tmu × 0.036)
- `wi_count`: Integer, default=0, not nullable (number of WI instances)
- `module_count`: Integer, default=0, not nullable (total modules across all WIs)
- `created_at`: DateTime(timezone=True), default=_utcnow, not nullable
- `updated_at`: DateTime(timezone=True), default=_utcnow, not nullable

---

## ProcessRouteItem
- `id`: String(36), PK, UUID
- `process_route_id`: String(36), FK (ondelete=CASCADE), not nullable
- `source_wi_template_id`: String(36), nullable (optional ref to WITemplate)
- `wi_name`: String(200), not nullable
- `wi_code`: String(50), nullable
- `description`: Text, nullable
- `module_instances_json`: Text, not nullable (JSON snapshot of WITemplateItem-like objects)
- `total_tmu`: Float, default=0.0, not nullable
- `total_seconds`: Float, default=0.0, not nullable
- `module_count`: Integer, default=0, not nullable
- `order_index`: Integer, default=0, not nullable
- `created_at`: DateTime(timezone=True), default=_utcnow, not nullable
- `updated_at`: DateTime(timezone=True), default=_utcnow, not nullable

---

## WISetProject
- `id`: String(36), PK, UUID
- `created_by_user_id`: String(36), FK, not nullable
- `project_code`: String(100), nullable
- `project_name`: String(300), not nullable
- `site`: String(100), not nullable
- `bu`: String(100), not nullable
- `process`: String(100), not nullable
- `family`: String(100), not nullable
- `model`: String(100), not nullable
- `description`: Text, nullable
- `status`: String(20), default="draft", not nullable (draft/active/archived)
- `total_wi_count`: Integer, default=0, not nullable (count of items)
- `total_action_count`: Integer, default=0, not nullable (sum of action counts)
- `total_tmu`: Float, default=0.0, not nullable (sum of item totals)
- `total_seconds`: Float, default=0.0, not nullable (sum of item seconds)
- `created_at`: DateTime(timezone=True), default=_utcnow, not nullable
- `updated_at`: DateTime(timezone=True), default=_utcnow, not nullable

---

## WISetProjectItem
- `id`: String(36), PK, UUID
- `project_id`: String(36), FK (ondelete=CASCADE), not nullable
- `source_wi_id`: String(36), nullable (ref to MostMiStatement from legacy MOST)
- `order_index`: Integer, default=0, not nullable
- `wi_code_snapshot`: String(50), nullable
- `wi_name_snapshot`: String(200), not nullable
- `wi_sentence_snapshot`: Text, nullable
- `action_count_snapshot`: Integer, default=0, not nullable
- `total_tmu_snapshot`: Float, default=0.0, not nullable
- `total_seconds_snapshot`: Float, default=0.0, not nullable
- `wi_snapshot_json`: Text, nullable (JSON: full WI data snapshot)
- `note`: Text, nullable (project-specific annotation)
- `created_at`: DateTime(timezone=True), default=_utcnow, not nullable
- `updated_at`: DateTime(timezone=True), default=_utcnow, not nullable

---

# PART C: SHARED HELPERS & JSON SHAPES

## _compose_full_sentence(action_type, hand_type, slot_calcs, context_fields, show_hand_in_sentence)

**精確規則**:
1. **slot_calcs**: list of {slot_key, parameter_code, tmu, sentence}
2. **context_fields**: {from_location, target_object, component, to_location, where_location} or None
3. **show_hand_in_sentence**: controls whether hand label appears
4. **Hand Label Lookup**: {"left": "左手", "right": "右手", "both": "雙手"}
5. **Order (GENERAL_MOVE)**:
   - [hand] + "從{from_location}" + A1 + B1 + G + {target_object} + {component} + A2 + B2 + P + "至{to_location}" + A3
6. **Order (CONTROLLED_MOVE)**:
   - [hand] + "從{from_location}" + A1 + B1 + G + {target_object} + {component} + M + "至{to_location}" + X + I + {where_location} + A3
7. **Empty fields**: Skipped (no placeholder added)
8. **Slot fragments**: Looked up from slot_calcs by slot_key (A1, A2, A3, B1, B2, G, P, M, X, I)
9. **Result**: Concatenated Chinese text (no spaces)

---

## _ensure_statement_items(statement, db) → list[MostMiStatementItem]

**行為**:
1. Query existing MostMiStatementItems by statement_id, order by order_index
2. If items exist: return them (backfill is one-time only)
3. If no items: **lazy backfill**:
   - Query MostMiStatementSequence links by mi_statement_id, ordered by sequence_order
   - For each link, fetch the referenced MostSequenceItem
   - Extract slot_selections + context_fields from MostSequenceItem using _extract_seq_payload helper
   - Create a **new independent MostMiStatementItem** (independent snapshot, never mutates source)
   - Copy all fields: action_type, hand_type, user_edited_sentence_zh or system_generated, slot_selections, context_fields, calculation_snapshot, base_tmu, frequency, effective_tmu, ct_seconds, is_simo, total_contribution fields
   - Set order_index = sequence order, is_modified_from_source=False, show_hand_in_sentence=True
   - Set source_sequence_id for provenance tracking (not a live link)
   - db.add all, then db.commit
4. Query and return all MostMiStatementItems ordered by order_index
5. **One-time guarantee**: After backfill, subsequent calls return the existing child items (no re-backfill)

---

## _recalc_statement_totals(statement, db) → None

**行為**:
1. Query MostMiStatementItems by statement_id, ordered by order_index
2. Build rows list: [{effective_tmu, is_simo, total_contribution_tmu}, ...]
3. Call calculate_analysis_total(rows) → {total_tmu, total_seconds, ...}
4. Re-compose system_generated_sentence_zh:
   - Collect sentence_zh from each item (if non-empty)
   - Join with "；" separator
   - Store result in statement.system_generated_sentence_zh (NOT user_edited_sentence_zh)
5. Update statement: total_tmu, total_seconds, system_generated_sentence_zh, updated_at = now
6. **Does NOT commit** (caller handles db.commit)
7. **Child snapshots are source of truth** (never reads source action rows)

---

## _extract_seq_payload(seq: MostSequenceItem) → (list[dict], dict | None)

**行為**:
1. Try to parse seq.selected_slots_json as JSON
2. If parsed result is dict with "slot_selections" key (new format):
   - Return (stored["slot_selections"], stored.get("context_fields"))
3. If parsed result is list (legacy bare-list format):
   - Extract context_fields from seq.calculation_snapshot_json if available
   - Return (stored list, context from snapshot or None)
4. If any JSON error: return ([], None)

---

## slot_selections_json Shape

**JSON Structure** (stored in MostSequenceItem / ActionModuleTemplate / WITemplateItem):
```json
{
  "slot_selections": [
    {
      "slot_key": "A1",
      "parameter_code": "A",
      "selections": {
        "reach_distance": {"tmu_value": 2.5, ...},
        "hand_degree": {...},
        "foot_step": {...}
      }
    },
    {
      "slot_key": "B1",
      "parameter_code": "B",
      "selections": {
        "option": {"tmu_value": 1.0, "sentence_text_zh": "轉身", ...}
      }
    },
    {
      "slot_key": "G",
      "parameter_code": "G",
      "selections": {
        "option": {"tmu_value": 3.0, "sentence_text_zh": "拿取", ...},
        "repeat_count": 1
      }
    },
    {
      "slot_key": "P",
      "parameter_code": "P",
      "selections": {
        "base_action": {"tmu_value": 2.0, "sentence_text_zh": "組裝", ...},
        "modifiers": [
          {"option_code": "P_INSERT", "tmu_value": 1.5, ...}
        ]
      }
    },
    {
      "slot_key": "M",
      "parameter_code": "M",
      "selections": {
        "verb": {"tmu_value": 3.0, "sentence_text_zh": "推", ...},
        "hand_degree": {...},
        "foot_step": {...},
        "repeat_count": 16
      }
    },
    {
      "slot_key": "X",
      "parameter_code": "X",
      "selections": {
        "x_option": {"tmu_value": 5.556, "sentence_text_zh": "測試", "fixed_seconds": 0.2},
        "repeat_count": 1
      }
    }
  ],
  "context_fields": {
    "from_location": "工作台左",
    "target_object": "螺釘",
    "component": "金屬片",
    "to_location": "組件上",
    "where_location": ""
  }
}
```

---

## context_fields_json Shape

**JSON Structure**:
```json
{
  "from_location": "string (where motion starts)",
  "target_object": "string (what is being moved)",
  "component": "string (part of target or related detail)",
  "to_location": "string (where motion ends)",
  "where_location": "string (additional location for CONTROLLED_MOVE)"
}
```
- All fields optional (default empty string)
- Used in _compose_full_sentence to inject context into composed sentence

---

## module_instances_json Shape (ProcessRouteItem)

**JSON Structure** (snapshot of WITemplateItem-like objects):
```json
[
  {
    "id": "uuid",
    "source_module_id": "uuid or null",
    "action_type": "GENERAL_MOVE",
    "hand_type": "right",
    "generated_sentence_zh": "右手從工作台拿取螺釘組裝至成品",
    "context_fields": {
      "from_location": "...",
      "target_object": "...",
      ...
    },
    "slot_selections": [...],
    "calculation_snapshot": {
      "slot_calculations": [...],
      "row_result": {...}
    },
    "base_tmu": 5.0,
    "frequency": 1.0,
    "effective_tmu": 5.0,
    "ct_seconds": 0.18,
    "is_simo": false,
    "contribution_tmu": 5.0,
    "contribution_seconds": 0.18,
    "order_index": 0
  },
  ...
]
```

---

## calculation_snapshot_json Shape

**JSON Structure** (frozen calc result for audit):
```json
{
  "slot_calculations": [
    {
      "slot_key": "A1",
      "parameter_code": "A",
      "tmu": 2.5,
      "sentence": "",
      "repeat_count": 1
    },
    {
      "slot_key": "G",
      "parameter_code": "G",
      "tmu": 3.0,
      "sentence": "拿取",
      "repeat_count": 1
    },
    ...
  ],
  "row_result": {
    "base_tmu": 10.5,
    "frequency": 1.0,
    "effective_tmu": 10.5,
    "effective_seconds": 0.378,
    "is_simo": false,
    "total_contribution_tmu": 10.5,
    "total_contribution_seconds": 0.378
  },
  "slot_sentence_fragments": "拿取組裝",
  "generated_mi_sentence": "右手從工作台拿取螺釘組裝至成品",
  "context_fields": {
    "from_location": "工作台",
    "target_object": "螺釘",
    ...
  }
}
```

---

# PART D: ORDERING & REORDERING MECHANISMS

## order_index Maintenance Rules

1. **ActionModuleTemplate**: order_index assigned at creation as max(created_by_user) + 1
2. **WITemplateItem**: order_index assigned sequentially (0, 1, 2, ...) when created as part of WI template snapshot
3. **ProcessRouteItem**: order_index assigned sequentially (0, 1, 2, ...) when created as part of process route snapshot
4. **MostMiStatementItem**: order_index assigned as sequence_order when lazily backfilled; re-packed to be contiguous (0, 1, ...) after deletion

## Reorder Endpoint Input Shapes

### ActionModuleBatchReorderRequest
```
{
  "ordered_ids": ["uuid1", "uuid2", "uuid3"]
}
```
- Endpoint: POST /most/action-modules/reorder
- Behavior: For each (idx, id), set ActionModuleTemplate[id].order_index = idx (user-scoped)

### WITemplateReorderItemsRequest
```
{
  "ordered_item_ids": ["item_uuid1", "item_uuid2", ...]
}
```
- Endpoint: POST /most/wi-templates/{template_id}/items/reorder
- Behavior: For each (idx, item_id), set WITemplateItem[item_id].order_index = idx

### ProcessRouteReorderRequest
```
{
  "ordered_item_ids": ["item_uuid1", "item_uuid2", ...]
}
```
- Endpoint: POST /most/process-routes/{route_id}/items/reorder
- Behavior: For each (idx, item_id), set ProcessRouteItem[item_id].order_index = idx

### MiStatementItemReorderRequest
```
{
  "item_ids": ["item_uuid1", "item_uuid2", ...]
}
```
- Endpoint: PUT /most/mi-statements/{statement_id}/items/reorder
- Behavior: For each (idx, item_id), set MostMiStatementItem[item_id].order_index = idx

### ReorderItemsRequest (WI Set Projects)
```
{
  "ordered_item_ids": ["item_uuid1", "item_uuid2", ...]
}
```
- Endpoint: PUT /most/wi-set-projects/{project_id}/items/reorder
- Behavior: For each (idx, item_id), set WISetProjectItem[item_id].order_index = idx

---

# PART E: CRITICAL CALCULATION RULES

## TMU Calculation Precision
- **Internal**: Python Decimal with precision up to 0.001 (3 decimal places)
- **Storage**: Float64 in DB (stored value is already rounded)
- **Seconds**: Decimal × 0.036, rounded to 0.0001 (4 decimal places)
- **Formula**: effective_tmu = base_tmu × frequency, quantized to ROUND_HALF_UP

## Row-Level Calculation (calculate_row)
```
base_tmu = sum(slot_tmu for each slot)  [quantized to 0.001]
effective_tmu = base_tmu × frequency    [quantized to 0.001]
effective_seconds = effective_tmu × 0.036 [quantized to 0.0001]

If is_simo == True:
  total_contribution_tmu = 0.0
  total_contribution_seconds = 0.0
Else:
  total_contribution_tmu = effective_tmu
  total_contribution_seconds = effective_seconds
```

## Analysis Total Calculation (calculate_analysis_total)
```
total_tmu = sum(row.total_contribution_tmu for each row where not row.is_simo)
total_tmu = total_tmu.quantize(ROUND_TMU)
total_seconds = total_tmu × 0.036  [quantized to ROUND_SECONDS]
simo_count = count(rows where is_simo == True)
row_count = total number of rows
```

---

This comprehensive specification is now ready for AI-driven implementation. All endpoints, data structures, validation rules, and calculation algorithms are fully defined and executable.