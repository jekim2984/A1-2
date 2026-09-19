# 🗺️ 국내 여행 추천 CLI 프로그램 (Travel Planner)

Google Gemini LLM API와 Kakao Local 장소 검색 API를 연동하여 사용자가 입력한 날짜에 최적화된 국내 여행지 및 맛집을 추천하고 최종 여행 리포트를 생성하는 파이썬 CLI 프로그램입니다.

---

## 📌 목차
1. [프로그램 개요](#-프로그램-개요)
2. [주요 기능 및 특징](#-주요-기능-및-특징)
3. [기술 스택 및 아키텍처](#-기술-스택-및-아키텍처)
4. [사전 준비 및 API 키 설정 (보안)](#-사전-준비-및-api-키-설정-보안)
5. [설치 및 실행 방법](#-설치-및-실행-방법)
6. [결과물 확인 방법](#-결과물-확인-방법)
7. [에러 처리 및 운영 정책](#-에러-처리-및-운영-정책)
8. [학습 및 기술 회고 (과제 목표 달성)](#-학습-및-기술-회고-과제-목표-달성)

---

## 📖 프로그램 개요

단일 API 호출에 그치지 않고, **서로 다른 두 개의 외부 REST API(LLM + 지도)를 유기적으로 조합**하여 가치 있는 여행 리포트를 도출하는 데이터 파이프라인을 구축했습니다.

* **입력**: 여행 예정 일자 (`-date "YYYY-MM-DD"`)
* **1단계 (LLM)**: 해당 시기(계절/월)에 최적화된 국내 여행지 2~3곳 추천 및 날씨, 축제 정보 구조화 생성 (JSON)
* **2단계 (지도 API)**: 도출된 추천 지역별 맛집 5곳 검색 (Kakao Local REST API)
* **3단계 (LLM)**: 1차 추천 데이터와 검색된 맛집 데이터를 융합하여 상세 Markdown 리포트 작성
* **저장**: `results/` 폴더에 원본 JSON 데이터와 최종 Markdown 리포트 자동 저장

---

## ✨ 주요 기능 및 특징

### 1. 기본 요구사항 100% 충족
* `argparse` 기반 CLI 인터페이스 (`-date "YYYY-MM-DD"`, `--date` 지원)
* 엄격한 날짜 포맷 검증 (비정상 날짜 입력 시 사용법 안내 후 종료)
* LLM JSON 구조화 출력 및 파싱 실패 시 프롬프트 보강 후 1회 재시도 정책
* 외부 의존성을 최소화하여 Python 표준 라이브러리(`urllib.request`, `json`, `argparse`)만으로도 완벽 동작

### 2. 보너스 과제 구현 완료
* **[보너스 1] 복수 지역 추천**:
  - 단일 지역 추천에 그치지 않고 계절에 어울리는 **2~3개 복수 지역(`recommended_cities`)**을 함께 추천
  - 각 지역별로 Kakao 장소 검색 API를 호출하여 지역당 5곳의 맛집 정보를 수집 및 리포트에 정리
* **[보너스 2] 결과 캐싱**:
  - 동일한 날짜(`-date`)로 재실행할 경우, 이미 저장된 `results/{date}_travel_data.json`이 존재하면 불필요한 API 호출을 건너뛰고 캐시 데이터를 즉시 활용
  - 강제로 새로 조회하고 싶을 때를 위한 `--no-cache` 옵션 지원

---

## 🛠️ 기술 스택 및 아키텍처

* **Language**: Python 3.10 이상 (Python 3.12 권장)
* **LLM API**: Google Gemini REST API (`gemini-3.5-flash-lite`, `gemini-flash-latest`)
* **지도/장소 API**: Kakao Local REST API (`/v2/local/search/keyword.json`)
* **라이브러리**: Python Standard Library (`urllib`, `json`, `argparse`, `os`, `pathlib`) + `python-dotenv` (선택적 지원)

### 데이터 흐름도 (Architecture Flow)

```
[사용자 CLI 입력]
   │  python travel_planner.py -date "YYYY-MM-DD"
   ▼
[1. 날짜 유효성 검사 및 캐시 확인]
   │
   ├─ (캐시 존재 시) ──► results/{date}_travel_data.json 로드 ──┐
   │                                                           │
   ▼ (캐시 없음 또는 --no-cache)                                  │
[2. Gemini API 1차 추천 호출]                                  │
   │  - JSON 강제 스키마 (도시, 날씨, 행사, 이유, 복수지역)         │
   │  - JSON 파싱 오류 시 1회 재시도                            │
   ▼                                                           │
[3. Kakao Local API 맛집 검색]                                 │
   │  - 각 지역별 'FD6' 음식점 5곳 검색                        │
   │  - 검색 결과 0건 또는 401 인증 실패 시 graceful fallback     │
   ▼                                                           │
[4. 원본 데이터 취합 및 JSON 캐시 저장]                         │
   │  - results/{date}_travel_data.json 저장                    │
   ▼                                                           ▼
[5. Gemini API 최종 리포트 Markdown 생성]
   │  - 종합 일정(오전/오후/저녁) 및 맛집 리스트 마크다운 작성
   │  - API 장애 시 로컬 템플릿 기반 폴백 제공
   ▼
[6. results/{date}_travel_plan.md 저장 완료 안내]
```

---

## 🔐 사전 준비 및 API 키 설정 (보안)

> [!CAUTION]
> **API 키 보안 주의사항**
> * API 키를 코드나 README, Git 커밋에 절대 직접 작성하지 마세요.
> * 본 프로젝트의 `.gitignore`에는 `.env` 및 `results/` 폴더가 등록되어 있어 키와 개인 데이터가 깃 저장소에 유출되지 않도록 보호합니다.

### 1. API 키 발급
1. **Google Gemini API Key**: [Google AI Studio](https://aistudio.google.com/)에서 무료 발급
2. **Kakao REST API Key**: [Kakao Developers 콘솔](https://developers.kakao.com/) > 애플리케이션 생성 후 `REST API 키` 복사

### 2. `.env` 파일 작성
프로젝트 루트 디렉터리에 `.env` 파일을 생성하고 발급받은 키를 입력합니다. (`.env.example` 참고)

```env
# Google Gemini API 키
GEMINI_API_KEY=AIzaSy...

# Kakao Developers REST API 키
KAKAO_REST_API_KEY=1234abcd5678efgh...
```

*(선택사항) 터미널 세션 환경변수로 직접 주입할 수도 있습니다:*
```bash
export GEMINI_API_KEY="AIzaSy..."
export KAKAO_REST_API_KEY="1234abcd5678efgh..."
```

---

## 🚀 설치 및 실행 방법

### 1. 환경 준비 (가상환경)
```bash
# Python 3.10+ 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate

# 의존성 설치 (선택사항, 기본 파이썬 표준 라이브러리만으로도 실행 가능)
pip install -r requirements.txt
```

### 2. 프로그램 실행 (CLI)

#### 기본 실행 (`-date` 또는 `--date`)
```bash
python travel_planner.py -date "2026-05-15"
# 또는
python travel_planner.py --date "2026-10-20"
```

#### 캐시 무시하고 새로 API 호출하기 (`--no-cache`)
동일한 날짜에 대해 새로운 추천 결과를 얻고 싶을 때 사용합니다.
```bash
python travel_planner.py -date "2026-10-20" --no-cache
```

#### 도움말 확인
```bash
python travel_planner.py --help
```

### 3. CLI 실행 화면 예시
```
$ python travel_planner.py -date "2026-10-20"

[1/3] 1차 추천 생성 중(LLM)...
  - recommended_cities: ["경주", "강릉", "제주"]
  - primary_city: "경주"
[2/3] 맛집 검색 중(지도/장소 API)...
  - [경주] 맛집 5곳 검색 완료
  - [강릉] 맛집 5곳 검색 완료
  - [제주] 맛집 5곳 검색 완료
[3/3] 최종 리포트 생성 중(LLM)...
  - 리포트 생성 완료

완료! results/2026-10-20_travel_plan.md 를 확인하세요.
(원본 데이터: results/2026-10-20_travel_data.json)
```

---

## 📂 결과물 확인 방법

실행이 완료되면 `results/` 디렉터리에 실행 일자를 접두사로 한 2가지 파일이 생성됩니다.

### 1. 원본 데이터 JSON (`results/{date}_travel_data.json`)
* 1차 추천 결과(도시, 날씨, 행사, 이유, 복수지역 목록)
* 각 지역별 맛집 검색 결과 목록 (`name`, `address`, `category`, `url`, `x`, `y`)
* 실행 중 발생한 오류 요약 리스트 (`errors`: `[]`)
* 실행 타임스탬프 (`created_at`)

### 2. 최종 여행 리포트 Markdown (`results/{date}_travel_plan.md`)
* `# YYYY-MM-DD 국내 여행 추천 리포트`
* `## 추천 지역` (복수 추천 지역 소개)
* `## 추천 이유` (각 지역의 매력 및 선정 근거)
* `## 날씨 요약` (체감 날씨 및 복장 팁)
* `## 행사/축제` (연계 축제 목록)
* `## 맛집 추천` (지역별 식당 이름, 카테고리, 도로명 주소, 카카오맵 상세 링크)
* `## 1일 일정 제안` (대표 추천 지역 기준 오전/오후/저녁 추천 동선)
* `## 오류 요약(errors)`

---

## 🛡️ 에러 처리 및 운영 정책

`guide.md`의 안전성 지침에 따라 예외 상황 발생 시 견고하게 대응합니다.

| 예외 상황 | 대응 방식 |
| :--- | :--- |
| **API 키 미설정** | 프로그램이 즉시 종료(`sys.exit(1)`)되며, `.env` 작성 및 환경변수 설정 가이드 출력 |
| **잘못된 날짜 형식** | 정규표현식 및 날짜 파싱 검증을 거쳐 오류 메시지와 CLI `usage`를 출력하고 종료 |
| **지도 API 인증 실패(401/403)** | 콘솔에 인증 실패 경고를 출력하고, 맛집 섹션을 `- 데이터 없음`으로 처리한 뒤 리포트 생성을 계속 진행 |
| **장소 검색 결과 0건** | 프로그램을 중단하지 않고 `errors`에 `EMPTY_RESULT`를 기록한 후 정상 진행 |
| **LLM JSON 파싱 오류** | 가이드 지침에 따라 프롬프트를 보강하여 1회에 한해 재시도 수행 |
| **Gemini 일시적 장애 (503/429)** | 지수 백오프 기반 재시도를 거치며, 실패 시에도 내장 로컬 리포트 템플릿으로 안전하게 폴백 생성 |

---

## 💡 학습 및 기술 회고 (과제 목표 달성)

### 1. REST API 요청/응답 구조 및 HTTP 메서드 (GET vs POST)
* **GET 메서드 (Kakao Local API)**:
  - 서버의 리소스를 조회하기 위해 사용됩니다.
  - 검색어(`query`), 카테고리(`category_group_code`), 개수(`size`) 등의 파라미터가 URL 쿼리 스트링(`?query=...&size=...`)에 포함되어 전송됩니다.
  - 멱등성(Idempotent)을 가지므로 캐싱에 적합합니다.
* **POST 메서드 (Gemini API)**:
  - 서버에 복잡한 데이터나 생성 요청을 전달할 때 사용됩니다.
  - 프롬프트와 생성 옵션(`responseMimeType`, `temperature` 등)이 요청 본문(HTTP Body, JSON 형태)에 담겨 전달되며, 요청 헤더에 `Content-Type: application/json`을 명시합니다.

### 2. LLM 출력의 구조화(JSON)와 파이프라인 연계
* 자연어는 사람이 읽기 좋지만, 프로그램의 다음 단계(예: 지도 API 쿼리)에서 인자로 활용하려면 불안정합니다.
* Gemini의 `generationConfig: {"responseMimeType": "application/json"}` 설정과 엄격한 스키마 프롬프트를 통해 LLM의 출력을 JSON으로 고정했습니다.
* 파싱된 JSON에서 `recommended_cities` 배열을 순회하며 지도 API의 검색어로 넘겨주는 **"데이터 조합 파이프라인"**을 완성했습니다.

### 3. 외부 API 호출 오류 대응 원칙
* 외부 API는 네트워크 지연, 인증 만료, 쿼터 제한(Rate Limit), 일시적 서버 장애(503) 등 언제든 실패할 수 있는 불확실성을 내포하고 있습니다.
* 본 프로그램은 한 부분의 실패(예: 맛집 API 인증 오류)가 전체 프로세스의 중단으로 이어지지 않도록 **결함 격리(Fault Isolation)**를 적용하여 "데이터 없음" 처리 후 리포트 생성을 이어가도록 설계했습니다.

### 4. API 키를 `.env`와 환경변수로 관리하는 이유
* **보안 사고 예방**: Git 등의 버전 관리 시스템에 소스 코드가 공개되더라도 비밀 키가 함께 유출되는 것을 차단합니다.
* **유지보수 및 배포 용이성**: 소스 코드 수정 없이 환경변수 변경만으로 개발/스테이징/운영 환경의 키를 교체할 수 있습니다.
* **과금 및 쿼터 보호**: 실수로 공용 저장소에 공개되어 발생할 수 있는 악의적 쿼터 남용 및 과금 폭탄을 방지합니다.

