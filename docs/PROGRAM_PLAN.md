# Ticker Scope 프로그램 기획서

작성일: 2026-05-01

## 1. 개요

`ticker-scope`는 Meta Prophet을 활용해 주식 시계열 데이터를 분석하는 개인 학습용 프로젝트이다. 첫 번째 대상은 Tesla(`TSLA`)의 최근 5년 일별 종가 데이터이며, Prophet의 예측 구간과 실제값의 차이를 통해 예측 흐름, 이상값 후보, 백테스트 성능을 시각적으로 확인하는 것을 목표로 한다.

이 프로젝트는 투자 판단 자동화가 목적이 아니다. 회사 서비스의 일별 재생수 같은 비즈니스 시계열에 Prophet을 적용하기 전, 주식 데이터를 실험 대상으로 삼아 Prophet의 장단점과 모델링 흐름을 익히는 탐색용 도구이다.

## 2. 목표

- `TSLA`의 최근 5년 일별 가격 데이터를 가져와 Prophet 입력 형식으로 변환한다.
- Prophet으로 미래 가격 흐름과 예측 구간을 생성한다.
- 실제 종가가 예측 구간을 벗어나는 지점을 이상값 후보로 표시한다.
- 과거 구간 백테스트를 통해 예측 오차를 정량화한다.
- Streamlit UI에서 종목, 기간, 예측 기간, 모델 옵션을 조정할 수 있게 한다.
- 초기에는 Tesla 중심으로 만들고, 이후 여러 종목 비교와 이벤트 반영 기능으로 확장한다.

## 3. 비목표

- 실거래, 자동 매매, 매수/매도 신호 제공은 범위에서 제외한다.
- 주가를 정확히 맞히는 모델을 만드는 것이 아니라, Prophet 기반 시계열 분석 패턴을 익히는 데 초점을 둔다.
- 회사 서비스 데이터와 직접 연결하는 기능은 초기 버전에서 제외한다.

## 4. 주요 개념

### 4.1 원 종가와 조정 종가

원 종가(`Close`)는 해당 거래일 장 마감 시점에 실제로 기록된 마지막 거래 가격이다. 뉴스나 차트에서 흔히 보는 "그날의 종가"가 여기에 해당한다.

조정 종가(`Adjusted Close`)는 액면분할, 병합, 배당 등 기업 이벤트가 과거 가격 비교에 미치는 영향을 보정한 값이다. 예를 들어 1주가 5주로 쪼개지는 액면분할이 발생하면, 이벤트 전후의 원 종가만 보면 가격이 갑자기 크게 떨어진 것처럼 보인다. 하지만 실제 기업 가치가 하루아침에 5분의 1이 된 것은 아니므로, 과거 가격을 같은 기준으로 비교하기 위해 조정 종가를 사용한다.

Prophet 같은 시계열 모델에는 조정 종가 기준이 더 적합하다. 기업 이벤트로 인한 기계적인 가격 변화가 이상값이나 추세 변화로 잘못 해석될 수 있기 때문이다. `yfinance`에서는 `auto_adjust=True` 옵션을 사용해 이런 보정이 반영된 가격 데이터를 우선 사용한다.

### 4.2 예측과 이상값 탐지

Prophet은 특정 날짜의 예측값 `yhat`과 함께 예측 구간 `yhat_lower`, `yhat_upper`를 제공한다. 이 프로젝트에서는 실제값 `y`가 예측 구간 밖에 위치하는 경우를 이상값 후보로 본다.

초기 이상값 기준:

- `y < yhat_lower`: 예상보다 낮은 이상값 후보
- `y > yhat_upper`: 예상보다 높은 이상값 후보
- `abs(y - yhat)` 또는 오차율을 함께 표시해 이상 정도를 비교한다.

이 기준은 통계적 신호일 뿐 원인 분석을 대체하지 않는다. 실적 발표, 금리 발표, 리콜, CEO 발언, 액면분할, 시장 전체 급락 같은 외부 이벤트를 함께 확인해야 한다.

### 4.3 이벤트와 캘린더

