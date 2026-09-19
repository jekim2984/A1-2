#!/usr/bin/env python3
"""
국내 여행 추천 CLI 프로그램 (Travel Planner)
- LLM API (Google Gemini) 및 지도/장소 API (Kakao Local) 연동
- 보너스 과제 포함: 복수 지역 추천(2~3곳) 및 결과 캐싱 지원
"""

import os
import sys
import json
import re
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import urllib.request
import urllib.error
import urllib.parse


# ==============================================================================
# 1. 환경 변수 및 .env 로더
# ==============================================================================
def load_env_file(filepath: Path = Path(".env")) -> None:
    """
    .env 파일이 존재할 경우 환경변수를 로드합니다.
    python-dotenv 패키지가 없어도 표준 라이브러리만으로 동작하도록 구현되었습니다.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(filepath)
        return
    except ImportError:
        pass

    if not filepath.exists() or not filepath.is_file():
        return

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    # 따옴표 제거
                    if len(val) >= 2 and (
                        (val[0] == '"' and val[-1] == '"') or 
                        (val[0] == "'" and val[-1] == "'")
                    ):
                        val = val[1:-1]
                    if key and key not in os.environ:
                        os.environ[key] = val
    except Exception as e:
        print(f"[경고] .env 파일을 읽는 중 오류가 발생했습니다: {e}", file=sys.stderr)


def validate_api_keys() -> Tuple[str, str]:
    """
    필수 API 키가 설정되어 있는지 검증합니다.
    미설정 시 설정 가이드를 출력하고 즉시 종료합니다.
    """
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    kakao_key = os.environ.get("KAKAO_REST_API_KEY", "").strip()

    missing = []
    if not gemini_key:
        missing.append("GEMINI_API_KEY (Google Gemini API 키)")
    if not kakao_key:
        missing.append("KAKAO_REST_API_KEY (Kakao Developers REST API 키)")

    if missing:
        print("=" * 65, file=sys.stderr)
        print("[오류] 필수 API 키가 설정되지 않았습니다.", file=sys.stderr)
        for m in missing:
            print(f"  - 누락된 키: {m}", file=sys.stderr)
        print("\n[설정 방법]", file=sys.stderr)
        print("  1) 프로젝트 루트 디렉터리의 .env 파일에 키를 작성하세요.", file=sys.stderr)
        print("     예시 (.env):", file=sys.stderr)
        print("       GEMINI_API_KEY=AIzaSy...", file=sys.stderr)
        print("       KAKAO_REST_API_KEY=1234abcd...", file=sys.stderr)
        print("  2) 또는 현재 터미널 세션에서 환경변수로 export 하세요.", file=sys.stderr)
        print("     export GEMINI_API_KEY=\"AIzaSy...\"", file=sys.stderr)
        print("     export KAKAO_REST_API_KEY=\"1234abcd...\"", file=sys.stderr)
        print("=" * 65, file=sys.stderr)
        sys.exit(1)

    return gemini_key, kakao_key


# ==============================================================================
# 2. Google Gemini API 클라이언트
# ==============================================================================
class GeminiClient:
    """
    Google Gemini REST API 연동 클라이언트 (표준 라이브러리 urllib 기반)
    """
    def __init__(self, api_key: str, model: Optional[str] = None):
        self.api_key = api_key
        # 환경변수 GEMINI_MODEL 또는 최신 안정 고속 모델 'gemini-3.5-flash-lite' 사용
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )

    def _call_api(self, prompt: str, is_json: bool = False, max_retries: int = 2) -> str:
        payload: Dict[str, Any] = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
            }
        }
        if is_json:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=data,
            headers={"Content-Type": "application/json"}
        )

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    res_body = response.read().decode("utf-8")
                    res_json = json.loads(res_body)
                    candidates = res_json.get("candidates", [])
                    if not candidates:
                        raise RuntimeError("Gemini API에서 후보 응답(candidates)이 비어 있습니다.")
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if not parts:
                        raise RuntimeError("Gemini API 응답 내 text part가 없습니다.")
                    return parts[0].get("text", "")
            except urllib.error.HTTPError as e:
                err_msg = e.read().decode("utf-8", errors="ignore")
                last_error = RuntimeError(f"Gemini API HTTP {e.code} 에러: {err_msg}")
                # 503(일시적 과부하) 또는 429(Rate Limit)의 경우 잠시 대기 후 재시도
                if e.code in (503, 429) and attempt < max_retries:
                    import time
                    time.sleep(2 * (attempt + 1))
                    continue
                raise last_error
            except urllib.error.URLError as e:
                last_error = RuntimeError(f"Gemini API 네트워크 연결 실패: {e.reason}")
                if attempt < max_retries:
                    import time
                    time.sleep(1)
                    continue
                raise last_error
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    import time
                    time.sleep(1)
                    continue
                raise last_error

        if last_error:
            raise last_error
        raise RuntimeError("Gemini API 호출 실패")

    def generate_travel_recommendation(self, date_str: str) -> Dict[str, Any]:
        """
        [1단계] 여행 날짜 기반 지역/날씨/행사 추천 (JSON 구조화 출력)
        - 보너스 과제 1 반영: 2~3개 복수 지역 추천 포함
        - 파싱 실패 시 1회 재시도 (Guide 제약조건 준수)
        """
        base_prompt = f"""
