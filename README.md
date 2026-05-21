# Ticker Scope

Ticker Scope는 Meta Prophet을 사용해 주식 일별 종가를 예측하고, 예측 구간을 벗어난 이상값 후보를 찾고, 과거 구간 기준으로 모델 성능을 백테스트하는 Python/Streamlit 애플리케이션입니다.

초기 실험 대상은 Tesla(`TSLA`)이지만, `yfinance`에서 조회 가능한 다른 미국 주식 티커도 함께 분석할 수 있습니다. 이 앱은 투자 판단용이 아니라 Prophet의 동작 방식, 이벤트 반영, 이상값 탐지, 백테스트 흐름을 학습하고 검증하기 위한 개인 프로젝트입니다.

## 실행 방법

가장 간단한 실행 방법은 프로젝트 루트에서 `run.sh`를 실행하는 것입니다. `.venv`가 없으면 자동으로 만들고, 필요한 의존성이 없으면 설치한 뒤 Streamlit을 시작합니다.

```bash
./run.sh
```

수동으로 실행하려면 다음 명령을 사용합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 `http://localhost:8501`로 접속합니다.

## Standalone 빌드

개발 의존성을 설치한 뒤 PyInstaller로 단독 실행 파일을 만들 수 있습니다.

```bash
python -m pip install -r requirements-dev.txt
pyinstaller TickerScope.spec --clean --noconfirm
```

빌드 결과는 `dist/TickerScope`에 생성됩니다. 실행하면 내부에서 Streamlit 서버를 띄우고 기본 브라우저를 엽니다.

standalone 실행에서는 SQLite DB가 실행파일 내부가 아니라 OS별 사용자 데이터 폴더에 저장됩니다.

- macOS: `~/Library/Application Support/Ticker Scope/ticker_scope.sqlite3`
- Windows: `%APPDATA%\Ticker Scope\ticker_scope.sqlite3`
- Linux: `$XDG_DATA_HOME/ticker-scope/ticker_scope.sqlite3` 또는 `~/.local/share/ticker-scope/ticker_scope.sqlite3`

개발 실행처럼 `TICKER_SCOPE_DB_PATH`를 지정하면 standalone에서도 해당 DB 경로를 우선 사용합니다.

## 개발/테스트

