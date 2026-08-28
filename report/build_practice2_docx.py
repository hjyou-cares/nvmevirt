#!/usr/bin/env python3
"""Build the Practice 2 Word report from the Markdown source."""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from finalize_docx import add_header_repeat


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "report/REPORT.md"
DEFAULT_OUTPUT = REPO_ROOT / "report/PRACTICE2_REPORT.docx"

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}

for prefix in ("w", "r", "wp", "a"):
    ET.register_namespace(prefix, NS[prefix])


def qn(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def prepare_markdown(source: Path) -> str:
    """Remove draft-only front matter and promote headings by one level."""
    lines = source.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    for index, line in enumerate(lines):
        if index == 0 and line.startswith("# "):
            continue
        if line.startswith("**유형진 (인턴)**") or line.startswith("> Word 문서:"):
            continue
        match = re.match(r"^(#{2,4})(\s+.*)$", line)
        if match:
            line = "#" * (len(match.group(1)) - 1) + match.group(2)
        output.append(line)
    return "\n".join(output).lstrip() + "\n"


def run_pandoc(source_text: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="practice2-docx-") as temp_dir:
        temp_source = Path(temp_dir) / "report.md"
        temp_source.write_text(source_text, encoding="utf-8")
        command = [
            "pandoc",
            str(temp_source),
            "--from=gfm",
            "--to=docx",
            "--standalone",
            "--toc",
            "--toc-depth=3",
            "--dpi=180",
            "--metadata",
            "title=NVMeVirt SLC Cache 구현 및 Migration 정책 분석",
            "--metadata",
            "subtitle=Practice 2 실험 보고서",
            "--metadata",
            "author=유형진 (인턴)",
            "--metadata",
            "date=2026-08-28",
            "--metadata",
            "toc-title=목차",
            f"--resource-path={REPO_ROOT / 'report'}",
            "--output",
            str(output),
        ]
        subprocess.run(command, cwd=REPO_ROOT, check=True)


def ensure(parent: ET.Element, tag: str) -> ET.Element:
    child = parent.find(tag, NS)
    if child is None:
        child = ET.SubElement(parent, qn(*tag.split(":")))
    return child


def set_attr(element: ET.Element, prefix: str, name: str, value: str) -> None:
    element.set(qn(prefix, name), value)


def set_font(rpr: ET.Element, size_half_points: int, *, bold: bool = False, color: str | None = None) -> None:
    fonts = ensure(rpr, "w:rFonts")
    for name, value in (("ascii", "Aptos"), ("hAnsi", "Aptos"), ("eastAsia", "맑은 고딕")):
        set_attr(fonts, "w", name, value)
    for tag in ("w:sz", "w:szCs"):
        set_attr(ensure(rpr, tag), "w", "val", str(size_half_points))
    if bold:
        ensure(rpr, "w:b")
    if color:
        set_attr(ensure(rpr, "w:color"), "w", "val", color)


def set_spacing(ppr: ET.Element, *, before: int = 0, after: int = 120, line: int = 300) -> None:
    spacing = ensure(ppr, "w:spacing")
    for name, value in (("before", before), ("after", after), ("line", line)):
        set_attr(spacing, "w", name, str(value))
    set_attr(spacing, "w", "lineRule", "auto")


def style_by_id(root: ET.Element, style_id: str) -> ET.Element | None:
    return root.find(f"w:style[@w:styleId='{style_id}']", NS)


def style_document(styles_xml: bytes) -> bytes:
    root = ET.fromstring(styles_xml)

    normal = style_by_id(root, "Normal")
    if normal is not None:
        set_font(ensure(normal, "w:rPr"), 21)
        set_spacing(ensure(normal, "w:pPr"), after=120, line=300)

    title = style_by_id(root, "Title")
    if title is not None:
        set_font(ensure(title, "w:rPr"), 46, bold=True, color="17365D")
        ppr = ensure(title, "w:pPr")
        set_attr(ensure(ppr, "w:jc"), "w", "val", "center")
        set_spacing(ppr, before=2600, after=280, line=300)

    subtitle = style_by_id(root, "Subtitle")
    if subtitle is not None:
        set_font(ensure(subtitle, "w:rPr"), 25, color="52677F")
        ppr = ensure(subtitle, "w:pPr")
        set_attr(ensure(ppr, "w:jc"), "w", "val", "center")
        set_spacing(ppr, before=0, after=240, line=280)

    date_style = style_by_id(root, "Date")
    if date_style is not None:
        set_font(ensure(date_style, "w:rPr"), 21, color="6B7785")
        ppr = ensure(date_style, "w:pPr")
        set_attr(ensure(ppr, "w:jc"), "w", "val", "center")
        set_spacing(ppr, before=0, after=120, line=260)

    for style_id, size, color, page_break in (
        ("Heading1", 31, "17365D", True),
        ("Heading2", 26, "244A73", False),
        ("Heading3", 23, "365F88", False),
    ):
        style = style_by_id(root, style_id)
        if style is None:
            continue
        set_font(ensure(style, "w:rPr"), size, bold=True, color=color)
        ppr = ensure(style, "w:pPr")
        set_spacing(ppr, before=260 if not page_break else 0, after=140, line=280)
        if page_break:
            ensure(ppr, "w:pageBreakBefore")

    caption = style_by_id(root, "ImageCaption")
    if caption is None:
        caption = style_by_id(root, "Caption")
    if caption is not None:
        set_font(ensure(caption, "w:rPr"), 18, color="4F5B66")
        ppr = ensure(caption, "w:pPr")
        set_attr(ensure(ppr, "w:jc"), "w", "val", "center")
        set_spacing(ppr, before=80, after=180, line=260)

    table = style_by_id(root, "Table")
    if table is not None:
        set_font(ensure(table, "w:rPr"), 18)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def page_break_paragraph() -> ET.Element:
    paragraph = ET.Element(qn("w", "p"))
    run = ET.SubElement(paragraph, qn("w", "r"))
    br = ET.SubElement(run, qn("w", "br"))
    set_attr(br, "w", "type", "page")
    return paragraph


def resize_drawings(root: ET.Element, max_width_emu: int = 5_700_000) -> None:
    for inline in root.findall(".//wp:inline", NS):
        extent = inline.find("wp:extent", NS)
        graphic_extent = inline.find(".//a:xfrm/a:ext", NS)
        if extent is None:
            continue
        width = int(extent.get("cx", "0"))
        height = int(extent.get("cy", "0"))
        if width <= max_width_emu or width == 0:
            continue
        new_height = round(height * max_width_emu / width)
        extent.set("cx", str(max_width_emu))
        extent.set("cy", str(new_height))
        if graphic_extent is not None:
            graphic_extent.set("cx", str(max_width_emu))
            graphic_extent.set("cy", str(new_height))


def style_tables(root: ET.Element) -> None:
    for table in root.findall(".//w:tbl", NS):
        properties = table.find("w:tblPr", NS)
        if properties is None:
            properties = ET.Element(qn("w", "tblPr"))
            table.insert(0, properties)
        layout = properties.find("w:tblLayout", NS)
        if layout is None:
            layout = ET.SubElement(properties, qn("w", "tblLayout"))
        set_attr(layout, "w", "type", "autofit")


def style_document_xml(document_xml: bytes, footer_rid: str) -> bytes:
    root = ET.fromstring(document_xml)
    body = root.find("w:body", NS)
    if body is None:
        raise RuntimeError("DOCX document body not found")

    toc_index = next((i for i, child in enumerate(list(body)) if child.tag == qn("w", "sdt")), None)
    if toc_index is not None:
        body.insert(toc_index, page_break_paragraph())

    section = body.find("w:sectPr", NS)
    if section is None:
        section = ET.SubElement(body, qn("w", "sectPr"))
    page_size = ensure(section, "w:pgSz")
    set_attr(page_size, "w", "w", "11906")
    set_attr(page_size, "w", "h", "16838")
    margins = ensure(section, "w:pgMar")
    for name, value in (("top", "1417"), ("right", "1417"), ("bottom", "1417"), ("left", "1417"), ("header", "708"), ("footer", "708"), ("gutter", "0")):
        set_attr(margins, "w", name, value)

    footer_ref = ET.Element(qn("w", "footerReference"))
    set_attr(footer_ref, "w", "type", "default")
    footer_ref.set(qn("r", "id"), footer_rid)
    section.insert(0, footer_ref)

    resize_drawings(root)
    style_tables(root)
    xml = ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")
    xml, _ = add_header_repeat(xml)
    return xml.encode("utf-8")


def add_footer_relationship(rels_xml: bytes) -> tuple[bytes, str]:
    root = ET.fromstring(rels_xml)
    existing = {item.get("Id", "") for item in root}
    number = 1
    while f"rIdFooter{number}" in existing:
        number += 1
    rid = f"rIdFooter{number}"
    relationship = ET.SubElement(root, f"{{{NS['pr']}}}Relationship")
    relationship.set("Id", rid)
    relationship.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer")
    relationship.set("Target", "footer1.xml")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), rid


