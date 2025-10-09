# 摘要列表 API 文檔

## 新增 API: `/api/summaries/list`

### 基本資訊

- **路徑**: `/api/summaries/list`
- **方法**: `POST`
- **認證**: 需要通行碼（使用 `@require_access_code` 裝飾器）
- **內容類型**: `application/json`

### 功能描述

獲取摘要列表，支援分頁、頻道篩選、關鍵字搜尋和書籤篩選。

### 請求參數

```json
{
  "access_code": "your_access_code",  // 必填：通行碼
  "page": 1,                          // 可選：頁碼（從1開始，預設1）
  "per_page": 30,                     // 可選：每頁數量（1-100，預設30）
  "channel": "HowFun",                // 可選：頻道篩選（支援原始名稱或顯示名稱）
  "search": "關鍵字",                  // 可選：搜尋標題中的關鍵字
  "bookmarked_only": false            // 可選：只顯示已加書籤的摘要（預設false）
}
```

### 參數說明

| 參數 | 類型 | 必填 | 說明 | 預設值 | 限制 |
|------|------|------|------|--------|------|
| `access_code` | string | 是 | 通行碼 | - | - |
| `page` | integer | 否 | 頁碼 | 1 | ≥ 1 |
| `per_page` | integer | 否 | 每頁數量 | 30 | 1-100 |
| `channel` | string | 否 | 頻道名稱 | null | - |
| `search` | string | 否 | 搜尋關鍵字 | null | - |
| `bookmarked_only` | boolean | 否 | 只顯示書籤 | false | - |

### 成功回應

**狀態碼**: `200 OK`

```json
{
  "success": true,
  "data": {
    "summaries": [
      {
        "filename": "2025.06.22 - HowFun-時間管理大師.txt",
        "title": "時間管理大師！三天兩夜快閃東京",
        "channel": "HowFun",
        "channel_display": "HowFun",
        "created_at": "2025-06-22 10:30:00",
        "file_size": 5200,
        "is_bookmarked": false
      }
      // ... 更多摘要
    ],
    "pagination": {
      "page": 1,
      "per_page": 30,
      "total_count": 771,
      "total_pages": 26,
      "has_next": true,
      "has_prev": false
    },
    "channels": [
      {
        "name": "HowFun",
        "display_name": "HowFun",
        "count": 45
      }
      // ... 更多頻道
    ]
  },
  "message": null
}
```

### 錯誤回應

#### 1. 通行碼錯誤

**狀態碼**: `401 Unauthorized`

```json
{
  "success": false,
  "error": "auth_error",
  "message": "通行碼錯誤"
}
```

#### 2. 參數驗證錯誤

**狀態碼**: `400 Bad Request`

```json
{
  "success": false,
  "error": "validation_error",
  "message": "page 必須是大於 0 的整數"
}
```

或

```json
{
  "success": false,
  "error": "validation_error",
  "message": "per_page 必須是 1-100 之間的整數"
}
```

#### 3. 伺服器錯誤

**狀態碼**: `500 Internal Server Error`

```json
{
  "success": false,
  "error": "internal_error",
  "message": "獲取摘要列表失敗: [錯誤詳情]"
}
```

### 使用範例

#### 範例 1: 獲取第一頁

```bash
curl -X POST http://localhost:5000/api/summaries/list \
  -H "Content-Type: application/json" \
  -d '{
    "access_code": "your_code",
    "page": 1,
    "per_page": 20
  }'
```

#### 範例 2: 搜尋包含「AI」的摘要

```bash
curl -X POST http://localhost:5000/api/summaries/list \
  -H "Content-Type: application/json" \
  -d '{
    "access_code": "your_code",
    "page": 1,
    "per_page": 20,
    "search": "AI"
  }'
```

#### 範例 3: 篩選特定頻道

```bash
curl -X POST http://localhost:5000/api/summaries/list \
  -H "Content-Type: application/json" \
  -d '{
    "access_code": "your_code",
    "page": 1,
    "per_page": 20,
    "channel": "HowFun"
  }'
```

#### 範例 4: 只顯示書籤

```bash
curl -X POST http://localhost:5000/api/summaries/list \
  -H "Content-Type: application/json" \
  -d '{
    "access_code": "your_code",
    "page": 1,
    "per_page": 20,
    "bookmarked_only": true
  }'
```

#### 範例 5: 組合篩選（搜尋 + 頻道 + 書籤）

```bash
curl -X POST http://localhost:5000/api/summaries/list \
  -H "Content-Type: application/json" \
  -d '{
    "access_code": "your_code",
    "page": 1,
    "per_page": 20,
    "channel": "HowFun",
    "search": "東京",
    "bookmarked_only": true
  }'
```

### Swift 範例（iOS App）

```swift
struct SummaryListRequest: Codable {
    let access_code: String
    let page: Int
    let per_page: Int
    let channel: String?
    let search: String?
    let bookmarked_only: Bool?
}

struct Summary: Codable {
    let filename: String
    let title: String
    let channel: String
    let channel_display: String
    let created_at: String
    let file_size: Int
    let is_bookmarked: Bool
}

struct Pagination: Codable {
    let page: Int
    let per_page: Int
    let total_count: Int
    let total_pages: Int
    let has_next: Bool
    let has_prev: Bool
}

struct Channel: Codable {
    let name: String
    let display_name: String
    let count: Int
}

struct SummaryListData: Codable {
    let summaries: [Summary]
    let pagination: Pagination
    let channels: [Channel]
}

struct SummaryListResponse: Codable {
    let success: Bool
    let data: SummaryListData?
    let message: String?
}

// 使用範例
func fetchSummaries(page: Int = 1, perPage: Int = 30) async throws -> SummaryListResponse {
    let url = URL(string: "http://your-server/api/summaries/list")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

    let body = SummaryListRequest(
        access_code: "your_code",
        page: page,
        per_page: perPage,
        channel: nil,
        search: nil,
        bookmarked_only: nil
    )

    request.httpBody = try JSONEncoder().encode(body)

    let (data, _) = try await URLSession.shared.data(for: request)
    return try JSONDecoder().decode(SummaryListResponse.self, from: data)
}
```

### 效能特性

- **總摘要數**: 771 個
- **首頁載入時間**: ~250ms（載入 30 筆）
- **記憶體佔用**: 極小（只載入當前頁）
- **網路流量**: 每頁約 15-30 KB

### 篩選邏輯

1. **書籤篩選**: 優先執行，減少後續處理量
2. **頻道篩選**: 支援原始名稱和顯示名稱
3. **關鍵字搜尋**: 不區分大小寫，搜尋標題欄位
4. **分頁**: 在所有篩選後執行

### 排序

- 預設按**修改時間降序**（最新的在最前面）

### 注意事項

1. `channel` 參數同時支援原始頻道名稱和顯示名稱
2. `search` 是不區分大小寫的模糊搜尋
3. 頻道列表 `channels` 會返回所有頻道的統計（不受篩選影響）
4. `per_page` 最大值為 100，超過會返回驗證錯誤
5. 如果請求的頁碼超過總頁數，會自動返回最後一頁

### 相關檔案

- **API Route**: `src/routes/api.py:881`
- **服務層**: `src/services/summary_api_service.py:228`
- **認證裝飾器**: `src/utils/auth_decorator.py:15`
