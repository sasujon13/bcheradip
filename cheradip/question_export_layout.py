"""The saved creator layout is authoritative for versioned exports.

Legacy API callers retain their top-level override behaviour. No content,
authentication, filename or format fields are accepted from a layout snapshot.
"""
from pathlib import Path
import hashlib
import struct
import uuid


LAYOUT_KEYS = {
    'exportLayoutVersion', 'pageSize', 'pageSizeCreative', 'pageSizeMcq',
    'pageOrientation', 'cqPageOrientation', 'mcqPageOrientation',
    'customPageWidthIn', 'customPageHeightIn',
    'customPageWidthInCreative', 'customPageHeightInCreative',
    'customPageWidthInMcq', 'customPageHeightInMcq',
    'marginTop', 'marginRight', 'marginBottom', 'marginLeft',
    'marginTopCreative', 'marginRightCreative', 'marginBottomCreative', 'marginLeftCreative',
    'marginTopMcq', 'marginRightMcq', 'marginBottomMcq', 'marginLeftMcq',
    'questionsPadding', 'questionsPaddingCreative', 'questionsPaddingMcq',
    'questionsGap', 'questionsGapCreative',
    'previewQuestionsFontPx', 'previewQuestionsFontPxCreative', 'previewQuestionsFontPxMcq',
    'previewQuestionsLineHeight', 'previewQuestionsLineHeightCreative', 'previewQuestionsLineHeightMcq',
    'previewHeaderLineHeight', 'previewHeaderLineHeightCreative', 'previewHeaderLineHeightMcq',
    'headerLineFontSizes', 'layoutColumns', 'layoutColumnsCreative',
    'layoutColumnGapPx', 'layoutColumnGapPxCreative', 'layoutColumnGapPxMcq',
    'showColumnDivider', 'showColumnDividerCreative', 'showColumnDividerMcq',
    'optionsColumns', 'optionsColumnsManualOverride', 'previewOptionsLayoutByQid',
    'pageSections', 'pageSectionsCreative', 'pageSectionsMcq',
    'sectionGapPx', 'sectionGapPxCreative', 'sectionGapPxMcq',
    'exportPreviewPagePlan', 'previewSerialByIndex', 'exportPreviewQuestionQids',
    'leadEmptyFirstPageActive', 'leadBindingItemIndexes',
}


def apply_export_layout_snapshot(raw_data, layout_settings=None):
    result = raw_data.copy() if isinstance(raw_data, dict) else {}
    layout = layout_settings if isinstance(layout_settings, dict) else result.get('layout_settings')
    if isinstance(layout, dict) and layout.get('exportLayoutVersion') == 1:
        result.update({key: layout[key] for key in LAYOUT_KEYS
                       if key in layout and layout[key] is not None})
    return result


def mcq_left_first_page_plan(plan):
    """MCQ headers span the page; migrate old right-first booklet plans without losing tails."""
    if not isinstance(plan, list):
        return plan
    pages = [dict(page) if isinstance(page, dict) else page for page in plan]
    mcq = [page for page in pages if isinstance(page, dict) and page.get('kind') == 'mcq']
    if any(page.get('leadEmpty') for page in mcq):
        ordered, tail, counts = [], [], []
        for page in mcq:
            columns = page.get('questionColumnIndexes') or []
            items = [i for column in columns if isinstance(column, list) for i in column]
            binding = page.get('leadBindingIndexes') or []
            ordered.extend(items)
            tail.extend(binding)
            counts.append(len(items) + len(binding))
        ordered.extend(tail)
        offset = 0
        for page, count in zip(mcq, counts):
            items = ordered[offset:offset + count]
            midpoint = (len(items) + 1) // 2
            page['questionColumnIndexes'] = [items[:midpoint], items[midpoint:]]
            offset += count
    for page in mcq:
        page['headerInFirstColumn'] = False
        page['leadEmpty'] = False
        page['leadBindingIndexes'] = []
    return pages


def _editable_font_embedding_allowed(data):
    """Honour the font's OS/2 embedding rights; do not embed restricted fonts."""
    try:
        count = struct.unpack_from('>H', data, 4)[0]
        for index in range(count):
            position = 12 + index * 16
            if data[position:position + 4] == b'OS/2':
                offset = struct.unpack_from('>I', data, position + 8)[0]
                flags = struct.unpack_from('>H', data, offset + 8)[0]
                return not (flags & (0x0002 | 0x0004 | 0x0200))
    except (struct.error, IndexError):
        pass
    return False


def embed_question_document_fonts(document, base_dir):
    """Embed the same redistributable text fonts used by the browser/PDF.

    Text and OMML remain native Word content. This prevents missing-font
    substitution, not differences between independent layout engines.
    """
    from lxml import etree
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.opc.packuri import PackURI
    from docx.opc.part import Part
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    root_dir = Path(base_dir)
    sources = [root_dir / 'fonts', root_dir / 'static/fonts', root_dir / 'static_src/fonts',
               root_dir / 'cheradip/fonts', root_dir.parent / 'fcheradip/src/assets/fonts']
    font_table = document.part.part_related_by(RT.FONT_TABLE)
    root = etree.fromstring(font_table.blob)
    embedded = []
    for family, prefix in [('Roboto', 'Roboto'), ('Noto Sans Bengali', 'NotoSansBengali')]:
        font = next((node for node in root if node.get(qn('w:name')) == family), None)
        if font is None:
            font = OxmlElement('w:font')
            font.set(qn('w:name'), family)
            root.append(font)
        for weight, tag in [('Regular', 'embedRegular'), ('Bold', 'embedBold')]:
            filename = f'{prefix}-{weight}.ttf'
            source = next((directory / filename for directory in sources
                           if (directory / filename).is_file()), None)
            if source is None:
                continue
            data = source.read_bytes()
            if not _editable_font_embedding_allowed(data):
                continue
            key = uuid.uuid5(uuid.NAMESPACE_URL, hashlib.sha256(data).hexdigest())
            mask = bytes.fromhex(key.hex)[::-1]
            obfuscated = bytearray(data)
            for i in range(min(32, len(obfuscated))):
                obfuscated[i] ^= mask[i % 16]
            part = Part(PackURI(f'/word/fonts/{prefix}-{weight}.odttf'),
                        'application/vnd.openxmlformats-officedocument.obfuscatedFont',
                        bytes(obfuscated), document.part.package)
            node = OxmlElement(f'w:{tag}')
            node.set(qn('r:id'), font_table.relate_to(part, RT.FONT))
            node.set(qn('w:fontKey'), '{' + str(key).upper() + '}')
            font.append(node)
            embedded.append(filename)
    font_table._blob = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
    if embedded:
        for name in ('embedTrueTypeFonts',):
            if document.settings.element.find(qn('w:' + name)) is None:
                document.settings.element.append(OxmlElement('w:' + name))
    return embedded