def add_footer_content_type(content_types_xml: bytes) -> bytes:
    root = ET.fromstring(content_types_xml)
    if not any(item.get("PartName") == "/word/footer1.xml" for item in root):
        override = ET.SubElement(root, f"{{{NS['ct']}}}Override")
        override.set("PartName", "/word/footer1.xml")
        override.set("ContentType", "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def footer_xml() -> bytes:
    return b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p>
    <w:pPr><w:jc w:val="center"/></w:pPr>
    <w:r><w:rPr><w:color w:val="6B7785"/><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="begin"/></w:r>
    <w:r><w:rPr><w:color w:val="6B7785"/><w:sz w:val="18"/></w:rPr><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>
    <w:r><w:rPr><w:color w:val="6B7785"/><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="end"/></w:r>
  </w:p>
</w:ftr>'''


def update_fields_on_open(settings_xml: bytes) -> bytes:
    root = ET.fromstring(settings_xml)
    update_fields = root.find("w:updateFields", NS)
    if update_fields is None:
        update_fields = ET.SubElement(root, qn("w", "updateFields"))
    set_attr(update_fields, "w", "val", "true")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def postprocess_docx(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        items = {name: archive.read(name) for name in archive.namelist()}

    rels, footer_rid = add_footer_relationship(items["word/_rels/document.xml.rels"])
    items["word/_rels/document.xml.rels"] = rels
    items["[Content_Types].xml"] = add_footer_content_type(items["[Content_Types].xml"])
    items["word/styles.xml"] = style_document(items["word/styles.xml"])
    items["word/settings.xml"] = update_fields_on_open(items["word/settings.xml"])
    items["word/document.xml"] = style_document_xml(items["word/document.xml"], footer_rid)
    items["word/footer1.xml"] = footer_xml()

    temp_path = path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in items.items():
            archive.writestr(name, data)
    temp_path.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    run_pandoc(prepare_markdown(source), output)
    postprocess_docx(output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
