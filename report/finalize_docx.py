"""REPORT.docx 후처리: 모든 표의 첫 행을 '제목 행 반복'으로 지정한다.

pandoc은 표의 머리행에 <w:tblHeader/>를 넣지 않는다. 그래서 표가 페이지 경계를
넘어가면 둘째 페이지부터 머리행 없이 숫자만 이어져 어느 열이 어느 정책인지
알 수 없게 된다. 각 표의 첫 <w:tr>에 이 속성을 넣어 Word가 페이지마다 머리행을
다시 그리도록 한다.

실행: python3 report/finalize_docx.py [docx 경로]   (기본값 report/REPORT.docx)
"""
import re
import shutil
import sys
import zipfile

DOC = "word/document.xml"


def add_header_repeat(xml: str) -> tuple[str, int]:
    out = []
    pos = 0
    count = 0
    for tbl in re.finditer(r"<w:tbl>.*?</w:tbl>", xml, re.S):
        body = tbl.group(0)
        first = re.search(r"<w:tr\b[^>]*>", body)
        if not first:
            continue
        head_end = first.end()
        rest = body[head_end:]
        if rest.lstrip().startswith("<w:trPr>"):
            # 이미 trPr이 있으면 그 안에 넣는다
            new_body = re.sub(r"<w:trPr>", "<w:trPr><w:tblHeader/>", body, count=1)
        else:
            new_body = body[:head_end] + "<w:trPr><w:tblHeader/></w:trPr>" + rest
        if "<w:tblHeader/>" in new_body:
            count += 1
        out.append((tbl.start(), tbl.end(), new_body))

    for start, end, new_body in reversed(out):
        xml = xml[:start] + new_body + xml[end:]
    return xml, count


def main(path="report/REPORT.docx"):
    backup = path + ".bak"
    shutil.copy(path, backup)

    with zipfile.ZipFile(backup) as zin:
        items = {n: zin.read(n) for n in zin.namelist()}

    xml, n = add_header_repeat(items[DOC].decode("utf-8"))
    items[DOC] = xml.encode("utf-8")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in items.items():
            zout.writestr(name, data)

    print(f"{path}: 표 {n}개의 첫 행을 제목 행 반복으로 지정")


if __name__ == "__main__":
    main(*sys.argv[1:])