Prophet은 휴일이나 특별 이벤트를 별도 데이터프레임으로 전달해 모델에 반영할 수 있다. 이벤트 데이터는 기본적으로 `holiday`, `ds` 컬럼을 가지며, 필요하면 이벤트 전후 영향을 나타내는 `lower_window`, `upper_window`를 추가한다.

주식 실험에서는 다음 이벤트를 후보로 둔다.

- 실적 발표일
- FOMC, CPI 등 시장 전체 이벤트
- 액면분할, 배당락일
- 제품 발표, 리콜, 대규모 계약 발표
- 회사 내부 서비스 적용 시에는 캠페인, 업데이트, 장애, 휴일, 주말 패턴

초기 버전에서는 수동 이벤트 등록 기능을 먼저 만들고, 이후 Financial Modeling Prep 같은 외부 API의 실적 캘린더 연동을 검토한다.

## 5. 데이터 정책

### 5.1 초기 데이터 소스

초기 데이터 수집은 `yfinance`를 사용한다. `yfinance`는 Yahoo Finance 데이터를 Python에서 쉽게 조회할 수 있게 해주는 오픈소스 라이브러리이며, 단일 종목과 다중 종목 다운로드를 지원한다.

초기 수집 조건:

- 대상 종목: `TSLA`
- 기간: 최근 5년
- 단위: 1일
- 기준값: 조정 종가
- Prophet 입력 컬럼: `ds`, `y`

예상 데이터 컬럼:

- `Date`
- `Open`
- `High`
- `Low`
- `Close`
- `Volume`

Prophet 학습에는 `Date`와 조정된 `Close`를 사용한다.

### 5.2 로컬 저장소 정책

주식 데이터를 필요할 때마다 `yfinance`에서 다시 가져오는 방식은 비효율적이고 재현성도 낮다. 같은 종목/기간을 반복 분석할 때 네트워크 호출이 늘어나고, 외부 API 장애나 응답 지연이 Streamlit 사용 경험에 직접 영향을 준다. 따라서 프로젝트의 기본 저장소는 파일 기반 RDB인 SQLite로 결정한다.

초기 저장소 결정:

- 기본 DB: SQLite
- DB 파일 위치: `data/ticker_scope.sqlite3`
- CSV/Parquet: 원천 저장소가 아니라 내보내기, 수동 확인, 분석 스냅샷 용도로만 사용
- Streamlit 캐시: 화면 반응성을 위한 단기 메모리 캐시로만 사용하고, 원천 캐시 역할은 SQLite가 맡음

SQLite를 선택하는 이유:

- 별도 서버 설치 없이 로컬 파일 하나로 동작한다.
- 주가 데이터, 종목 메타데이터, 이벤트, API 동기화 이력을 함께 관리할 수 있다.
- 이벤트 데이터처럼 수정/삭제/분류가 필요한 정보를 CSV보다 안정적으로 다룰 수 있다.
- 종목과 날짜 기준의 중복 방지, upsert, 조회 조건 처리에 적합하다.
- 이후 PostgreSQL 같은 서버형 RDB로 옮기기 쉬운 스키마 설계를 연습할 수 있다.

CSV만 사용하는 방식은 초기 실험에는 간단하지만, 이벤트 관리와 증분 업데이트가 들어가면 관리 비용이 빠르게 늘어난다. 특히 수동 이벤트, API 이벤트, 종목별 가격 데이터, 백테스트 결과를 함께 다루려면 관계형 구조가 더 자연스럽다.

### 5.3 저장 대상 데이터

초기 DB에는 다음 데이터를 저장한다.

| 데이터 | 설명 | 저장 이유 |
| --- | --- | --- |
| 종목 | ticker, 이름, 거래소, 통화, 활성 여부 | UI 선택과 데이터 관리 기준 |
| 일별 가격 | ticker, 날짜, open, high, low, close, volume, adjusted 여부 | Prophet 학습 원천 데이터 |
| 이벤트 | 이벤트명, 날짜, 카테고리, ticker, 영향 범위 | Prophet holidays 및 원인 분석 |
| 동기화 이력 | 데이터 소스, ticker, 기간, 성공 여부, 실행 시각 | API 호출 추적과 장애 확인 |
| 백테스트 결과 | 모델 설정, 기간, 지표, 실행 시각 | 실험 결과 비교 |

