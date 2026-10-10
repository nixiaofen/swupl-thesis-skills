# 西政论文写作工具包（WorkBuddy Skills）

两个给**西南政法大学硕士学位论文**写作者用的 WorkBuddy 技能，也可作为独立脚本单独使用。

规范依据：《西南政法大学硕士学位论文格式要求》（2023-03-01）第七、八部分。

| 技能 | 干什么 | 什么时候用 |
|---|---|---|
| [`cnki-to-xizheng`](cnki-to-xizheng/) | 知网题录 → 西政脚注／参考文献格式，**批量**转换 | 补文献、整参考文献表 |
| [`thesis-final-audit`](thesis-final-audit/) | 论文「完稿体检」：无源论断、注号孤儿、页码越界、引注格式、立场冲突、摘要结语重复率 | 写完提交／答辩前 |

两者关系：**前者生产，后者质检**。体检报告里"格式不合规"的条目，回到 `cnki-to-xizheng` 重新生成即可。

## 安装

把需要的技能目录整个拷进 WorkBuddy 的技能目录：

```
Windows:  %USERPROFILE%\.workbuddy\skills\
macOS/Linux:  ~/.workbuddy/skills/
```

例如 `cnki-to-xizheng/` → `%USERPROFILE%\.workbuddy\skills\cnki-to-xizheng/`。

## 也可以不装 WorkBuddy，直接用脚本

两个脚本都**只用 Python 标准库**，无需任何第三方包。

```bash
# 1. 知网题录 → 西政格式
python cnki-to-xizheng/scripts/cnki2xz.py 题录.txt --mode both --out 结果.md

# 2. 完稿体检
python thesis-final-audit/scripts/audit.py --dir <论文目录> --out 体检报告.md
```

## 快速示例

输入（知网引文格式）：
```
吴芳.有限责任公司股东除名规则之检讨与完善[J].现代法学,2021,43(2):106-118.
```

输出·脚注：
```
吴芳：“有限责任公司股东除名规则之检讨与完善”，《现代法学》，2021年第2期，第106-118页。
```

输出·参考文献：
```
吴芳：“有限责任公司股东除名规则之检讨与完善”，《现代法学》，2021年第2期。
```

## 两条最容易踩的规范坑

1. **《期刊名》后面有逗号**（原文：作者："篇名"，《期刊名》，期刊号，页码）。
2. **篇名用中文引号“ ”，不是书名号**——书名号只给期刊名／专著名。

## 说明

- 脚本只做**机械可判定**的转换与检查，改不改正文由你决定，不自动改写文档。
- 字体（宋体小五／Times New Roman）、脚注上标、引号字形属 Word 排版职责，不在脚本范围内。
- 若你的学校不是西政，把 `cnki-to-xizheng/SKILL.md` 里的「规范依据」表换成你学校的要求即可，脚本逻辑不需改动。
