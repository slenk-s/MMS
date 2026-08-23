"""
Excel 图片提取器 (v4.3 v25)
支持两种图片存储方式：
1. 传统浮动图片（openpyxl drawing 方式）
2. Excel 365 "放置在单元格中"（richData / vm 属性方式）

用法：
    from utils.excel_image_extractor import extract_all_images
    images = extract_all_images(file_path, ws)
    # images: {(row, col): bytes}
"""

import zipfile
# 安全修复：使用 defusedxml 替代 xml.etree.ElementTree，防御 XXE 攻击
# defusedxml 禁用外部实体解析，API 与 xml.etree.ElementTree 兼容
from defusedxml import ElementTree as ET
import re
from typing import Dict, Tuple

# ---------- Magic bytes → 扩展名 ----------
_IMAGE_SIGNATURES = [
    (b'\x89PNG\r\n\x1a\n', '.png'),
    (b'\x89PNG', '.png'),
    (b'\xff\xd8\xff', '.jpg'),
    (b'GIF87a', '.gif'),
    (b'GIF89a', '.gif'),
    (b'BM', '.bmp'),
]


def guess_image_ext(data: bytes) -> str:
    """通过 magic bytes 推断图片扩展名，失败返回 .png"""
    if data.startswith(b'RIFF') and len(data) > 12 and data[8:12] == b'WEBP':
        return '.webp'
    for sig, ext in _IMAGE_SIGNATURES:
        if data.startswith(sig):
            return ext
    return '.png'


def _col_letter_to_num(letters: str) -> int:
    """Excel 列字母转列号，如 'A'→1, 'F'→6, 'AA'→27"""
    result = 0
    for c in letters.upper():
        result = result * 26 + (ord(c) - ord('A') + 1)
    return result


def _parse_cell_ref(ref: str) -> Tuple[int, int]:
    """解析单元格坐标 'F2' → (row=2, col=6)"""
    match = re.match(r'^([A-Z]+)(\d+)$', ref, re.IGNORECASE)
    if match:
        return int(match.group(2)), _col_letter_to_num(match.group(1))
    return None, None


def extract_richdata_images(xlsx_path: str) -> Dict[Tuple[int, int], bytes]:
    """
    提取 Excel 365 "放置在单元格中" 的图片（richData 方式）。

    映射链:
        cell(vm) → metadata.xml(v) → richValueRel.xml[rId]
        → richValueRel.xml.rels[rId→media] → xl/media/*.png

    Returns:
        {(row, col): image_data_bytes}
    """
    images: Dict[Tuple[int, int], bytes] = {}

    with zipfile.ZipFile(xlsx_path, 'r') as zf:
        # 检测 richData 结构是否存在
        required = (
            'xl/worksheets/sheet1.xml',
            'xl/metadata.xml',
            'xl/richData/richValueRel.xml',
            'xl/richData/_rels/richValueRel.xml.rels',
        )
        if not all(f in zf.namelist() for f in required):
            return images

        # 1. sheet1.xml — 收集带 vm 属性的单元格
        vm_cells: Dict[Tuple[int, int], int] = {}
        sheet_tree = ET.fromstring(zf.read('xl/worksheets/sheet1.xml').decode('utf-8'))
        for cell in sheet_tree.iter():
            vm = cell.get('vm')
            ref = cell.get('r')
            if vm and ref:
                row, col = _parse_cell_ref(ref)
                if row is not None:
                    vm_cells[(row, col)] = int(vm)
        if not vm_cells:
            return images

        # 2. metadata.xml — vm(1-based) → richData 索引(v, 0-based)
        meta_tree = ET.fromstring(zf.read('xl/metadata.xml').decode('utf-8'))
        rc_values = []
        for rc in meta_tree.iter():
            if rc.get('t') == '1' and rc.get('v') is not None:
                rc_values.append(int(rc.get('v')))
        vm_to_rich_idx = {i + 1: v for i, v in enumerate(rc_values)}

        # 3. richValueRel.xml — richData 索引 → rId
        rich_rel_tree = ET.fromstring(zf.read('xl/richData/richValueRel.xml').decode('utf-8'))
        ns_r = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
        rids = [
            rel.get(f'{ns_r}id')
            for rel in rich_rel_tree.iter()
            if rel.get(f'{ns_r}id')
        ]

        # 4. richValueRel.xml.rels — rId → media 路径
        rels_tree = ET.fromstring(zf.read('xl/richData/_rels/richValueRel.xml.rels').decode('utf-8'))
        rId_to_media = {
            rel.get('Id'): rel.get('Target')
            for rel in rels_tree.iter()
            if rel.get('Id') and rel.get('Target')
        }

        # 5. 提取图片
        for (row, col), vm in vm_cells.items():
            rich_idx = vm_to_rich_idx.get(vm)
            if rich_idx is None or rich_idx < 0 or rich_idx >= len(rids):
                continue
            media_target = rId_to_media.get(rids[rich_idx])
            if not media_target:
                continue
            media_path = f'xl/{media_target.lstrip("../")}'
            try:
                images[(row, col)] = zf.read(media_path)
            except KeyError:
                pass

    return images


def _parse_anchor(anchor) -> Tuple[int, int]:
    """解析浮动图片锚点到 (row, col)，失败返回 (None, None)"""
    # openpyxl 不同版本的 anchor 结构
    if hasattr(anchor, '_from'):
        from_obj = anchor._from
        if hasattr(from_obj, 'col') and hasattr(from_obj, 'row'):
            return from_obj.row + 1, from_obj.col + 1
        if hasattr(from_obj, 'col_idx') and hasattr(from_obj, 'row_idx'):
            return from_obj.row_idx, from_obj.col_idx
    if hasattr(anchor, 'col') and hasattr(anchor, 'row'):
        return anchor.row + 1, anchor.col + 1

    # 备用：字符串解析
    match = re.search(r'([A-Z]+)(\d+)', str(anchor))
    if match:
        return int(match.group(2)), _col_letter_to_num(match.group(1))
    return None, None


def extract_floating_images(ws) -> Dict[Tuple[int, int], bytes]:
    """
    提取传统浮动图片（openpyxl ws._images 方式）。

    Returns:
        {(row, col): image_data_bytes}
    """
    images: Dict[Tuple[int, int], bytes] = {}
    for img in ws._images:
        try:
            img_data = img._data()
            if not img_data:
                continue
            row, col = _parse_anchor(img.anchor)
            if row and col:
                images[(row, col)] = img_data
        except Exception:
            continue
    return images


def extract_all_images(xlsx_path: str, ws=None) -> Dict[Tuple[int, int], bytes]:
    """
    统一入口：同时提取两种方式的图片。
    richData 方式优先（覆盖传统方式的同位置图片）。

    Args:
        xlsx_path: xlsx 文件路径
        ws: openpyxl worksheet 对象（用于提取浮动图片，可选）

    Returns:
        {(row, col): image_data_bytes}
    """
    images: Dict[Tuple[int, int], bytes] = {}

    # 方式1：传统浮动图片
    if ws is not None:
        images.update(extract_floating_images(ws))

    # 方式2：richData（优先，覆盖同位置）
    images.update(extract_richdata_images(xlsx_path))

    return images