현재 구현에서는 종목, 일별 가격, 이벤트, 동기화 이력에 더해 백테스트 실행 이력과 지표를 SQLite에 저장한다. 백테스트는 개별 예측 row 전체가 아니라 실행 설정과 성능 지표를 우선 저장해, 종목별/설정별 비교에 필요한 정보를 가볍게 유지한다.

### 5.4 가격 데이터 동기화 전략

가격 데이터는 전체 재다운로드보다 증분 업데이트를 기본으로 한다.

초기 로딩:

- DB에 해당 종목 데이터가 없으면 `yfinance`에서 요청 기간 전체를 다운로드한다.
- 다운로드 결과를 날짜 기준으로 upsert한다.
- Prophet 학습은 DB에 저장된 데이터를 다시 조회해 수행한다.

이후 로딩:

- DB에서 해당 종목의 마지막 거래일을 확인한다.
- 마지막 거래일 이후 데이터만 `yfinance`에서 요청한다.
- 새 데이터가 있으면 upsert하고, 없으면 DB 데이터만 사용한다.
- 사용자가 강제 새로고침을 누르면 지정 기간을 다시 다운로드해 upsert한다.

데이터 정합성:

- `(ticker, date, interval, adjusted)` 조합에 unique 제약을 둔다.
- 기본 interval은 `1d`로 시작한다.
- 기본 adjusted 값은 `true`로 시작한다.
- 원 종가와 조정 종가를 함께 관리할 필요가 생기면 `adjusted=false` 데이터를 별도로 저장한다.

저장소 안정화 정책:

- SQLite는 `WAL` 모드와 `busy_timeout`을 사용해 Streamlit 재실행 중 DB 잠금 가능성을 줄인다.
- `schema_migrations` 테이블과 SQLite `user_version`으로 스키마 버전을 기록한다.
- 가격 데이터 저장 전 `Date`, `Close` 필수 컬럼과 양수 종가, 음수 거래량 여부를 검증한다.
- 동일 날짜 데이터가 중복으로 들어오면 마지막 값을 기준으로 정규화한 뒤 upsert한다.
- 저장된 가격 범위, row 수, 최신성, 긴 예상일 누락 구간을 UI에서 확인할 수 있게 한다.
- 주식 데이터는 미국장 거래 캘린더 기준으로 주말과 NYSE 휴장일을 제외한다.
- 중간에 5거래일 이상 연속으로 비어 있는 가격 구간은 다음 sync 때 보강 대상으로 본다.
- `sync_runs`는 성공/실패와 메시지를 계속 기록해 API 호출 이력과 장애 원인을 추적한다.

### 5.5 이벤트 저장 전략

이벤트는 주식 분석과 회사 서비스 데이터 분석 모두에서 중요하므로 DB에 정규화해 저장한다.

이벤트 필드:

- `name`: 이벤트명
- `event_date`: 이벤트 기준일
- `category`: `earnings`, `macro`, `split`, `dividend`, `product`, `manual`, `service` 등
- `ticker`: 특정 종목 이벤트일 경우 종목 코드
- `lower_window`, `upper_window`: Prophet에 전달할 이벤트 영향 범위
- `source`: `manual`, `csv`, `financial_modeling_prep`, `finnhub` 등
- `notes`: 사용자가 입력한 설명

초기에는 수동 이벤트 등록과 CSV 업로드를 우선 지원한다. 외부 API 연동은 이벤트 구조가 안정된 뒤 추가한다.

### 5.6 DB 스키마 초안

