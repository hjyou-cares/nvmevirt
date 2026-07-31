#!/usr/bin/env bash
#
# REPORT.md -> REPORT.html (그림까지 파일 하나에 포함된 단일 HTML)
#
# 이 HTML을 브라우저에서 열고 Ctrl+P -> "PDF로 저장"하면 제출용 PDF가 된다.
# docx 경로(pandoc + finalize_docx.py)와 달리 표 머리행 반복이 report.css의
# `thead { display: table-header-group }` 로 자동 처리되므로 후처리가 필요 없다.
#
# 사용법:
#   ./report/make_html.sh
#
set -euo pipefail

REPORT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPORT_DIR"

command -v pandoc > /dev/null || {
  echo "pandoc이 필요합니다: sudo apt install -y pandoc" >&2
  exit 1
}

# --self-contained: 그림(figures/*.png)과 CSS를 base64로 HTML 안에 넣어 파일 하나로
#   만든다. Windows 쪽으로 복사해서 열어도 그림이 깨지지 않게 하려는 목적.
#   (pandoc 2.19+ 에서는 --embed-resources --standalone 로 이름이 바뀌었지만,
#    이 환경의 pandoc 2.9는 --self-contained 를 쓴다.)
# --metadata pagetitle: 지정하지 않으면 pandoc이 빈 <title> 경고를 낸다. title이 아닌
#   pagetitle을 쓰는 이유는, title로 주면 본문 맨 위에 <h1 class="title">이 하나 더
#   생겨서 REPORT.md의 첫 줄 제목과 중복되기 때문이다.
pandoc REPORT.md \
  --standalone \
  --self-contained \
  --css=report.css \
  --metadata pagetitle="실습 1: NVMeVirt Cost-Benefit GC 구현 및 성능 분석" \
  -o REPORT.html

echo "생성 완료: $REPORT_DIR/REPORT.html ($(du -h REPORT.html | cut -f1))"