당신은 대한민국 국내 여행 플래너 AI입니다.
여행 예정 날짜: "{date_str}"

해당 시기(계절/월)에 여행하기 가장 좋은 대한민국 국내 여행지 2~3곳을 추천해 주세요.
반드시 아래 스키마를 만족하는 순수 JSON으로만 응답해 주세요. 다른 설명이나 마크다운 코드블록을 붙이지 마세요.

JSON 스키마:
{{
  "recommended_city": "가장 추천하는 대표 도시명 1개 (예: '제주' 또는 '강릉')",
  "weather": "해당 시기의 대표적인 날씨 요약 1~2문장",
  "events": ["해당 시기 인근 축제 또는 행사 후보 1~3개"],
  "reason": "해당 날짜에 여행하기 좋은 추천 근거 2~4문장",
  "recommended_cities": [
    {{
      "city": "도시명 (예: 제주, 강릉, 경주 등)",
      "weather": "해당 도시의 해당 시기 날씨 요약",
      "events": ["도시 관련 행사 또는 축제 1~3개"],
      "reason": "해당 도시 추천 근거 2~3문장"
    }}
  ]
}}
"""
        for attempt in range(2):
            try:
                current_prompt = base_prompt
                if attempt == 1:
                    current_prompt += "\n\n주의: 앞선 응답 파싱에 실패했습니다. 반드시 유효한 JSON 형식만 출력하세요."

                raw_text = self._call_api(current_prompt, is_json=True)
                # 혹시 코드블록(```json ... ```)이 포함되어 있다면 제거
                cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip(), flags=re.MULTILINE)
                cleaned = re.sub(r"```$", "", cleaned.strip(), flags=re.MULTILINE)

                parsed = json.loads(cleaned)
                # 필수 키 검증
                if "recommended_city" not in parsed:
                    if "recommended_cities" in parsed and parsed["recommended_cities"]:
                        parsed["recommended_city"] = parsed["recommended_cities"][0].get("city", "국내 인기 지역")
                    else:
                        raise ValueError("recommended_city 키가 누락되었습니다.")

                # recommended_cities 보장 (단일 추천만 반환되었을 경우 안전장치)
                if "recommended_cities" not in parsed or not isinstance(parsed["recommended_cities"], list):
                    parsed["recommended_cities"] = [
                        {
                            "city": parsed["recommended_city"],
                            "weather": parsed.get("weather", "비교적 온화함"),
                            "events": parsed.get("events", []),
                            "reason": parsed.get("reason", "")
                        }
                    ]

                return parsed
            except Exception as e:
                if attempt == 1:
                    raise RuntimeError(f"1차 추천 JSON 생성 및 파싱 재시도(1회) 실패: {e}")

        raise RuntimeError("1차 추천 생성 실패")

    def generate_final_report(
        self,
        date_str: str,
        rec_data: Dict[str, Any],
        places_by_city: Dict[str, List[Dict[str, Any]]],
        errors: List[Dict[str, Any]]
    ) -> str:
        """
        [3단계] 최종 여행 리포트 Markdown 생성
        """
        prompt = f"""
당신은 전문 여행 가이드 에디터입니다.
아래 제공된 1차 여행 추천 데이터와 지도 API로 검색한 맛집 정보, 그리고 오류 로그를 바탕으로
가독성 높고 친절한 최종 국내 여행 리포트(Markdown 형식)를 작성해 주세요.

[입력 데이터]
여행 일자: {date_str}
1차 추천 데이터: {json.dumps(rec_data, ensure_ascii=False, indent=2)}
지역별 맛집 검색 결과: {json.dumps(places_by_city, ensure_ascii=False, indent=2)}
발생 오류 요약: {json.dumps(errors, ensure_ascii=False, indent=2)}