```sql
CREATE TABLE symbols (
  ticker TEXT PRIMARY KEY,
  name TEXT,
  exchange TEXT,
  currency TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE daily_prices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker TEXT NOT NULL,
  price_date TEXT NOT NULL,
  interval TEXT NOT NULL DEFAULT '1d',
  open REAL,
  high REAL,
  low REAL,
  close REAL NOT NULL,
  volume INTEGER,
  adjusted INTEGER NOT NULL DEFAULT 1,
  source TEXT NOT NULL DEFAULT 'yfinance',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (ticker, price_date, interval, adjusted),
  FOREIGN KEY (ticker) REFERENCES symbols(ticker)
);

CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  event_date TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'manual',
  ticker TEXT,
  lower_window INTEGER NOT NULL DEFAULT 0,
  upper_window INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT 'manual',
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (ticker) REFERENCES symbols(ticker)
);

CREATE TABLE sync_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  ticker TEXT,
  period TEXT,
  interval TEXT,
  status TEXT NOT NULL,
  row_count INTEGER NOT NULL DEFAULT 0,
  message TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL
);

CREATE TABLE backtest_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker TEXT NOT NULL,
  strategy TEXT NOT NULL,
  period TEXT,
  interval TEXT NOT NULL DEFAULT '1d',
  adjusted INTEGER NOT NULL DEFAULT 1,
  train_ratio REAL,
  horizons TEXT,
  rolling_windows INTEGER,
  min_train_rows INTEGER,
  interval_width REAL NOT NULL,
  use_events INTEGER NOT NULL DEFAULT 0,
  event_count INTEGER NOT NULL DEFAULT 0,
  date_policy TEXT NOT NULL DEFAULT 'us_stock_market',
  row_count INTEGER NOT NULL DEFAULT 0,
  data_start_date TEXT,
  data_end_date TEXT,
  status TEXT NOT NULL,
  message TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (ticker) REFERENCES symbols(ticker)
);

CREATE TABLE backtest_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  horizon_days INTEGER,
  cutoff_date TEXT,
  train_start_date TEXT,
  train_end_date TEXT,
  test_start_date TEXT,
  test_end_date TEXT,
  test_rows INTEGER NOT NULL DEFAULT 0,
  mae REAL,
  rmse REAL,
  mape REAL,
  coverage REAL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (run_id) REFERENCES backtest_runs(id) ON DELETE CASCADE
);
```

SQLite 접근 방식은 초기에는 Python 표준 라이브러리 `sqlite3`와 `pandas.read_sql_query`를 사용한다. ORM은 아직 도입하지 않는다. 테이블 수가 늘거나 마이그레이션 관리가 필요해지는 시점에 SQLAlchemy와 Alembic 도입을 검토한다.

### 5.7 데이터 사용 주의사항

`yfinance`는 개인 학습 및 리서치 목적에는 편리하지만, Yahoo에서 공식 보증하는 상업용 API는 아니다. 회사 적용 단계에서는 데이터 이용 약관, 안정성, 과금, SLA를 따로 검토해야 한다.

회사 또는 운영 환경 후보:

- Financial Modeling Prep
- Finnhub
- Polygon.io
- Tiingo
- Nasdaq Data Link
- 사내 로그/집계 데이터 저장소

## 6. 기능 요구사항

### 6.1 MVP

- Streamlit 앱 실행
- 사이드바에서 종목 선택
- 기본 종목은 `TSLA`
- 기간 선택: 1년, 3년, 5년, 최대
- 예측 기간 선택: 7일, 30일, 90일, 180일
- `yfinance` 데이터 다운로드 및 SQLite 저장
- DB 저장 데이터 우선 조회
- 필요 시 yfinance 증분 업데이트
- Prophet 학습 및 예측
- Plotly 기반 시계열 차트 표시
- 실제 종가, 예측값, 예측 구간 표시
- 이상값 후보 마커 표시
- 기본 성능 지표 표시: MAE, RMSE, MAPE
- 최근 이상값 후보 테이블 표시

### 6.2 백테스트

백테스트는 과거 특정 시점까지만 학습하고, 이후 구간을 예측해 실제값과 비교하는 방식으로 구현한다.

구현된 백테스트 옵션:

- 학습 기간: 전체 데이터 중 앞 80%
- 테스트 기간: 뒤 20%
- 예측 horizon: 테스트 구간
- 지표: MAE, RMSE, MAPE, Coverage
- rolling cutoff 검증: 여러 cutoff 날짜를 잡아 cutoff별로 Prophet을 학습한다.
- 예측 기간별 성능 비교: 기본 후보는 7일, 30일, 90일이며 14일, 60일, 180일도 선택할 수 있다.
- 결과 저장: `backtest_runs`, `backtest_metrics`에 실행 설정과 지표를 저장한다.
- 날짜 정책 저장: `date_policy`로 미국 주식 거래일 기준과 매일 달력일 기준을 구분한다.
- 비교 화면: 저장된 결과를 종목별/설정별로 조회하고 MAPE, MAE, RMSE, Coverage 기준으로 비교한다.

추가 확장 후보:

- Prophet `cross_validation` API 기반 검증과 현재 rolling 구현 비교
- 이벤트 포함 전후 rolling 성능 비교 전용 화면
- 개별 예측 row 저장 또는 Parquet snapshot export

### 6.3 이벤트 관리

초기 이벤트 기능:

- UI에서 이벤트명, 날짜, 영향 범위 입력
- 이벤트 목록 테이블 표시
- 이벤트 CSV 업로드
- Prophet `holidays` 파라미터로 이벤트 반영
- 이벤트 DB 저장, 조회, 삭제
- 이벤트 반영 예측과 이벤트 제외 예측 비교

확장 이벤트 기능:

- Alpha Vantage 실적 발표 API 연동
- 이벤트 카테고리 분류
- 이벤트 포함/제외 비교
- 특정 이벤트 전후 평균 오차 분석

현재 구현된 외부 이벤트 연동:

- `Events` 탭에서 Alpha Vantage `EARNINGS_CALENDAR` 기반 실적 발표 일정을 수집한다.
- API key는 `.env`/환경변수 `ALPHA_VANTAGE_API_KEY` 또는 UI 입력 필드로 전달한다.
- 수집된 이벤트는 `category=earnings`, `source=alpha_vantage_earnings`로 저장한다.
- 같은 종목, 날짜, 카테고리의 수동 이벤트가 이미 있으면 API 이벤트를 중복 저장하지 않는다.
- 기존 `sync_runs`를 재사용해 외부 이벤트 API 호출 성공/실패/skip 이력을 기록한다.
- 최근 성공 sync가 있으면 기본 12시간 동안 재호출을 skip해 API 호출 제한에 대응한다.

### 6.4 다중 종목 확장

초기에는 `TSLA` 단일 종목 상세 화면을 기준으로 만들고, 다중 종목은 별도의 비교 화면으로 분리한다. 기본 후보는 다음 종목이다.

- `AAPL`
- `MSFT`
- `NVDA`
- `GOOGL`
- `AMZN`

다중 종목 확장 시 고려사항:

- 다운로드 실패 종목 처리
- 종목별 캐시
- 종목별 모델 학습 시간
- 종목 간 성능 비교 화면
- 여러 차트를 한 화면에 과도하게 넣지 않도록 UI 분리

현재 구현된 다중 종목 분석:

- `Single ticker`와 `Multi ticker` 화면을 사이드바에서 분리한다.
- 여러 preset 종목과 comma-separated custom ticker를 함께 선택할 수 있다.
- 선택 종목별로 SQLite 저장 데이터를 우선 조회하고, 필요한 경우 `yfinance` sync를 수행한다.
- 종목별 Prophet 예측과 80/20 holdout 백테스트를 같은 설정으로 실행한다.
- 종목별 MAE, RMSE, MAPE, Coverage를 비교한다.
- 종목별 이상값 개수와 전체 데이터 대비 이상값 발생 비율을 비교한다.
- 다중 분석 중 실패한 종목은 나머지 종목 결과와 분리해 오류 테이블로 보여준다.
- 다중 종목 holdout 결과는 선택적으로 DB에 저장할 수 있다.

## 7. UI 기획

### 7.1 기술 선택

UI는 Streamlit을 사용한다. Streamlit은 Python 코드만으로 데이터 앱을 빠르게 만들 수 있고, Prophet 실험처럼 입력값을 조정하며 그래프를 확인하는 도구에 잘 맞는다.

