# Fear & Greed Sentiment 기능 구현 계획

작성일: 2026-05-07

## 1. 배경

현재 `Forecast` 탭은 가격 시계열, Prophet 예측값, 예측 구간, 이상값, 이벤트를 하나의 가격 축에서 보여준다. 여기에 주식시장 전체 심리를 나타내는 CNN Fear & Greed Index를 같은 시간축으로 함께 표시하면, 개별 종목의 급등락이나 이상값 후보가 시장 전반의 공포/탐욕 국면과 어떤 관계를 갖는지 더 쉽게 볼 수 있다.

이 프로젝트는 암호화폐를 대상으로 하지 않으므로 Alternative.me, CoinMarketCap 같은 Crypto Fear & Greed Index는 기본 대상에서 제외한다. 기본 데이터 소스는 주식시장용 CNN Fear & Greed Index로 검토한다.

## 2. 목표

- CNN Fear & Greed Index 데이터를 자동으로 가져올 수 있는지 먼저 검증한다.
- 검증된 데이터를 SQLite에 캐싱한다.
- 자동 동기화가 실패하거나 과거 데이터가 부족할 때 수동 입력과 CSV 업로드로 보완할 수 있게 한다.
- `Forecast` 탭에 가격 차트와 같은 x축을 공유하는 Sentiment 서브차트를 추가한다.
- Sentiment 섹션에서 Fear & Greed 데이터의 sync 상태, 수동 입력, CSV import, 저장 데이터 조회를 관리한다.

## 3. 비목표

- Fear & Greed Index를 매수/매도 신호로 직접 해석하지 않는다.
- Prophet 가격 예측 모델에 Fear & Greed를 regressor로 반영하는 것은 이번 범위에서 제외한다.
- Crypto Fear & Greed Index 연동은 이번 범위에서 제외한다.
- CNN 공식 계산식을 자체 재구현하지 않는다.

## 4. 데이터 소스 검토

### 4.1 1차 후보: `fear-greed` Python 패키지

`fear-greed` 패키지는 CNN 페이지가 사용하는 내부 데이터 API를 통해 현재 점수, 7개 구성 지표, 약 1년치 일별 히스토리를 가져온다고 설명한다. 공식 CNN 개발자 API는 아니므로 내부 API 변경에 취약할 수 있다.

검증 항목:

- 패키지 설치 가능 여부
- `import fear_greed` 성공 여부
- 현재 점수 조회 성공 여부
- `get_history(last="1y")` 또는 동등 기능으로 일별 히스토리 조회 가능 여부
- 반환 필드 확인: 날짜, 점수, 등급
- 반환 기간 확인: 실제로 약 1년치 미국 거래일 데이터를 제공하는지
- 네트워크 오류, 응답 포맷 변경, 빈 응답 발생 시 예외 형태 확인
- Streamlit 앱 실행 환경에서 의존성 충돌이 없는지 확인

검증 결과가 양호하면 이 패키지를 초기 자동 sync provider로 사용한다.

검증 결과:

- `fear-greed==0.1.0` 설치와 import가 성공했다.
- `get_score()` 호출은 성공했으며 CNN 내부 엔드포인트 `production.dataviz.cnn.io`를 사용한다.
- `get_history(last="1y")`는 패키지에서 지원하지 않는다.
- `get_history(last="365")`는 성공했고, 2026-05-07 기준 253개 포인트를 반환했다.
- 반환 객체는 dict가 아니라 `HistoricalPoint(date, score, rating)` 형태이므로 provider 정규화 계층에서 attribute 접근을 지원해야 한다.
- 같은 날짜 포인트가 중복될 수 있어 SQLite upsert 과정에서 날짜 기준으로 합쳐진다. 임시 DB end-to-end 검증에서는 253개 fetch, 252개 저장을 확인했다.

### 4.2 장기 과거 데이터

Yahoo Finance처럼 CNN Fear & Greed Index의 수년치 데이터를 공식 문서화된 API로 한 번에 가져오는 방법은 현재 확인되지 않았다. 따라서 장기 과거 데이터는 다음 순서로 접근한다.