[작성 가이드라인]
반드시 다음 섹션 구조(마크다운 헤더)를 포함하여 완성도 높은 리포트를 작성하세요.
1. # {date_str} 국내 여행 추천 리포트
2. ## 추천 지역 (추천된 각 지역 소개)
3. ## 추천 이유 (각 지역별 추천 이유와 매력)
4. ## 날씨 요약 (각 지역별 예상 기온/날씨 팁)
5. ## 행사/축제 (각 지역별 연계 축제 및 행사)
6. ## 맛집 추천
   - 각 지역별로 검색된 맛집 이름, 주소, 카테고리, 링크(url)를 깔끔한 리스트 또는 표로 정리
   - 만약 맛집 검색 결과가 0건이거나 데이터가 없으면 반드시 "- 데이터 없음 (장소 검색 결과 0건)" 형태로 명시
7. ## 1일 일정 제안 (추천 지역 중 대표적인 곳을 기준으로 오전/오후/저녁 추천 동선 제시)
8. ## 오류 요약(errors)
   - 발생한 오류가 있으면 안내하고, 없으면 "발생한 오류가 없습니다."로 깔끔하게 표기

결과는 마크다운 텍스트만 출력해 주세요.
"""
        try:
            return self._call_api(prompt, is_json=False)
        except Exception as e:
            # LLM 오류 시에도 리포트 파일 저장이 가능하도록 템플릿 폴백 제공
            print(f"[경고] 최종 리포트 LLM 생성 중 오류({e})가 발생하여 기본 템플릿으로 생성합니다.", file=sys.stderr)
            return self._fallback_report(date_str, rec_data, places_by_city, errors)

    def _fallback_report(
        self,
        date_str: str,
        rec_data: Dict[str, Any],
        places_by_city: Dict[str, List[Dict[str, Any]]],
        errors: List[Dict[str, Any]]
    ) -> str:
        lines = [
            f"# {date_str} 국내 여행 추천 리포트",
            "",
            "## 추천 지역",
        ]
        cities = rec_data.get("recommended_cities", [])
        if cities:
            for item in cities:
                lines.append(f"- **{item.get('city')}**")
        else:
            lines.append(f"- **{rec_data.get('recommended_city')}**")

        lines.extend([
            "",
            "## 추천 이유",
        ])
        if cities:
            for item in cities:
                lines.append(f"### {item.get('city')}\n{item.get('reason', '')}\n")
        else:
            lines.append(rec_data.get("reason", ""))

        lines.extend([
            "",
            "## 날씨 요약",
        ])
        if cities:
            for item in cities:
                lines.append(f"- **{item.get('city')}**: {item.get('weather', '')}")
        else:
            lines.append(rec_data.get("weather", ""))

        lines.extend([
            "",
            "## 행사/축제",
        ])
        if cities:
            for item in cities:
                evs = item.get("events", [])
                ev_str = ", ".join(evs) if evs else "등록된 행사 없음"
                lines.append(f"- **{item.get('city')}**: {ev_str}")
        else:
            evs = rec_data.get("events", [])
            for ev in evs:
                lines.append(f"- {ev}")

        lines.extend([
            "",
            "## 맛집 추천",
        ])
        for city, places in places_by_city.items():
            lines.append(f"### {city} 맛집")
            if not places:
                lines.append("- 데이터 없음 (장소 검색 결과 0건)")
            else:
                for idx, p in enumerate(places, 1):
                    name = p.get("name", "이름 없음")
                    addr = p.get("address", "")
                    cat = p.get("category", "")
                    url = p.get("url", "")
                    cat_str = f" ({cat})" if cat else ""
                    url_str = f" [상세보기]({url})" if url else ""
                    lines.append(f"{idx}. **{name}**{cat_str} - {addr}{url_str}")
            lines.append("")

        lines.extend([
            "## 1일 일정 제안",
            "- **오전**: 주요 관광지 및 산책 코스 방문",
            "- **오후**: 추천 맛집 방문 및 지역 대표 행사/카페 투어",
            "- **저녁**: 야경 명소 감상 및 여유로운 휴식",
            "",
            "## 오류 요약(errors)",
        ])
        if errors:
            for err in errors:
                lines.append(f"- [{err.get('step')}] {err.get('type')}: {err.get('message')}")
        else:
            lines.append("- 발생한 오류가 없습니다.")

        return "\n".join(lines)


# ==============================================================================
# 3. Kakao Local API 클라이언트 (장소/맛집 검색)
# ==============================================================================
class KakaoLocalClient:
    """
    Kakao Developers Local REST API 연동 클라이언트
    """
    def __init__(self, rest_api_key: str):
        self.api_key = rest_api_key
        self.base_url = "https://dapi.kakao.com/v2/local/search/keyword.json"

    def search_restaurants(
        self, city: str, count: int = 5
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        도시명을 기준으로 맛집 검색
        반환값: (맛집 목록, 에러 정보 객체 또는 None)
        """
        query = f"{city} 맛집"
        params = urllib.parse.urlencode({
            "query": query,
            "category_group_code": "FD6",  # 음식점 카테고리
            "size": min(count, 15),
            "sort": "accuracy"
        })
        url = f"{self.base_url}?{params}"

        headers = {
            "Authorization": f"KakaoAK {self.api_key}"
        }
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                docs = res_json.get("documents", [])

                if not docs:
                    err = {
                        "step": "place_search",
                        "city": city,
                        "type": "EMPTY_RESULT",
                        "message": f"0 results for query='{query}'"
                    }
                    return [], err

                places: List[Dict[str, Any]] = []
                for d in docs[:count]:
                    x_val = float(d["x"]) if d.get("x") else None
                    y_val = float(d["y"]) if d.get("y") else None
                    place = {
                        "name": d.get("place_name", ""),
                        "address": d.get("road_address_name") or d.get("address_name", ""),
                        "category": d.get("category_name", ""),
                        "url": d.get("place_url", ""),
                        "x": x_val,
                        "y": y_val
                    }
                    places.append(place)

                return places, None

        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                print(f"    - 오류: 인증 실패({e.code}). 키 설정을 확인하세요.", file=sys.stderr)
                print("    - 맛집 섹션은 '데이터 없음'으로 처리하고 계속 진행합니다.", file=sys.stderr)
                err = {
                    "step": "place_search",
                    "city": city,
                    "type": "AUTH_ERROR",
                    "message": f"HTTP {e.code}: 카카오 API 인증 실패. KAKAO_REST_API_KEY를 점검하세요."
                }
            else:
                err = {
                    "step": "place_search",
                    "city": city,
                    "type": "HTTP_ERROR",
                    "message": f"HTTP {e.code}"
                }
            return [], err
        except urllib.error.URLError as e:
            err = {
                "step": "place_search",
                "city": city,
                "type": "NETWORK_ERROR",
                "message": str(e.reason)
            }
            return [], err
        except Exception as e:
            err = {
                "step": "place_search",
                "city": city,
                "type": "UNKNOWN_ERROR",
                "message": str(e)
            }
            return [], err