차트는 Plotly를 사용한다. Plotly는 Python용 인터랙티브 차트 라이브러리이며, Streamlit의 `st.plotly_chart`로 자연스럽게 표시할 수 있다.

### 7.2 화면 구성

사이드바:

- `Analysis`: 분석 화면 선택, 종목 입력/선택
- `Data`: 기간, 날짜 처리 방식, 수동 sync
- `Model`: 예측 기간, 예측 구간 폭, 이벤트 반영, 백테스트 실행 여부
- 분석 화면 선택: `Single ticker`, `Multi ticker`
- 종목 입력/선택
- 다중 종목 preset/custom ticker 선택
- 데이터 기간 선택
- 예측 기간 선택
- 예측 구간 폭 선택
- 이벤트 반영 여부
- 백테스트 실행 여부

메인 화면:

- 요약 지표 영역
- DB 상태, 마지막 동기화 시간, 데이터 범위
- 실제값/예측값/예측 구간 차트
- Prophet components 차트
- 이상값 후보 테이블과 설명 컬럼
- 백테스트 지표
- 이벤트 목록

탭 구성:

단일 종목 상세 화면:

- `Forecast`: 예측 차트와 Prophet components
- `Anomalies`: 이상값 후보와 경계 초과 설명
- `Backtest`: 백테스트 결과
- `Events`: 이벤트 관리
- `Data`: 원본 데이터 확인

다중 종목 비교 화면:

- `Performance`: 종목별 holdout 예측 성능 비교
- `Anomalies`: 종목별 이상값 발생 빈도 비교
- `Sync/Data`: 종목별 sync 결과와 데이터 범위 확인
- `Saved Backtests`: 저장된 백테스트 결과의 종목별/설정별 비교

## 8. 모델링 방향

### 8.1 기본 모델

기본 Prophet 모델은 다음 설정으로 시작한다.

- `weekly_seasonality=True`
- `yearly_seasonality=True`
- `daily_seasonality=False`
- `interval_width=0.8`
- `changepoint_prior_scale`는 기본값에서 시작 후 튜닝

날짜 생성 정책은 데이터 성격에 따라 분리한다.

- `US stock trading days`: 주식 데이터 기본값이다. 미래 예측 날짜에서 주말과 NYSE 휴장일을 제외한다.
- `Daily calendar days`: 서비스 일별 재생수처럼 매일 값이 있는 데이터에 사용한다. 주말과 공휴일도 예측 날짜에 포함한다.

이 정책은 Prophet 학습 후 미래 날짜 생성, DB 커버리지 표시, 백테스트 저장 설정에 함께 기록한다. 이벤트 날짜가 휴장일에 걸릴 수 있으므로 이벤트 영향 범위(`lower_window`, `upper_window`)를 통해 인접 거래일에 영향이 반영되도록 관리한다.

### 8.2 이상값 탐지

초기 기준:

- 실제값이 예측 구간 밖이면 이상값 후보
- 오차율이 큰 순으로 정렬
- 상방/하방 이상값을 구분

확장 기준:

- 잔차 z-score
- 수익률 기반 이상값
- 이동 변동성 대비 이상값
- Bollinger Band와 Prophet 구간 비교

### 8.3 서비스 데이터 적용 관점

회사 서비스의 일별 재생수는 주식보다 Prophet에 더 잘 맞을 가능성이 있다. 이유는 주말 효과, 휴일 효과, 캠페인 효과, 계절성 같은 반복 패턴이 주가보다 명확하게 나타날 수 있기 때문이다.

서비스 데이터 적용 시 추가 고려사항:

- 주말 재생수 상승 패턴
- 공휴일/연휴 영향
- 마케팅 캠페인
- 앱 업데이트
- 장애/점검
- 콘텐츠 공개일
- 외부 이벤트

## 9. 아키텍처 초안

초기 구조:

```text
ticker-scope/
  app.py
  requirements.txt
  data/
    ticker_scope.sqlite3
  docs/
    PROGRAM_PLAN.md
  ticker_scope/
    data/
      database.py
      market_data.py
      repositories.py
      sync.py
    modeling/
      prophet_model.py
      anomalies.py
      backtest.py
    ui/
      charts.py
    events/
      calendar.py
    date_policy.py
```

