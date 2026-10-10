#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit.py —— 学位论文「完稿体检」：把靠人眼读十遍也看不见的问题用脚本扫出来。

用法：
    python audit.py --dir <论文目录> [--out 体检报告.md]
    python audit.py --dir . --refs 参考文献.md --pages 文献页码总表.csv

自动发现（在 --dir 下）：
    * 章节稿     02-章节草稿/第*章-*.md、定稿同步-*.md（自动排除 bak/试写/留档）
    * 摘要/结语  02-章节草稿/摘要*.md、结语*.md
    * 一致性清单 03-素材库/全文立场一致性清单.md
    * 页码总表   03-素材库/refs_pages.csv（可选，列：作者,篇名,刊物,起始页,结束页）

六项检查：
    1. 无源论断审计   —— "有学者主张…" 这类句子有没有挂注
    2. 注号完整性     —— 孤儿注 / 悬空引用 / 正文首现顺序
    3. 页码越界       —— 所引页码是否落在该文献起止页之内
    4. 引注格式体检   —— 篇名引号、期刊名后逗号、参考文献带页码、重复条目
    5. 立场一致性     —— 清单里未闭合的张力点
    6. 摘要/结语重复率 —— 6-gram 重叠比（结语复述摘要是最常见的败笔）

只出报告，不改正文。纯标准库，无第三方依赖。
"""

import argparse
import csv
import os
import re
import sys
from collections import OrderedDict

# ---------------------------------------------------------------- 通用

CJK = re.compile(r'[\u4e00-\u9fff]')
NOTE_MARK = re.compile(r'[〔\[【]\s*\d+\s*[〕\]】]')

SKIP_NAMES = ('bak', '试写', '留档', '留底', '草稿-旧', '完整稿', '.bak')


def is_skipped(path):
    b = os.path.basename(path)
    return any(k in b for k in SKIP_NAMES)


def read(p):
    return open(p, encoding='utf-8').read()


def strip_meta(body):
    """去掉前言(>)与标题(#)行，只留真正会被印出来的正文。"""
    return '\n'.join(l for l in body.splitlines()
                     if not (l.lstrip().startswith('>') or l.lstrip().startswith('#')))


def body_of(text):
    return text.split('## 【脚注】')[0]


def foot_of(text):
    return text.split('## 【脚注】')[1] if '## 【脚注】' in text else ''


def grams(t, n=6):
    t = ''.join(CJK.findall(t))
    return set(t[i:i + n] for i in range(len(t) - n + 1))


# ---------------------------------------------------------------- 1. 无源论断审计

ATTRIB = re.compile(
    r'(有学者|有观点|有研究|有意见|有论者|论者|有判决|有法院|学界(?:多|一般)?(?:认为|主张)|'
    r'通说|多数学者|部分学者|既有研究)[^。！？；\n]{0,220}[。！？；]'
)


def check_attribution(files):
    """⚠️ 关键：中文论文常把注号放在句号【之后】，
    只取到句号为止会把大量正常句子误判为无源，故窗口须跨过句末再多看一段。"""
    bad, skipped = [], []
    for f in files:
        body = strip_meta(body_of(read(f)))
        # 若全文压根没有注号标记（脚注被切到别的文件、或尚未挂注），
        # 逐句判"无源"只会 100% 误报——跳过并单列说明。
        if not NOTE_MARK.search(body):
            skipped.append(os.path.basename(f))
            continue
        # 段落级判定：中文论文的注号常落在句末之后甚至下一句，
        # 逐句判必然误报；一个段落里只要出现过注号，就认为该段已挂注。
        pos = 0
        for para in re.split(r'\n\s*\n', body):
            ln0 = body[:pos].count('\n') + 1
            pos += len(para) + 1
            if ATTRIB.search(para) and not NOTE_MARK.search(para):
                first = ATTRIB.search(para).group(0).strip()[:70]
                bad.append((os.path.basename(f), ln0, first))
    return bad, skipped


# ---------------------------------------------------------------- 2. 注号完整性


def check_notes(files):
    out = []
    for f in files:
        t = read(f)
        if '## 【脚注】' not in t:
            continue
        b = strip_meta(body_of(t))
        cited, seq = set(), []
        for m in re.finditer(r'[〔\[]\s*(\d+)\s*[〕\]]', b):
            n = int(m.group(1))
            cited.add(n)
            if n not in seq:
                seq.append(n)
        defined = OrderedDict()
        for m in re.finditer(r'^\s*[〔\[]\s*(\d+)\s*[〕\]]', foot_of(t), re.M):
            defined[int(m.group(1))] = True
        defs = list(defined.keys())
        orphans = sorted(set(defs) - cited)
        dangling = sorted(cited - set(defs))
        inorder = seq == sorted(seq) and seq == list(range(1, len(seq) + 1))
        if orphans or dangling or not inorder:
            out.append((os.path.basename(f), orphans, dangling, seq, defs))
    return out


# ---------------------------------------------------------------- 3. 页码越界


def load_pages(csv_path):
    tbl = {}
    if not csv_path or not os.path.exists(csv_path):
        return None
    with open(csv_path, encoding='utf-8-sig') as fh:
        for row in csv.DictReader(fh):
            key = (row.get('篇名') or '').strip()
            if not key:
                continue
            try:
                tbl[key] = (int(row['起始页']), int(row['结束页']))
            except (KeyError, ValueError, TypeError):
                continue
    return tbl or None


PAGE_CITE = re.compile(r'第\s*(\d+)(?:\s*[-—–]\s*(\d+))?\s*页')


def check_pages(files, tbl):
    if not tbl:
        return None
    bad = []
    for f in files:
        foot = foot_of(read(f))
        for line in foot.splitlines():
            for title, (lo, hi) in tbl.items():
                if title and title in line:
                    for m in PAGE_CITE.finditer(line):
                        a = int(m.group(1))
                        b = int(m.group(2)) if m.group(2) else a
                        if a < lo or b > hi:
                            bad.append((os.path.basename(f), title, '%s-%s' % (a, b),
                                        '%d-%d' % (lo, hi), line[:60]))
    return bad


# ---------------------------------------------------------------- 4. 引注格式体检

BAD_QUOTE = re.compile(r'：\s*\u300a[^\u300b]+\u300b[^\n]*\u300a')   # 冒号后紧跟书名号且后面还有书名号 → 篇名疑似用了书名号
NO_COMMA = re.compile(r'\u300b\s*(?:19|20)\d{2}年')                  # 《刊名》后直接接年份 → 缺逗号
REF_PAGE = PAGE_CITE


def check_format(files, refs_file):
    issues = []

    def scan(lines, tag, filepath, is_ref):
        seen = {}
        for i, ln in enumerate(lines, 1):
            s = ln.strip()
            if not s or s.startswith('#') or s.startswith('>'):
                continue
            if is_ref and REF_PAGE.search(s):
                issues.append((tag, filepath, i, '参考文献条目不应列页码', s[:60]))
            if BAD_QUOTE.search(s):
                issues.append((tag, filepath, i, '篇名疑似误用书名号（期刊篇名应用“ ”）', s[:60]))
            if NO_COMMA.search(s):
                issues.append((tag, filepath, i, '《期刊名》后缺逗号', s[:60]))
            if not s.endswith('。'):
                issues.append((tag, filepath, i, '条目末尾缺句号', s[:60]))
            head = s.split('：')[0]
            n = len([x for x in re.split(r'[，,、;；]', head) if x.strip()])
            if n >= 3 and '等' not in head:
                issues.append((tag, filepath, i, '作者 %d 人，应列前 3 人加“等”' % n, s[:60]))
            key = re.sub(r'\s+', '', s)
            if key in seen:
                issues.append((tag, filepath, i, '与第 %d 条重复' % seen[key], s[:60]))
            else:
                seen[key] = i

    for f in files:
        scan(foot_of(read(f)).splitlines(), '脚注', os.path.basename(f), False)
    if refs_file and os.path.exists(refs_file):
        scan(read(refs_file).splitlines(), '参考文献', os.path.basename(refs_file), True)
    return issues


# ---------------------------------------------------------------- 5. 立场一致性


def check_consistency(listfile):
    if not listfile or not os.path.exists(listfile):
        return None
    t = read(listfile)
    # 只统计形如「张力 N：」的登记项，避免把章节标题、表格行一并算进来造成噪音
    ids = sorted({int(x) for x in re.findall(r'张力\s*(\d+)\s*[：:]', t)})
    pending = [l.strip() for l in t.splitlines()
               if '⚠️' in l and ('待' in l or '须由' in l or '未' in l)
               and not l.lstrip().startswith(('#', '|', '>'))]
    return ids, pending


# ---------------------------------------------------------------- 6. 摘要/结语重复率


def overlap(a, b):
    if not a or not b:
        return None
    g1, g2 = grams(a), grams(b)
    if not g1 or not g2:
        return None
    return len(g1 & g2) / len(g2) * 100


# ---------------------------------------------------------------- 主流程


def find_one(d, *pats):
    import glob
    for pat in pats:
        for p in sorted(glob.glob(os.path.join(d, pat))):
            if not is_skipped(p):
                return p
    return None


def main():
    ap = argparse.ArgumentParser(description='学位论文完稿体检')
    ap.add_argument('--dir', default='.', help='论文项目根目录')
    ap.add_argument('--refs', help='参考文献列表文件（每行一条）')
    ap.add_argument('--pages', help='文献页码总表 CSV：作者,篇名,刊物,起始页,结束页')
    ap.add_argument('--abstract', help='摘要文件')
    ap.add_argument('--conclusion', help='结语文件')
    ap.add_argument('--intro', help='引言文件（用于查"引言是否与摘要雷同"）')
    ap.add_argument('--list', help='立场一致性清单')
    ap.add_argument('--out', help='报告写入文件')
    args = ap.parse_args()

    d = args.dir
    import glob
    chaps = [p for p in glob.glob(os.path.join(d, '02-章节草稿', '*.md'))
             if not is_skipped(p) and (os.path.basename(p).startswith('第')
                                       or os.path.basename(p).startswith('定稿同步'))]
    chaps.sort()

    abs_f = args.abstract or find_one(d, '02-章节草稿/摘要*.md')
    con_f = args.conclusion or find_one(d, '02-章节草稿/结语*.md')
    intro_f = args.intro or find_one(d, '02-章节草稿/定稿同步*引言*.md')
    list_f = args.list or find_one(d, '03-素材库/全文立场一致性清单.md')
    pages_f = args.pages or os.path.join(d, '03-素材库', 'refs_pages.csv')

    R = []
    R.append('# 论文完稿体检报告\n')
    R.append('扫描章节 %d 个：%s\n' % (len(chaps), '、'.join(os.path.basename(x) for x in chaps)))

    # 1
    bad, skipped = check_attribution(chaps)
    R.append('\n## 1. 无源论断审计\n')
    if bad:
        R.append('**⚠️ %d 处转述句没有挂注——须回原文确认"人是谁、说过什么"，确认不了就改成本文自己的论断。**\n' % len(bad))
        for f, ln, s in bad:
            R.append('- `%s` 第 %d 行：%s' % (f, ln, s))
    else:
        R.append('✅ 未发现无源论断。')
    if skipped:
        R.append('\n⏭ 以下文件**正文内没有任何注号标记**（脚注可能存放在别的文件），已跳过：%s'
                 % '、'.join('`%s`' % x for x in skipped))

    # 2
    notes = check_notes(chaps)
    R.append('\n## 2. 注号完整性\n')
    if notes:
        for f, orphans, dangling, seq, defs in notes:
            R.append('- `%s`' % f)
            if orphans:
                R.append('  - ⚠️ **孤儿注**（脚注列了、正文从不引用）：%s' % orphans)
            if dangling:
                R.append('  - ⚠️ **悬空引用**（正文引了、无对应脚注）：%s' % dangling)
            if seq != sorted(seq):
                R.append('  - ⚠️ 正文首现顺序非递增：%s' % seq)
            elif seq != list(range(1, len(seq) + 1)):
                R.append('  - ⚠️ 正文首现编号不连续（应为 1..%d）：%s' % (len(seq), seq))
    else:
        R.append('✅ 各章注号自洽。')

    # 3
    tbl = load_pages(pages_f)
    R.append('\n## 3. 页码越界检查\n')
    pg = check_pages(chaps, tbl)
    if tbl is None:
        R.append('⏭ 跳过：未提供 `%s`（列：作者,篇名,刊物,起始页,结束页）。' % os.path.basename(pages_f))
        R.append('   建好这张表才能真正拦住"第63页"这类越界错误。')
    elif pg:
        R.append('**⚠️ %d 处页码超出该文献起止页：**\n' % len(pg))
        for f, t, cited, rng, line in pg:
            R.append('- `%s` 《%s》引第 %s 页，实际区间 %s —— %s' % (f, t, cited, rng, line))
    else:
        R.append('✅ 所引页码均在起止页之内。')

    # 4
    R.append('\n## 4. 引注格式体检\n')
    fm = check_format(chaps, args.refs)
    if fm:
        R.append('**⚠️ %d 处：**\n' % len(fm))
        for tag, f, i, why, s in fm:
            R.append('- [%s] `%s` 第 %d 行：%s —— %s' % (tag, f, i, why, s))
    else:
        R.append('✅ 未发现格式问题。')
    if not args.refs:
        R.append('\n（未指定 `--refs`，参考文献列表未纳入检查。）')

    # 5
    R.append('\n## 5. 立场一致性\n')
    op = check_consistency(list_f)
    if op is None:
        R.append('⏭ 跳过：未找到立场一致性清单。')
    else:
        ids, pending = op
        if ids:
            R.append('- 清单已登记张力点 **%d** 个（编号 %s）——**写下一章前须逐条读过**，'
                     '确认新写的论断不与既有立场打架。' % (len(ids), '、'.join(map(str, ids))))
        else:
            R.append('- 清单中未登记张力点。')
        if pending:
            R.append('\n**⚠️ %d 项含"待/须由/未"字样的悬空事项：**\n' % len(pending))
            for l in pending[:12]:
                R.append('- %s' % l[:110])

    # 6
    R.append('\n## 6. 摘要 / 结语 / 引言 重复率\n')
    a = read(abs_f) if abs_f else ''
    c = read(con_f) if con_f else ''
    i_ = read(intro_f) if intro_f else ''
    r1 = overlap(c, a)
    r2 = overlap(i_, a)
    if r1 is None:
        R.append('⏭ 跳过：未找到摘要或结语文件。')
    else:
        R.append('- **结语 vs 摘要**：%.1f%% %s' % (r1, '⚠️ 过高——结语在复述摘要' if r1 > 20 else '✅'))
    if r2 is not None:
        R.append('- **引言 vs 摘要**：%.1f%% %s' % (r2, '⚠️ 过高——规范明令"引言不要与内容摘要雷同"' if r2 > 15 else '✅'))

    R.append('\n---\n\n> ⚠️ 本脚本只做**机械可判定**的检查。观点是否成立、论证是否充分，'
             '仍需人工通读；脚本查不出"看起来很对其实是错的"。')

    res = '\n'.join(R)
    if args.out:
        open(args.out, 'w', encoding='utf-8').write(res)
        print('已写入 %s' % args.out)
    else:
        print(res)


if __name__ == '__main__':
    main()
