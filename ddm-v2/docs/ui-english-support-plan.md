# English Language Support UI Workflow Plan

## 📋 Current State Analysis

### ✅ What Works Now
1. **Backend Infrastructure**: Complete language detection and routing
2. **API Endpoint**: `/api/v2/worksheets/nl-draft` supports all languages
3. **Frontend Types**: Now includes `language` field in `AiParseBlock`
4. **Fallback Mechanism**: Rule-based fallback works for English input

### 🔄 What Needs Enhancement

## 📱 UI Workflow Enhancements

### 1. Language Indicator in AI Draft Panel
**Location**: `AiDraftPanel.tsx`
**Enhancement**: Add language detection indicator
```tsx
// Show detected language with appropriate flag/icon
{ai?.plan?.language && (
  <div className="flex items-center gap-2 text-sm text-slate-600">
    <LanguageIcon language={ai.plan.language} />
    <span>{t(`language.${ai.plan.language}`)}</span>
  </div>
)}
```

### 2. Multi-language Action Display
**Location**: `ActionCard.tsx` 
**Enhancement**: Support English action descriptions
```tsx
// Display action roles in original language
{action.roles.object && (
  <div className="text-sm">
    <span className="text-slate-500">{t('roles.object')}:</span>
    <span className="ml-1 font-medium">{action.roles.object.text}</span>
  </div>
)}
```

### 3. Input Language Detection Preview
**Location**: AI text input area
**Enhancement**: Real-time language detection feedback
```tsx
// Show detected language as user types
const detectedLang = detectLanguageClient(inputText)
<div className="text-xs text-slate-500">
  {t('parsing.detectedLanguage')}: {t(`language.${detectedLang}`)}
</div>
```

### 4. Bilingual Narrative Display 
**Location**: Cycle display/preview
**Enhancement**: Show both Chinese and English narratives
```tsx
// Display both narratives when available
<div className="space-y-1">
  {narrative_zh && <div className="text-sm">{narrative_zh}</div>}
  {narrative_en && <div className="text-sm text-slate-600">{narrative_en}</div>}
</div>
```

### 5. Language-Aware Error Messages
**Enhancement**: Context-appropriate error handling
```tsx
// Show errors in appropriate language context
const getErrorMessage = (error: string, language: string) => {
  const key = `errors.${error}`
  return language === 'en' ? t(`${key}.en`) : t(`${key}.zh`)
}
```

## 🎨 Visual Design Improvements

### Language Indicators
- **Chinese**: 🇹🇼 or "中" badge
- **English**: 🇺🇸 or "EN" badge  
- **Mixed**: 🌐 or "MIX" badge

### Color Coding
- **Chinese text**: Default black
- **English text**: Slightly muted (text-slate-700)
- **Mixed content**: Alternating or highlighted segments

### Status Indicators
- **Parsing success**: Green checkmark with language
- **Fallback mode**: Yellow warning with "Rule-based" label
- **Multi-language**: Special badge for mixed content

## 📱 Complete User Flow

### Scenario: English Work Instruction Input

1. **Input Phase**:
   ```
   User types: "Pick up the electric screwdriver"
   → Real-time detection shows: "🇺🇸 English detected"
   ```

2. **Processing Phase**:
   ```
   User clicks "Parse" 
   → Loading with "Processing English input..."
   → Fallback notice: "⚠️ Using rule-based parsing (LLM offline)"
   ```

3. **Results Phase**:
   ```
   Action Card shows:
   ┌─────────────────────────────────┐
   │ 🇺🇸 Action 1: move_place        │
   │ Object: electric screwdriver    │
   │ Sequence: GM                    │
   │ Status: ✅ Ready to adopt       │
   │ [Adopt] [Details]               │
   └─────────────────────────────────┘
   ```

4. **Adoption Phase**:
   ```
   User clicks "Adopt"
   → Cycle created with bilingual narratives:
     中文: "拿取電動螺絲起子"
     English: "Pick up the electric screwdriver"
   ```

## 🛠 Implementation Priority

### Phase 1 (Immediate)
1. ✅ Update TypeScript types (DONE)
2. 🔄 Add language indicator to AI results
3. 🔄 Display original text language in ActionCard

### Phase 2 (Next Sprint)
1. 🔄 Real-time language detection in input
2. 🔄 Bilingual narrative display
3. 🔄 Language-aware error messages

### Phase 3 (Future Enhancement)
1. 🔄 Advanced mixed-language handling
2. 🔄 Language preference settings
3. 🔄 Translation suggestions

## 🧪 Testing Scenarios

### Core Test Cases
1. **Pure English**: "Install the memory module"
2. **Pure Chinese**: "安裝記憶體模組" 
3. **Mixed**: "Install the 記憶體 module"
4. **Technical Terms**: "Connect USB cable"
5. **Fallback Mode**: All above without LLM API

### Expected Behaviors
- ✅ Language detection accuracy > 95%
- ✅ Fallback graceful degradation
- ✅ UI shows appropriate language indicators
- ✅ Bilingual narratives generated correctly
- ✅ No UI crashes on mixed content

This plan ensures seamless English language support while maintaining all existing Chinese functionality.