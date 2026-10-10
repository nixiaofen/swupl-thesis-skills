#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cnki2xz.py —— 把中国知网（CNKI）导出的题录，批量转为西南政法大学硕士学位论文格式。

用法：
    python cnki2xz.py 题录.txt                    # 默认同时输出脚注版与参考文献版
    python cnki2xz.py 题录.txt --mode footnote    # 只要脚注
    python cnki2xz.py 题录.txt --mode ref         # 只要参考文献
    python cnki2xz.py 题录.txt --out 结果.md
    type 题录.txt | python cnki2xz.py -           # 从 stdin 读

规范依据：《西南政法大学硕士学位论文格式要求》（2023-03-01）
    · 七(二)2(2) 期刊文章：作者："篇名"，《期刊名》，期刊号，页码。
    · 七(二)1(1) 中文专著：作者：《专著名》，出版地：出版者，出版年，页码。
    · 七(二)2(5) 学位论文：作者："论文题目"，所在学校博（硕）士论文，毕业年份，页码。
    · 八(一)    参考文献：各类格式除毋需列明页码外，其余与注释相同。
    · 七(一)3   作者少于3人全部写出，3人以上只列前3人，后加"等"。

⚠️ 本脚本只负责"文本内容"的转换。字体（宋体小五 / Times New Roman）、
   上标序号、引号字形，一律由 Word 样式决定，不在本脚本职责范围内。