# ==============================================================================
# 4. 캐시 및 결과 파일 매니저
# ==============================================================================
class StorageManager:
    """
    결과 데이터 JSON 및 마크다운 리포트 저장, 캐싱(보너스 과제 2) 관리
    """
    def __init__(self, results_dir: Path = Path("results")):
        self.results_dir = results_dir
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def get_data_json_path(self, date_str: str) -> Path:
        return self.results_dir / f"{date_str}_travel_data.json"

    def get_report_md_path(self, date_str: str) -> Path:
        return self.results_dir / f"{date_str}_travel_plan.md"

    def load_cache(self, date_str: str) -> Optional[Dict[str, Any]]:
        """
        보너스 과제 2: 동일 날짜의 저장된 원본 JSON이 있는지 확인하고 로드
        """
        path = self.get_data_json_path(date_str)
        if path.exists() and path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[경고] 캐시 파일 읽기 실패({e}), 새로 API를 호출합니다.", file=sys.stderr)
        return None

    def save_data_json(self, date_str: str, data: Dict[str, Any]) -> Path:
        path = self.get_data_json_path(date_str)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    def save_report_md(self, date_str: str, report_content: str) -> Path:
        path = self.get_report_md_path(date_str)
        with open(path, "w", encoding="utf-8") as f:
            f.write(report_content)
        return path