- 자동 sync는 패키지가 안정적으로 제공하는 범위부터 지원한다.
- 1년 이전 데이터는 CSV import로 seed할 수 있게 한다.
- 추후 신뢰 가능한 공개 데이터셋이나 사용 허가가 명확한 소스가 확인되면 별도 provider로 추가한다.

## 5. SQLite 스키마 계획

새 테이블 `fear_greed_index`를 추가한다.

```sql
CREATE TABLE IF NOT EXISTS fear_greed_index (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  index_date TEXT NOT NULL,
  value REAL NOT NULL,
  classification TEXT,
  raw_timestamp INTEGER,
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (source, index_date)
);
```

인덱스:

```sql
CREATE INDEX IF NOT EXISTS idx_fear_greed_index_date
ON fear_greed_index (index_date);
```

마이그레이션:

- `ticker_scope/data/database.py`의 `CURRENT_SCHEMA_VERSION`을 5로 올린다.
- migration v5 `fear_greed_index_storage`를 추가한다.

저장 정책:

- `source="cnn_api"`: 자동 sync 데이터
- `source="manual"`: 단건 수동 입력
- `source="csv_import"`: CSV 업로드 데이터
- 같은 날짜에 여러 source가 있으면 조회 시 우선순위를 적용한다.
- 우선순위는 `manual > csv_import > cnn_api`로 둔다.

## 6. Repository API 계획

`ticker_scope/data/repositories.py`에 다음 함수를 추가한다.

- `upsert_fear_greed_index(connection, data, source) -> int`
- `get_fear_greed_history(connection, start_date=None, end_date=None, preferred_sources=None) -> pd.DataFrame`
- `delete_fear_greed_value(connection, value_id) -> bool`
- `get_fear_greed_coverage(connection) -> dict`

`get_fear_greed_history`는 날짜별 대표 row를 반환한다. 같은 날짜에 여러 source가 있을 경우 수동 입력을 우선한다.

반환 컬럼:

- `id`
- `index_date`
- `value`
- `classification`
- `source`
- `notes`
- `created_at`
- `updated_at`

## 7. 자동 Sync 계획

새 패키지 영역을 추가한다.

```text
ticker_scope/sentiment/
  __init__.py
  providers.py
  sync.py
```

`providers.py`:

- `FearGreedRecord` dataclass
- `FearGreedClient` protocol 또는 기본 client
- `CnnFearGreedClient`
- 패키지 import 실패 시 명확한 오류 메시지 제공

`sync.py`:

- `SentimentSyncResult` dataclass
- `sync_fear_greed_index(force_refresh=False, min_refresh_hours=12) -> SentimentSyncResult`
- `sync_runs`에 source `cnn_fear_greed`로 성공/실패/skip 이력 기록

동기화 정책:

- 최근 성공 sync가 `min_refresh_hours` 안에 있으면 API 호출을 skip한다.
- `force_refresh=True`면 즉시 재조회한다.
- 자동 sync가 실패해도 저장된 SQLite 데이터는 유지한다.
- 실패 시 Forecast 화면 전체가 깨지지 않게 한다.

## 8. 수동 입력 및 CSV Import 계획

Sentiment 섹션에 다음 기능을 추가한다.

단건 입력:

- 날짜 입력
- 점수 입력: 0~100 숫자 입력 또는 slider
- classification 자동 계산
- notes 선택 입력
- 저장 시 `source="manual"`로 upsert

CSV import:

- 필수 컬럼: `date`, `value`
- 선택 컬럼: `classification`, `notes`
- 날짜 파싱 실패 row, 0~100 범위 밖 점수 row는 저장하지 않고 오류 요약 표시
- 저장 시 `source="csv_import"`로 upsert

CSV 예시:

```csv
date,value,classification,notes
2025-01-02,32,Fear,manual seed
2025-01-03,41,Fear,manual seed
2025-01-06,52,Neutral,manual seed
```

분류 기준:

- `0 <= value <= 24`: `Extreme Fear`
- `25 <= value <= 44`: `Fear`
- `45 <= value <= 55`: `Neutral`
- `56 <= value <= 75`: `Greed`
- `76 <= value <= 100`: `Extreme Greed`

이 기준은 표시용 기본값이며, CNN의 현재 표기와 차이가 확인되면 조정한다.

## 9. UI 계획

### 9.1 Forecast 탭