"""

import argparse
import re
import sys

# ---------------------------------------------------------------- 工具函数

DASH = re.compile(r'[\u2010\u2013\u2014\u2015\-]{1,2}')  # 各种连字符归一为 -

# 学位论文默认按"硕士论文"输出（知网 [D] 不区分硕博），可用 --degree 博 切换
DEGREE = '硕'


def norm_pages(p):
    """106-118 / 106–118 / 106—118 → 106-118"""
    if not p:
        return ''
    return DASH.sub('-', p.strip()).strip('-')


def fmt_pages(p):
    p = norm_pages(p)
    if not p:
        return ''
    return '第%s页' % p


def split_authors(s):
    """拆分作者；≥3 人只列前 3 人加"等"；间隔用全角逗号。"""
    if not s:
        return ''
    names = [x.strip() for x in re.split(r'[,，;；]', s) if x.strip()]
    if not names:
        return ''
    if len(names) > 3:
        names = names[:3] + ['等']
    return '，'.join(names)


def clean(s):
    return re.sub(r'\s+', ' ', (s or '')).strip() if s else ''


def quote_cn(s):
    return '\u201c%s\u201d' % s          # 中文双引号


def book_cn(s):
    return '\u300a%s\u300b' % s          # 书名号


# ---------------------------------------------------------------- 知网引文格式 / GB-T 7714（单行）

CNKI_RE = re.compile(
    r'^(?P<authors>[^.\[]+?)\.\s*'                 # 作者（到第一个句点为止）
    r'(?P<title>.+?)\s*'                           # 篇名
    r'\[(?P<type>[A-Za-z]{1,2})\]\s*\.\s*'         # 文献类型标识
    r'(?P<src>[^,]+?)\s*,\s*'                      # 期刊名 / 出版地:出版社 / 学校
    r'(?P<year>(?:19|20)\d{2})'                    # 年份
    r'(?:\s*,\s*(?P<vol>\d+)\s*)?'                 # 卷号（可选）
    r'(?:,?\s*\((?P<issue>[^)]+)\)\s*)?'           # 期号（可选）
    r'(?:\s*:\s*(?P<pages>[\d\u2010\u2013\u2014\u2015\-]+))?'  # 页码（可选）
    r'\s*\.?\s*$'
)


def parse_cnki(line):
    m = CNKI_RE.match(line.strip())
    if not m:
        return None
    d = m.groupdict()
    src = clean(d['src'])
    rec = {
        'type': d['type'].upper(),
        'authors': d['authors'],
        'title': clean(d['title']),
        'year': d['year'],
        'issue': clean(d['issue']),
        'pages': norm_pages(d['pages']),
        'journal': '', 'place': '', 'publisher': '', 'school': '',
    }
    if rec['type'] == 'J':
        rec['journal'] = src
    elif rec['type'] == 'D':
        rec['school'] = src
    else:                                  # M / C 等：出版地:出版者
        if ':' in src or '：' in src:
            a, b = re.split(r'[:：]', src, maxsplit=1)
            rec['place'], rec['publisher'] = clean(a), clean(b)
        else:
            rec['publisher'] = src
    return rec


# ---------------------------------------------------------------- RefWorks / EndNote RIS / EndNote 旧式

TAG_KEYS = {
    'authors': ('A1', 'AU', '%A'),
    'title':   ('T1', 'TI', 'ST', '%T'),
    'journal': ('JF', 'JO', 'T2', 'J2', '%J', '%B'),
    'year':    ('YR', 'PY', 'Y1', '%D'),
    'volume':  ('VO', 'VL', '%V'),
    'issue':   ('IS', '%N'),
    'sp':      ('SP', '%P'),
    'ep':      ('OP', 'EP'),
    'type':    ('RT', 'TY', '%0'),
}


def parse_tagged(block):
    """把 RefWorks(A1 )/RIS(AU  - )/EndNote旧式(%A ) 记录块解析成字段。"""
    tags = {}
    for ln in block.splitlines():
        ln = ln.rstrip()
        if not ln.strip():
            continue
        m = re.match(r'^(%?[A-Z0-9]{1,2})\s*(?:-\s*)?(.*)$', ln)
        if not m:
            continue
        k, v = m.group(1), clean(m.group(2))
        tags.setdefault(k, [])
        tags[k].append(v)

    def get(*keys):
        for k in keys:
            if k in tags and tags[k]:
                return tags[k]
        return []

    out = {
        'type': '', 'authors': '', 'title': '', 'journal': '',
        'year': '', 'issue': '', 'pages': '', 'place': '', 'publisher': '', 'school': '',
    }
    t = ' '.join(get(*TAG_KEYS['type'])).upper()
    if 'JOUR' in t or 'JOURNAL' in t:
        out['type'] = 'J'
    elif 'BOOK' in t or 'MONO' in t:
        out['type'] = 'M'
    elif 'THES' in t or 'DISS' in t or 'DOCTOR' in t or 'MASTER' in t:
        out['type'] = 'D'
    else:
        out['type'] = '?'

    out['authors'] = '，'.join(get(*TAG_KEYS['authors']))
    out['title'] = ' '.join(get(*TAG_KEYS['title']))
    out['journal'] = ' '.join(get(*TAG_KEYS['journal']))
    yr = ' '.join(get(*TAG_KEYS['year']))
    m = re.search(r'((?:19|20)\d{2})', yr)
    out['year'] = m.group(1) if m else ''
    out['issue'] = ' '.join(get(*TAG_KEYS['issue']))
    sp = ' '.join(get(*TAG_KEYS['sp']))
    ep = ' '.join(get(*TAG_KEYS['ep']))
    if sp and ep and sp != ep:
        out['pages'] = '%s-%s' % (sp, ep)
    else:
        out['pages'] = norm_pages(sp)
    if out['type'] == 'D':
        out['school'] = out['journal'] or ' '.join(tags.get('PB', []))
    return out


# ---------------------------------------------------------------- 输入切分与格式识别


def detect(text):
    if re.search(r'^\s*%[0A-Z]\s', text, re.M):          # EndNote 旧式 %A
        return 'endnote'
    if re.search(r'^\s*(?:TY|AU|TI)\s{0,2}-\s', text, re.M):  # RIS
        return 'endnote'
    if re.search(r'^\s*(?:RT|A1|TY)\s', text, re.M):      # RefWorks
        return 'endnote'
    return 'cnki'


def split_records(text, fmt):
    if fmt == 'endnote':
        return [b.strip() for b in re.split(r'\n\s*\n', text.strip()) if b.strip()]
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


# ---------------------------------------------------------------- 格式化输出


def to_footnote(r):
    """返回 (文本, 待人工确认的提示列表)"""
    warn = []
    who = split_authors(r['authors'])
    title = r['title']

    if r['type'] == 'J':
        s = '%s：%s，%s' % (who, quote_cn(title), book_cn(r['journal']))
        if r['year']:
            s += '，%s年' % r['year']
            if r['issue']:
                s += '第%s期' % r['issue']
            else:
                warn.append('缺期号，仅写到年份')
        else:
            warn.append('缺年份')
        p = fmt_pages(r['pages'])
        if p:
            s += '，%s' % p
        else:
            warn.append('缺页码（知网题录未给）')
        return s + '。', warn

    if r['type'] == 'M':
        s = '%s：%s' % (who, book_cn(title))
        tail = []
        if r['place']:
            tail.append(r['place'])
        if r['publisher']:
            tail.append(r['publisher'])
        if tail:
            s += '，%s' % '：'.join(tail) if r['place'] else '，%s' % tail[0]
        if r['year']:
            s += '，%s年' % r['year']
        p = fmt_pages(r['pages'])
        if p:
            s += '，%s' % p
        else:
            warn.append('专著缺页码，正文引用时须补具体页码')
        return s + '。', warn

    if r['type'] == 'D':
        s = '%s：%s，%s%s士论文' % (who, quote_cn(title), r['school'] or '（学校缺失）', DEGREE)
        if r['year']:
            s += '，%s年' % r['year']
        warn.append('学位论文须人工确认"硕士论文"还是"博士论文"，并补页码')
        return s + '。', warn

    return None, ['暂不支持的文献类型 [%s]，请手工转换：%s' % (r['type'], title)]


def to_ref(r):
    """参考文献 = 脚注去掉页码"""
    s, warn = to_footnote(r)
    if s is None:
        return s, warn
    # 去掉「，第X页」，保留结尾句号
    s2 = re.sub(r'，第[^，。]*页(?=。$)', '', s)
    return s2, [w for w in warn if '页码' not in w]


# ---------------------------------------------------------------- 主流程


def main():
    ap = argparse.ArgumentParser(description='知网题录 → 西南政法大学论文格式')
    ap.add_argument('input', help='题录文本文件路径，- 表示 stdin')
    ap.add_argument('--mode', choices=['footnote', 'ref', 'both'], default='both')
    ap.add_argument('--out', help='结果写入文件（默认打印到 stdout）')
    ap.add_argument('--degree', choices=['硕', '博'], default='硕',
                    help='学位论文的默认学位层次（知网题录不区分硕博），默认"硕"')
    args = ap.parse_args()

    global DEGREE
    DEGREE = args.degree

    text = sys.stdin.read() if args.input == '-' else open(args.input, encoding='utf-8').read()
    fmt = detect(text)
    recs_raw = split_records(text, fmt)

    footnotes, refs, warns = [], [], []
    for i, raw in enumerate(recs_raw, 1):
        r = parse_tagged(raw) if fmt == 'endnote' else parse_cnki(raw)
        if r is None:
            warns.append('[%d] 无法解析，请手工处理：%s' % (i, raw[:60]))
            continue
        f, w1 = to_footnote(r)
        b, w2 = to_ref(r)
        if f:
            footnotes.append(f)
        if b:
            refs.append(b)
        for w in dict.fromkeys(w1 + w2):
            warns.append('[%d] %s —— %s' % (i, r['title'][:28], w))

    out = []
    out.append('<!-- 识别到的输入格式：%s；共 %d 条 -->' % (fmt, len(footnotes)))
    if args.mode in ('footnote', 'both'):
        out.append('\n## 脚注\n')
        out.extend('%d. %s' % (i, s) for i, s in enumerate(footnotes, 1))
    if args.mode in ('ref', 'both'):
        out.append('\n## 参考文献（不列页码）\n')
        out.extend('%d. %s' % (i, s) for i, s in enumerate(refs, 1))
    if warns:
        out.append('\n## ⚠️ 需人工确认\n')
        out.extend('- ' + w for w in warns)

    res = '\n'.join(out)
    if args.out:
        open(args.out, 'w', encoding='utf-8').write(res)
        print('已写入 %s（%d 条）' % (args.out, len(footnotes)))
    else:
        print(res)


if __name__ == '__main__':
    main()