테스트와 커버리지 도구까지 설치하려면 개발 의존성을 사용합니다.

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p 'test_*.py' -v
python -m coverage run -m unittest discover -s tests -p 'test_*.py'
python -m coverage report
```

## 데이터 저장소

개발 실행에서는 앱이 `data/ticker_scope.sqlite3` SQLite DB를 로컬 저장소로 사용합니다. 가격 데이터가 필요할 때마다 `yfinance`를 새로 호출하지 않고, 먼저 DB에 저장된 데이터를 확인한 뒤 비어 있는 날짜 구간만 동기화합니다.

테스트나 별도 실험용 DB를 쓰고 싶을 때는 `TICKER_SCOPE_DB_PATH` 환경변수로 DB 파일 경로를 지정할 수 있습니다.

```bash
TICKER_SCOPE_DB_PATH=data/my_experiment.sqlite3 streamlit run app.py
```

## 외부 이벤트 API 설정

실적 발표 캘린더 자동 수집은 Alpha Vantage `EARNINGS_CALENDAR` API를 사용합니다. API key는 다음 중 하나로 설정할 수 있습니다.

```bash
ALPHA_VANTAGE_API_KEY=your_api_key
```

또는 `Events` 탭의 `Alpha Vantage API key` 입력 필드에 임시로 입력할 수 있습니다. 앱은 최근 성공한 실적 이벤트 동기화가 있으면 기본 12시간 동안 재호출을 건너뛰어 API 호출 제한에 대응합니다. `Force API refresh`를 켜면 이 캐시 보호를 무시하고 다시 호출합니다.

## Fear & Greed Index

주식시장 심리 확인용 Fear & Greed Index는 CNN 데이터를 사용하는 `fear-greed` 패키지를 통해 동기화합니다. 별도 API key는 필요하지 않지만, CNN 내부 데이터 엔드포인트에 의존하므로 응답 형식이 바뀌면 자동 동기화가 실패할 수 있습니다.

자동 동기화가 실패하거나 장기 과거 데이터를 보강하고 싶을 때는 `Sentiment` 탭에서 날짜와 점수를 수동 입력하거나 CSV로 가져올 수 있습니다. 같은 날짜에 여러 값이 있으면 `manual`, `csv_import`, `cnn_api` 순서로 우선 표시됩니다.

## 화면 구성

사이드바는 `Analysis`, `Data`, `Model` 세 영역으로 구성됩니다. 본문은 선택한 분석 모드에 따라 단일 종목 상세 화면 또는 다중 종목 비교 화면으로 바뀝니다.

## Analysis

### Single ticker

하나의 종목을 자세히 분석하는 모드입니다. 선택한 티커에 대해 데이터 동기화, Prophet 예측, 이상값 탐지, 백테스트, 이벤트 관리, 시장 심리 확인, 저장 데이터 확인을 모두 수행합니다.

단일 종목을 깊게 보고 싶을 때 사용합니다. 예를 들어 `TSLA`의 최근 5년 가격을 기준으로 향후 30거래일 예측, 실적 이벤트 반영 여부 비교, 과거 백테스트 결과 저장을 확인할 수 있습니다.

### Multi ticker

여러 종목을 한 번에 비교하는 모드입니다. 선택한 모든 티커에 대해 데이터를 동기화하고, 동일한 모델 설정으로 예측 및 80/20 Holdout 백테스트를 실행합니다.

종목별 `MAPE`, `MAE`, `RMSE`, `Coverage`, 이상값 빈도, 동기화 상태를 비교할 때 사용합니다. 다만 개별 종목의 이벤트 등록, 상세 Forecast/Anomalies/Backtest 화면은 `Single ticker`에서 확인하는 편이 좋습니다.

### Preset

앱에 미리 등록된 대표 티커 목록입니다. `Single ticker`에서는 하나를 선택하고, `Multi ticker`에서는 여러 개를 선택할 수 있습니다.

### Custom ticker

Preset에 없는 티커를 직접 입력하는 기능입니다. `Single ticker`에서는 하나의 티커를 입력합니다. `Multi ticker`에서는 `META, NFLX`처럼 쉼표로 여러 개를 입력할 수 있습니다.

입력한 티커는 대문자로 정규화됩니다. 단, `yfinance`에서 조회할 수 없는 티커이거나 데이터가 없는 티커는 분석 중 오류로 표시될 수 있습니다.

## Data

### Period

분석에 사용할 과거 데이터 기간입니다.

- `1y`: 최근 1년
- `3y`: 최근 3년
- `5y`: 최근 5년
- `10y`: 최근 10년
- `max`: `yfinance`에서 제공하는 최대 기간

기간이 길수록 모델이 더 많은 과거 패턴을 학습할 수 있지만, 실행 시간이 늘어납니다.

### Data handling

Prophet이 미래 날짜를 만들 때 어떤 날짜를 예측 대상으로 볼지 정하는 옵션입니다.

- `US stock trading days`: 미국 주식 거래일 기준입니다. 주말과 NYSE 휴장일을 제외합니다. 주식 분석의 기본 권장값입니다.
- `Daily calendar days`: 달력일 기준입니다. 주말과 공휴일도 포함합니다. 회사 서비스의 일별 재생수처럼 매일 값이 존재하는 데이터에 적합합니다.

주식 데이터는 주말/휴장일에 가격이 없기 때문에 `US stock trading days`가 자연스럽습니다. 반대로 서비스 지표는 주말에도 값이 있으므로 `Daily calendar days`를 써야 주말 패턴이 모델에 반영됩니다.

`Sync now` 버튼은 선택한 종목과 기간의 데이터를 강제로 다시 동기화합니다.

## Model

### Forecast days

오늘 이후 몇 개의 미래 날짜를 예측할지 정합니다. `Data handling`이 `US stock trading days`이면 예측 일수는 거래일 기준이고, `Daily calendar days`이면 달력일 기준입니다.

### Interval width

예측 구간의 폭입니다. 예를 들어 `0.8`은 Prophet이 약 80% 신뢰 구간에 해당하는 `yhat_lower`와 `yhat_upper`를 만듭니다.

값을 높이면 예측 범위가 넓어져 이상값이 덜 잡힐 수 있습니다. 값을 낮추면 범위가 좁아져 이상값이 더 많이 잡힐 수 있습니다.

### Use DB events

DB에 등록된 이벤트를 Prophet `holidays` 파라미터로 반영할지 선택합니다.

켜져 있으면 수동 이벤트와 외부 API로 수집한 이벤트가 예측에 반영됩니다. 꺼져 있으면 이벤트를 무시하고 가격 시계열만으로 예측합니다. 이벤트가 예측에 얼마나 영향을 주는지는 `Events` 탭의 `Forecast comparison`에서 비교할 수 있습니다.

### Backtest

`Single ticker` 화면에서 백테스트 탭을 활성화할지 선택합니다. 백테스트는 과거 데이터 일부를 일부러 숨긴 뒤, 모델이 숨겨진 구간을 얼마나 잘 예측했는지 확인하는 기능입니다.

## Ticker Scope

단일 종목 화면 상단에는 현재 분석 결과와 로컬 DB 상태가 요약됩니다.

### Latest close

선택한 기간 내 가장 최근 날짜의 종가입니다. 앱은 조정 종가 기준 데이터를 사용합니다.

### Latest date

현재 분석에 사용된 가격 데이터의 마지막 날짜입니다.

### Anomalies

실제 가격이 Prophet의 예측 구간을 벗어난 날짜 수입니다. 예측 구간 위로 벗어나면 `above`, 아래로 벗어나면 `below`로 분류됩니다.

### DB price rows

로컬 SQLite DB에 저장된 전체 가격 row 수입니다. 화면에 표시되는 선택 종목의 row 수가 아니라 DB 전체의 가격 데이터 저장량입니다.

### Data range

현재 선택한 종목과 기간에 대해 DB가 보유한 데이터의 시작일과 종료일입니다.

### Last sync

가장 최근 데이터 동기화가 끝난 시각과 상태입니다. 시간은 KST 기준으로 표시됩니다.

### Freshness

DB에 저장된 마지막 가격 날짜가 현재 기준으로 얼마나 오래되었는지 나타냅니다. 값이 작을수록 최신 데이터에 가깝습니다.

## Forecast

`Forecast` 탭은 실제 가격, Prophet 예측, 예측 구간, 이동평균선, 이상값, 이벤트를 한 그래프에서 보여줍니다. Fear & Greed 데이터가 저장되어 있으면 같은 시간축을 공유하는 하단 서브차트가 함께 표시됩니다.

### 그래프 범례

- `Events`: DB에 등록된 이벤트 날짜입니다. `Use DB events`가 켜져 있을 때 Forecast 그래프에 표시됩니다.
- `Anomaly`: 실제 가격이 예측 범위 밖에 있는 지점입니다.
- `Actual`: 실제 관측된 종가입니다.
- `MA 5`, `MA 20`, `MA 60`, `MA 120`, `MA 240`: 실제 종가 기준 5일, 20일, 60일, 120일, 240일 이동평균선입니다. Forecast 탭의 `Moving averages` 선택값이나 그래프 범례 클릭으로 표시 여부를 조정할 수 있습니다.
- `Forecast`: Prophet이 예측한 중심값입니다. 내부적으로는 `yhat`입니다.
- `Forecast range`: Prophet 예측 하한과 상한 사이의 범위입니다. 내부적으로는 `yhat_lower`부터 `yhat_upper`까지입니다.
- `Fear & Greed`: CNN Fear & Greed Index입니다. 가격 축과 섞지 않고 0~100 고정 축의 서브차트로 표시됩니다.

### Prophet components

Prophet이 예측값을 어떤 구성 요소로 나누어 보고 있는지 보여주는 차트입니다.

- `Trend`: 장기적인 상승/하락 방향입니다.
- `Weekly`: 요일별 반복 패턴입니다. 주식 거래일 기준에서는 거래일 데이터에서 추정되는 주간 효과입니다.
- `Yearly`: 연중 특정 시기마다 반복되는 계절성입니다.
- `Holidays`: DB 이벤트가 예측에 주는 효과입니다. `Use DB events`가 켜져 있고 반영 가능한 이벤트가 있을 때 의미가 있습니다.

## Anomalies

`Anomalies` 탭은 예측 구간 밖으로 벗어난 날짜만 표로 보여줍니다.

주요 컬럼은 다음과 같습니다.

- `ds`: 날짜입니다.
- `y`: 실제 종가입니다.
- `yhat`: Prophet 예측 중심값입니다.
- `expected_range`: 정상으로 기대한 예측 구간입니다.
- `direction`: 실제값이 구간보다 위인지(`above`), 아래인지(`below`) 나타냅니다.
- `bound_exceeded`: 벗어난 경계입니다. `upper` 또는 `lower`입니다.
- `distance_from_bound`: 예측 경계에서 얼마나 벗어났는지 가격 단위로 표시합니다.
- `distance_from_bound_pct`: 벗어난 폭을 실제값 대비 비율로 표시합니다.
- `error_pct`: 실제값과 예측 중심값의 차이를 비율로 표시합니다.
- `interval_width_value`: 예측 상한과 하한 사이의 폭입니다.
- `explanation`: 왜 이상값으로 분류되었는지 읽을 수 있는 문장입니다.

이상값은 투자 신호가 아니라 “Prophet이 학습한 패턴으로는 설명하기 어려웠던 지점”으로 보는 것이 좋습니다.

## Forecast Replay

`Forecast Replay` 탭은 과거의 특정 기준일까지 학습했을 때 Prophet 예측선과 예측 구간이 어떻게 보였는지 재생합니다.

슬라이더를 드래그해 기준 날짜를 크게 이동하거나, 좌우 화살표 버튼으로 한 관측일씩 미세 조정할 수 있습니다. 슬라이더는 실제 가격 row가 있는 관측일만 선택합니다.

차트에는 전체 `Actual`, 선택한 기준일까지 학습한 `Forecast`, `Forecast range`, 그리고 기준 날짜를 나타내는 세로선이 표시됩니다. 기준 날짜 이후의 `Actual`은 그 시점에는 알 수 없었던 실제 결과이므로, 예측선이 이후 실제 흐름을 얼마나 따라갔는지 눈으로 비교하는 용도로 보면 됩니다.

## Backtest

`Backtest` 탭은 과거 데이터를 기준으로 Prophet 예측 성능을 확인합니다.

### Backtest mode

`Holdout`과 `Rolling` 두 가지 방식이 있습니다.

`Holdout`은 전체 과거 데이터의 앞 80%만 학습에 사용하고, 뒤 20%를 테스트 구간으로 남겨둡니다. 그 뒤 모델이 테스트 구간을 얼마나 잘 예측했는지 한 번 평가합니다. 단순하고 빠르지만, 평가 시점이 한 구간에 고정됩니다.

`Rolling`은 여러 개의 과거 시점을 기준점으로 잡고 반복 평가합니다. 예를 들어 2023년 어느 시점까지 학습한 뒤 7일/30일/90일 뒤를 예측하고, 다시 2024년 어느 시점까지 학습한 뒤 같은 방식으로 예측합니다. 여러 시점과 여러 예측 기간을 비교하므로 Holdout보다 현실적인 성능 감각을 얻기 좋지만 실행 시간이 더 오래 걸립니다.

### MAE

Mean Absolute Error입니다. 실제값과 예측값 차이의 절댓값 평균입니다.

가격 단위로 표시되므로 `MAE = 10`이면 평균적으로 약 10달러 정도 빗나갔다는 의미입니다. 낮을수록 좋습니다.

### RMSE

Root Mean Squared Error입니다. 큰 오차에 더 민감한 지표입니다.

갑자기 크게 틀린 구간이 있으면 MAE보다 RMSE가 더 크게 반응합니다. 낮을수록 좋습니다.

### MAPE

Mean Absolute Percentage Error입니다. 실제값 대비 예측 오차의 평균 비율입니다.

`MAPE = 5%`이면 평균적으로 실제값 대비 약 5% 정도 빗나갔다는 의미입니다. 종목별 가격 단위가 달라도 비교하기 쉬운 지표입니다. 낮을수록 좋습니다.

### Coverage

실제값이 Prophet 예측 구간(`yhat_lower` ~ `yhat_upper`) 안에 들어온 비율입니다.

`Interval width`를 0.8로 설정했다면 Coverage도 대략 80% 근처를 기대할 수 있습니다. 너무 낮으면 예측 구간이 실제 변동성을 충분히 담지 못한다는 뜻일 수 있고, 너무 높으면 구간이 지나치게 넓어 실용성이 떨어질 수 있습니다.

### Save holdout result

현재 Holdout 백테스트 결과를 DB에 저장합니다. 저장된 결과는 이후 `Saved performance comparison`에서 다른 설정이나 다른 종목의 결과와 비교할 수 있습니다.

### Saved performance comparison

DB에 저장된 백테스트 결과를 비교하는 영역입니다.

`Show all tickers`를 켜면 현재 종목뿐 아니라 DB에 저장된 모든 종목의 백테스트 결과를 함께 봅니다. `Comparison metric`에서 `mape`, `mae`, `rmse`, `coverage` 중 비교 기준을 선택할 수 있습니다.

## Events

`Events` 탭은 예측에 반영할 이벤트를 관리하고, 이벤트 반영 전/후 예측 차이를 비교합니다.

### External earnings calendar

Alpha Vantage 실적 발표 캘린더 API에서 선택 종목의 실적 발표 이벤트를 가져옵니다.

- `Alpha Vantage API key`: API key를 입력합니다. 비워두면 환경변수 또는 `.env`의 `ALPHA_VANTAGE_API_KEY`를 사용합니다.
- `Horizon`: 가져올 실적 캘린더 범위입니다. 예를 들어 `3month`, `6month`, `12month` 중 선택합니다.
- `Force API refresh`: 최근 성공한 동기화가 있어도 API를 다시 호출합니다.
- `Sync earnings events`: 외부 API에서 이벤트를 가져와 DB에 저장합니다.

외부 이벤트는 기존 수동 이벤트와 같은 `ticker + event_date + category` 조합이 있으면 중복 저장하지 않습니다.

### Manual event

사용자가 직접 이벤트를 등록하는 영역입니다.

- `Event name`: 이벤트 이름입니다.
- `Date`: 이벤트 날짜입니다.
- `Category`: 이벤트 종류입니다. 예: `earnings`, `macro`, `split`, `dividend`, `product`, `manual`, `service`.
- `Ticker`: 이벤트가 적용될 티커입니다. 특정 종목이 아닌 공통 이벤트로 쓰려면 내부 DB에서는 `NULL`인 글로벌 이벤트도 지원하지만, 현재 UI 입력은 티커 중심입니다.
- `Lower window`: 이벤트 날짜 이전 며칠까지 영향을 줄지 정합니다. 예를 들어 `-3`이면 이벤트 3일 전부터 반영합니다.
- `Upper window`: 이벤트 날짜 이후 며칠까지 영향을 줄지 정합니다.
- `Notes`: 이벤트에 대한 메모입니다.

예를 들어 실적 발표 전후 영향을 보고 싶다면 `Category = earnings`, `Lower window = -3`, `Upper window = 1`처럼 등록할 수 있습니다.

### Registered events

DB에 저장된 이벤트 목록입니다. 현재 선택 종목과 글로벌 이벤트가 함께 표시됩니다.

표에는 이벤트 날짜, 티커, 카테고리, 이벤트명, 적용 window, source, notes가 표시됩니다. `Delete selected event`로 선택한 이벤트를 삭제할 수 있습니다.

### Forecast comparison

이벤트를 반영한 예측과 반영하지 않은 예측을 비교합니다.

- `Actual`: 실제 가격입니다.
- `Without events`: 이벤트를 제외한 예측입니다.
- `With events`: DB 이벤트를 Prophet holidays로 반영한 예측입니다.
- `Events`: 비교 구간 안에 있는 이벤트 날짜입니다.

아래 표의 `delta`는 이벤트 반영 후 예측값에서 이벤트 미반영 예측값을 뺀 값입니다. `delta_pct`는 그 차이를 비율로 표시합니다.

## Sentiment

`Sentiment` 탭은 CNN Fear & Greed Index 데이터를 관리합니다.

- `Latest value`: 저장된 최신 Fear & Greed 점수입니다.
- `Classification`: 최신 점수의 구간 분류입니다.
- `Stored range`: SQLite에 저장된 Fear & Greed 날짜 범위입니다.
- `Last sync`: 최근 CNN Fear & Greed 동기화 시각과 상태입니다.
- `Sync CNN Fear & Greed`: `fear-greed` 패키지를 통해 최근 약 1년치 데이터를 가져와 저장합니다.
- `Manual entry`: 날짜와 0~100 점수를 직접 저장합니다.
- `CSV import`: `date,value` 필수 컬럼을 가진 CSV를 가져옵니다. `classification`, `notes` 컬럼은 선택입니다.
- `Stored sentiment values`: 저장된 원천 row입니다. 같은 날짜의 대표값은 `manual`, `csv_import`, `cnn_api` 우선순위로 Forecast 차트에 표시됩니다.

## Data

`Data` 탭은 로컬 저장소와 원천 가격 데이터를 확인하는 화면입니다.

### Local storage

현재 사용 중인 SQLite DB 경로와 저장 상태를 보여줍니다.

- `Stored price rows`: DB에 저장된 전체 가격 row 수입니다.
- `Symbols`: DB에 등록된 티커 수입니다.
- `Sync runs`: 데이터 동기화 실행 이력 수입니다.
- `Events`: 저장된 이벤트 수입니다.
- `Backtests`: 저장된 백테스트 실행 수입니다.
- `Sentiment`: 저장된 Fear & Greed 원천 row 수입니다.
- `Selected rows`: 현재 선택한 종목/기간에 해당하는 가격 row 수입니다.
- `Stored range`: 현재 선택한 종목/기간 기준으로 저장된 데이터 범위입니다.
- `Freshness days`: 마지막 저장 가격 날짜가 현재 기준으로 며칠 전인지입니다.
- `Longest gap`: 선택한 날짜 처리 방식 기준으로 가장 길게 비어 있는 예상 날짜 구간입니다.

### Recent sync runs

최근 데이터 동기화 이력을 보여줍니다. 가격 데이터 동기화와 외부 이벤트 API 동기화 상태를 확인할 수 있습니다.

성공, 실패, 캐시로 인한 skip 여부, 동기화 대상 기간, 가져온 row 수, 오류 메시지 등을 점검할 때 사용합니다.

### Price history

현재 선택한 종목과 기간에 대해 분석에 사용된 가격 데이터입니다.

주요 컬럼은 날짜, 시가, 고가, 저가, 종가, 거래량입니다. Prophet에는 이 중 날짜(`ds`)와 종가(`y`)가 사용됩니다.

## Multi Ticker 화면

`Multi ticker` 모드에서는 다음 탭이 표시됩니다.

- `Performance`: 종목별 예측 성능을 `mape`, `mae`, `rmse`, `coverage` 기준으로 비교합니다.
- `Anomalies`: 종목별 이상값 발생률과 이상값 상세 목록을 보여줍니다.
- `Sync/Data`: 종목별 데이터 row 수, 최신 날짜, 최근 동기화 시각, 이벤트 수, 동기화 메시지를 보여줍니다.
- `Saved Backtests`: 선택 종목들의 저장된 백테스트 결과를 비교합니다.

`Run multi-ticker analysis`를 누르면 선택된 모든 종목에 대해 데이터 동기화, 예측, 이상값 탐지, Holdout 백테스트가 실행됩니다.

## 해석 시 주의사항

Prophet은 추세, 계절성, 이벤트 효과를 설명하기 좋은 모델이지만 주가의 모든 급등락 원인을 알 수는 없습니다. 특히 주식 가격은 금리, 실적, 뉴스, 수급, 시장 심리 등 외부 요인의 영향을 크게 받습니다.

따라서 Ticker Scope의 Forecast, Anomaly, Backtest 결과는 모델 실험과 데이터 분석 관점에서 해석해야 하며, 투자 의사결정의 근거로 사용하면 안 됩니다.