# ==============================================================================
# 5. CLI 및 메인 컨트롤러
# ==============================================================================
def validate_date_format(date_str: str) -> bool:
    """
    입력 날짜가 YYYY-MM-DD 형식이며 유효한 날짜인지 검증
    """
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return False
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def main():
    # .env 파일 로드
    load_env_file()

    # CLI 파서 설정 (-date 및 --date 모두 지원)
    parser = argparse.ArgumentParser(
        description="국내 여행 추천 CLI 프로그램 (LLM & 지도 API 연동)",
        usage="python travel_planner.py -date YYYY-MM-DD [--no-cache]"
    )
    # -date / --date 지원 (guide.md 요구사항)
    parser.add_argument(
        "-date", "--date",
        dest="date",
        type=str,
        required=True,
        help="여행 예정 날짜 (형식: YYYY-MM-DD, 예: 2026-05-15)"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="기존에 저장된 캐시 데이터가 있어도 무시하고 새로 API를 호출합니다."
    )

    args = parser.parse_args()
    date_str = args.date.strip()

    # 입력값 검증: 날짜 형식이 올바르지 않으면 사용법을 출력하고 종료
    if not validate_date_format(date_str):
        print(f"\n[오류] 날짜 형식이 올바르지 않습니다: '{date_str}'", file=sys.stderr)
        print("올바른 형식: YYYY-MM-DD (예: 2026-05-15)", file=sys.stderr)
        parser.print_usage(file=sys.stderr)
        sys.exit(1)

    # API 키 검증 (미설정 시 즉시 종료)
    gemini_key, kakao_key = validate_api_keys()

    # 클라이언트 및 저장소 초기화
    gemini_client = GeminiClient(api_key=gemini_key)
    kakao_client = KakaoLocalClient(rest_api_key=kakao_key)
    storage = StorageManager()

    errors: List[Dict[str, Any]] = []
    rec_data: Dict[str, Any] = {}
    places_by_city: Dict[str, List[Dict[str, Any]]] = {}

    # 보너스 과제 2: 결과 캐싱 확인
    cached_data = None if args.no_cache else storage.load_cache(date_str)

    if cached_data:
        print(f"\n[캐시 발견] 기존 검색 결과({storage.get_data_json_path(date_str)})를 활용합니다.")
        rec_data = cached_data.get("recommendation", {})
        places_by_city = cached_data.get("places_by_city", {})
        errors = cached_data.get("errors", [])
        city_names = list(places_by_city.keys()) or [rec_data.get("recommended_city", "")]
        print(f"  - 추천 지역: {', '.join(city_names)}")
    else:
        # ----------------------------------------------------------------------
        # [1/3] 1차 추천 생성 중(LLM)...
        # ----------------------------------------------------------------------
        print(f"\n[1/3] 1차 추천 생성 중(LLM)...")
        try:
            rec_data = gemini_client.generate_travel_recommendation(date_str)
            cities_info = rec_data.get("recommended_cities", [])
            if cities_info:
                city_list_str = ", ".join([f'"{c.get("city")}"' for c in cities_info])
                print(f'  - recommended_cities: [{city_list_str}]')
                print(f'  - primary_city: "{rec_data.get("recommended_city")}"')
            else:
                print(f'  - recommended_city: "{rec_data.get("recommended_city")}"')
        except Exception as e:
            print(f"[오류] 1차 추천 생성 중 심각한 오류가 발생했습니다: {e}", file=sys.stderr)
            sys.exit(1)

        # ----------------------------------------------------------------------
        # [2/3] 맛집 검색 중(지도/장소 API)...
        # ----------------------------------------------------------------------
        print(f"[2/3] 맛집 검색 중(지도/장소 API)...")
        target_cities = [
            c.get("city") for c in rec_data.get("recommended_cities", []) if c.get("city")
        ]
        if not target_cities:
            target_cities = [rec_data.get("recommended_city")]

        for city in target_cities:
            places, err = kakao_client.search_restaurants(city, count=5)
            places_by_city[city] = places
            if err:
                errors.append(err)
                if err.get("type") == "EMPTY_RESULT":
                    print(f"  - [{city}] 검색 결과 0건(다음 단계로 진행)")
            else:
                print(f"  - [{city}] 맛집 {len(places)}곳 검색 완료")

        # 원본 데이터 JSON 저장 (캐싱 및 결과 제출용)
        full_data = {
            "date": date_str,
            "created_at": datetime.now().isoformat(),
            "recommendation": rec_data,
            "places_by_city": places_by_city,
            "errors": errors
        }
        json_path = storage.save_data_json(date_str, full_data)

    # ----------------------------------------------------------------------
    # [3/3] 최종 리포트 생성 중(LLM)...
    # ----------------------------------------------------------------------
    print(f"[3/3] 최종 리포트 생성 중(LLM)...")
    report_content = gemini_client.generate_final_report(
        date_str=date_str,
        rec_data=rec_data,
        places_by_city=places_by_city,
        errors=errors
    )
    md_path = storage.save_report_md(date_str, report_content)
    print(f"  - 리포트 생성 완료")

    # 최종 완료 안내 출력
    print(f"\n완료! {md_path} 를 확인하세요.\n(원본 데이터: {storage.get_data_json_path(date_str)})")


if __name__ == "__main__":
    main()