모듈 책임:

- `market_data.py`: yfinance 데이터 수집 및 정규화
- `database.py`: SQLite 연결, 스키마 초기화, DB 경로 관리
- `repositories.py`: 종목, 가격, 이벤트 데이터 저장/조회
- `sync.py`: yfinance와 SQLite 간 증분 동기화
- `prophet_model.py`: Prophet 학습/예측
- `anomalies.py`: 이상값 후보 계산
- `backtest.py`: 백테스트와 지표 계산
- `charts.py`: Plotly 차트 생성
- `calendar.py`: 수동 이벤트 및 API 이벤트 정규화
- `date_policy.py`: 달력일/미국 주식 거래일 날짜 생성 정책
- `app.py`: Streamlit 화면 구성

## 10. 개발 단계

### Phase 1: Tesla 단일 종목 MVP

- 프로젝트 기본 구조 생성
- 의존성 정의
- SQLite 스키마 초기화
- `TSLA` 5년 데이터 다운로드 및 DB 저장
- Prophet 학습/예측
- Plotly 차트 표시
- 이상값 후보 표시

### Phase 2: 데이터 저장소 안정화

- 종목/가격 repository 구현
- yfinance 증분 업데이트
- 강제 새로고침 기능
- 동기화 이력 기록
- DB 데이터 기반 Prophet 학습으로 전환
- 스키마 버전 관리와 저장 데이터 검증
- DB 상태와 최근 sync 이력 UI 표시

### Phase 3: 백테스트

- train/test split 기반 백테스트
- 성능 지표 계산
- 백테스트 차트와 테이블 추가
- 예측 기간별 성능 비교
- rolling cutoff 기반 백테스트
- 백테스트 실행 이력과 지표 DB 저장
- 종목별/설정별 저장 성능 비교 화면

### Phase 4: 이벤트 기능

- 수동 이벤트 등록
- 이벤트 CSV 업로드
- 이벤트 DB 저장
- Prophet holidays 연동
- 이벤트 반영 전후 비교

현재 구현 상태:

- `Events` 탭에서 수동 이벤트를 등록할 수 있다.
- 이벤트 필드는 이벤트명, 날짜, 카테고리, 종목, `lower_window`, `upper_window`, notes를 사용한다.
- 종목을 비워두면 전체 종목에 적용되는 글로벌 이벤트로 저장한다.
- 선택 종목의 이벤트와 글로벌 이벤트를 함께 조회해 Prophet `holidays` 파라미터에 전달한다.
- 사이드바에서 `Use DB events` 옵션으로 DB 이벤트 반영 여부를 켜고 끌 수 있다.
- `Events` 탭에서 이벤트 반영 예측과 이벤트 제외 예측을 비교 차트와 테이블로 확인할 수 있다.
- 등록된 이벤트는 UI에서 선택 삭제할 수 있다.

### Phase 5: 다중 종목

- 종목 입력/선택 확장
- 종목별 DB 저장 및 증분 업데이트
- 종목별 성능 비교
- 종목별 이상값 발생 빈도 비교
- 단일 종목 상세 화면과 다중 종목 비교 화면 분리
- 다중 종목 holdout 결과 선택 저장
- 실패/누락 데이터 처리

### Phase 6: 거래일 기준 처리

- Prophet 미래 날짜 생성 시 데이터 날짜 정책 적용
- 주식 데이터는 주말과 NYSE 휴장일 제외
- 서비스 일별 데이터는 달력일 전체 사용
- DB 커버리지와 sync 누락 구간 판단에 미국장 거래 캘린더 적용
- 백테스트 저장 설정에 날짜 정책 기록

현재 구현 상태:

- 사이드바 `Date handling`에서 `US stock trading days`와 `Daily calendar days`를 선택할 수 있다.
- 주식 기본값은 `US stock trading days`이며, Prophet 미래 예측 날짜에서 주말과 NYSE 휴장일을 제외한다.
- `Daily calendar days`는 서비스 일별 재생수처럼 매일 값이 있는 데이터 검증을 위해 달력일 전체를 유지한다.
- 로컬 DB 커버리지의 긴 누락 구간 계산은 선택한 날짜 정책을 기준으로 표시한다.
- yfinance 가격 sync의 내부 누락 구간 보강은 미국장 거래일 기준으로 판단한다.

### Phase 7: 외부 이벤트 API 연동

- 실적 발표 캘린더 API 후보 조사
- API 키 관리
- 이벤트 데이터 정규화
- 이벤트 자동 수집
- 수동 이벤트와 API 이벤트 병합 및 중복 제거
- API 호출 제한 및 캐시 적용

현재 구현 상태:

- 1차 provider는 Alpha Vantage `EARNINGS_CALENDAR`로 선정했다.
- 선정 이유는 공식 문서가 명확하고, symbol별 3/6/12개월 horizon을 CSV로 받을 수 있어 MVP 구현과 테스트가 단순하기 때문이다.
- FMP Earnings Calendar는 과거/미래 실적 데이터 확장 후보로 유지한다.
- UI에서 실적 발표 이벤트를 수동 sync할 수 있고, key가 없으면 명확한 오류를 표시한다.
- API 이벤트는 Prophet holidays 변환 경로를 수동 이벤트와 공유한다.

## 11. 성공 기준

MVP 완료 기준:

- Streamlit 앱에서 `TSLA` 최근 5년 데이터를 불러올 수 있다.
- 실제 종가, Prophet 예측값, 예측 구간이 한 차트에 표시된다.
- 예측 구간 밖의 날짜가 이상값 후보로 표시된다.
- 백테스트 지표가 화면에 표시된다.
- 코드가 종목 확장에 무리가 없는 구조로 분리되어 있다.

학습 성공 기준:

- Prophet의 입력 형식과 주요 출력값을 설명할 수 있다.
- 휴일/이벤트 데이터가 예측에 어떻게 반영되는지 설명할 수 있다.
- 예측 구간 기반 이상값 탐지의 한계를 설명할 수 있다.
- 주식 데이터와 서비스 재생수 데이터의 차이를 설명할 수 있다.

## 12. 리스크와 대응

| 리스크 | 설명 | 대응 |
| --- | --- | --- |
| 주식 데이터의 예측 난이도 | 주가는 외부 충격과 시장 심리에 크게 반응한다. | 투자 모델이 아닌 Prophet 학습용으로 명확히 제한한다. |
| yfinance 안정성 | 비공식 성격의 데이터 접근이므로 장애나 제한이 있을 수 있다. | SQLite에 데이터를 저장하고, 회사 적용 시 공식/상용 API를 검토한다. |
| 로컬 DB 스키마 변경 | 실험 중 컬럼과 테이블 구조가 바뀔 수 있다. | 초기에는 단순 스키마로 시작하고, 필요 시 SQLAlchemy/Alembic을 도입한다. |
| 이벤트 과적합 | 이벤트를 너무 많이 넣으면 과거 설명에 치우칠 수 있다. | 이벤트 전후 백테스트 성능을 비교한다. |
| 주말/휴장일 처리 | 주식 데이터는 매일 존재하지 않고, 서비스 지표는 매일 존재할 수 있다. | `Date handling`으로 미국장 거래일과 달력일 정책을 분리한다. |
| Prophet 한계 | 급격한 비반복 이벤트나 시장 충격 예측에는 약하다. | 이상값 탐지와 설명 보조 도구로 사용한다. |

## 13. 참고 자료

- Prophet seasonality, holidays, regressors: https://facebook.github.io/prophet/docs/seasonality%2C_holiday_effects%2C_and_regressors.html
- Prophet diagnostics and cross validation: https://facebook.github.io/prophet/docs/diagnostics.html
- yfinance PyPI: https://pypi.org/project/yfinance/
- Streamlit `st.plotly_chart`: https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart
- Financial Modeling Prep earnings calendar: https://site.financialmodelingprep.com/developer/docs/stable/earnings-calendar