`make_forecast_chart`를 확장해 Fear & Greed 서브차트를 추가한다.

권장 표시:

- 위쪽: 기존 가격 Forecast 차트
- 아래쪽: Fear & Greed Index 라인 차트
- x축 공유
- F&G y축은 0~100 고정
- 배경 구간:
  - 0~24: Extreme Fear
  - 25~44: Fear
  - 45~55: Neutral
  - 56~75: Greed
  - 76~100: Extreme Greed
- 미래 예측 기간에는 F&G 데이터가 없으면 선을 이어 그리지 않는다.

데이터가 없을 때:

- 기존 Forecast 차트는 그대로 표시한다.
- 차트 아래 또는 Sentiment 섹션에 "Fear & Greed data is not available yet." 수준의 안내를 표시한다.

### 9.2 Sentiment 섹션

현재 `Single ticker` 탭 목록에 `Sentiment` 탭을 추가하는 방식을 우선 검토한다.

예상 탭 구성:

```text
Forecast | Anomalies | Backtest | Events | Sentiment | Data
```

Sentiment 탭 구성:

- 최근 Fear & Greed 값 metric
- 저장 데이터 범위와 row 수
- 마지막 sync 상태
- `Sync CNN Fear & Greed` 버튼
- `Force API refresh` 체크박스
- 단건 수동 입력 form
- CSV 업로드 form
- 저장된 데이터 테이블

## 10. 테스트 계획

### 10.1 Provider 검증 테스트

네트워크를 사용하는 통합 검증은 수동 또는 별도 스크립트로 먼저 수행한다.

검증 스크립트 후보:

```bash
python -m scripts.verify_fear_greed_provider
```

확인 내용:

- 패키지 import
- 현재 점수 조회
- 1년 히스토리 조회
- 날짜/점수/등급 정규화

### 10.2 Unit Test

추가 테스트:

- `tests/test_sentiment_sync.py`
- `tests/test_sentiment_repositories.py`
- `tests/test_charts.py` 확장

검증 항목:

- F&G 데이터 upsert
- 같은 날짜 중복 처리
- source 우선순위
- CSV normalization
- sync skip 정책
- provider 실패 시 `sync_runs` failed 기록
- F&G 데이터가 있는 차트에서 서브차트 trace가 추가되는지
- F&G 데이터가 없어도 Forecast 차트가 기존처럼 렌더링되는지

## 11. 구현 순서

1. `fear-greed` 패키지 검증 스파이크를 수행한다.
2. 검증 결과에 따라 의존성을 `requirements.txt`에 추가할지 결정한다.
3. SQLite migration v5와 repository API를 추가한다.
4. provider와 sync 함수를 추가한다.
5. repository/sync unit test를 작성한다.
6. Forecast 차트에 Sentiment 서브차트를 추가한다.
7. Sentiment 탭과 수동 입력/CSV import UI를 추가한다.
8. chart/UI 테스트를 보강한다.
9. Streamlit에서 실제 `Single ticker` 화면을 확인한다.
10. README에 Sentiment 섹션 설명을 추가한다.

## 12. 리스크와 대응

| 리스크 | 대응 |
| --- | --- |
| CNN 내부 API 변경 | sync 실패를 허용하고 SQLite 캐시와 수동 입력으로 fallback |
| 1년 이상 히스토리 부족 | CSV import로 장기 데이터 seed 지원 |
| 수동 입력과 API 데이터 충돌 | source 우선순위 `manual > csv_import > cnn_api` 적용 |
| Forecast 화면 복잡도 증가 | 가격 차트와 F&G 서브차트를 분리하고 x축만 공유 |
| 패키지 의존성 품질 미확인 | 구현 전 검증 스파이크와 최소 wrapper 계층 도입 |

## 13. 완료 기준

- CNN Fear & Greed 자동 sync가 성공/실패/skip 이력을 SQLite에 기록한다.
- F&G 값이 SQLite에 저장되고 기간 조건으로 조회된다.
- Forecast 탭에서 같은 시간축의 Sentiment 서브차트를 볼 수 있다.
- Sentiment 탭에서 수동 입력과 CSV import가 가능하다.
- 자동 sync 실패 상황에서도 앱 주요 화면이 정상 동작한다.
- 관련 unit test가 통과한다.
