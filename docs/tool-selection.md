# 文档解析工具选型

2026-10-23 检查 GitHub 候选项目。环境中 GitHub 搜索 API 请求返回 403，因此本次通过原生 Git 直接访问并检查已知候选项目，不声称完成了全站搜索。

| 项目 | 第一版用途/决定 |
|---|---|
| [pdfplumber](https://github.com/jsvine/pdfplumber) | 复用 `extract_text(layout=True)`、`find_tables()`、`to_image()`，处理 PDF 文字、候选表格、页面图像 |
| [python-docx](https://github.com/python-openxml/python-docx) | 复用 `iter_inner_content()`、表格单元格和图片关系，处理 Word 主体 |
| [openpyxl](https://openpyxl.readthedocs.io/) | 复用 `load_workbook()`，读取工作表、单元格、公式和缓存；使用官方发行包 |
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | 作为 pdfplumber 的页面渲染依赖，保留视觉证据 |
| [Docling](https://github.com/docling-project/docling) | 后续复杂 PDF/OCR 候选；统一格式和布局能力更强，但本地模型额外依赖及权重下载尚未验收 |
| [PyMuPDF4LLM](https://github.com/pymupdf/pymupdf4llm) | 检查时 main README 表示 4LLM 已迁入 PyMuPDF 2.x，不直接依赖变化中的仓库 HEAD |

检查的 GitHub HEAD：

- pdfplumber: `4c64b92d5caccd71c645e98e0fabb0c4dba7ff45`
- Docling: `36be1d247d6cc35bed2b815b64e1fd924e6f50ed`
- PyMuPDF4LLM: `d9b212b737dd27550401a2691a5bc1719b2fef2c`
- python-docx: `e45454602b53e8e572b179ccf1c91093ec9f4ed7`（远端查询）
- pypdfium2: `21fa91a05007e06d13c76c86f2fc39f6e9d2cc43`（远端查询）

实际运行版本固定在 `pyproject.toml`，并非上述 Git HEAD。通过依赖导入复用代码，不复制整个第三方仓库。自写部分仅负责格式转换、锚点、分块、查询与错误报告。直接依赖已固定版本，传递依赖暂未提供完整锁文件。

pdfplumber 与 Docling 的代码许可证为 MIT（已检查仓库）；Docling 模型权重另有许可证。各依赖及二进制组件的完整许可证以其发行包为准。本仓库不重分发模型权重。
