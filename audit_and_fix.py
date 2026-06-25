"""
WebIntel-Agent 自动审计脚本
扫描代码库中的潜在隐患并生成报告
"""

import os
import re
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
REPORT = []


def audit(severity: str, category: str, file: str, line: int, message: str):
    REPORT.append({
        "severity": severity,
        "category": category,
        "file": str(file),
        "line": line,
        "message": message,
    })


def scan_python_files():
    """扫描 Python 文件"""
    for py_file in PROJECT_ROOT.rglob("*.py"):
        if "venv" in str(py_file) or "__pycache__" in str(py_file):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
            lines = content.splitlines()
        except Exception:
            continue

        rel = py_file.relative_to(PROJECT_ROOT)

        for i, line in enumerate(lines, 1):
            # 1. 硬编码密钥
            if re.search(r'(api_key|secret|password|token)\s*=\s*["\'][^"\']{8,}', line, re.I):
                if "os.getenv" not in line and "settings." not in line and "Field(" not in line and "example" not in str(rel):
                    audit("CRITICAL", "security", rel, i, "疑似硬编码密钥/密码")

            # 2. 裸 except
            if re.match(r"\s*except\s*:", line):
                audit("HIGH", "error-handling", rel, i, "裸 except 会吞掉所有异常，应指定异常类型")

            # 3. 缺少 await 的异步调用
            if re.search(r"\bawait\s+", line) is None:
                if re.search(r"\b(fetch_|smart_fetch|analyze_content)\(", line):
                    audit("HIGH", "async", rel, i, "异步函数可能缺少 await")

            # 4. TODO/FIXME/HACK
            if re.search(r"#\s*(TODO|FIXME|HACK|XXX)", line, re.I):
                audit("LOW", "maintenance", rel, i, f"存在待办注释: {line.strip()}")

            # 5. print 调试语句（排除 logging）
            if re.match(r"\s*print\(", line) and "logging" not in content[:200]:
                audit("LOW", "cleanup", rel, i, "存在 print 调试语句，建议使用 logging")

            # 6. 未使用的导入（简单检测）
            if re.match(r"^import\s+(\w+)|^from\s+\S+\s+import\s+(\w+)", line):
                import_match = re.search(r"import\s+(\w+)", line)
                if import_match:
                    name = import_match.group(1)
                    # 检查是否在文件其他地方使用
                    rest = "\n".join(lines[i:])
                    if name not in rest and name != "__init__":
                        audit("MEDIUM", "unused-import", rel, i, f"导入 '{name}' 可能未使用")


def scan_frontend_files():
    """扫描前端文件"""
    for ext in ("*.html", "*.css", "*.js"):
        for f in PROJECT_ROOT.rglob(ext):
            if "venv" in str(f) or "node_modules" in str(f):
                continue

            try:
                content = f.read_text(encoding="utf-8")
                lines = content.splitlines()
            except Exception:
                continue

            rel = f.relative_to(PROJECT_ROOT)

            for i, line in enumerate(lines, 1):
                # 1. console.log
                if "console.log" in line:
                    audit("LOW", "cleanup", rel, i, "存在 console.log 调试语句")

                # 2. 内联样式
                if f.suffix == ".html" and 'style="' in line:
                    audit("LOW", "style", rel, i, "存在内联样式，建议使用 CSS 类")

                # 3. !important
                if f.suffix == ".css" and "!important" in line:
                    audit("MEDIUM", "css", rel, i, "使用了 !important，可能导致样式难以覆盖")

                # 4. 未加单位的 0（CSS 中 0px 等同于 0，但仅限 0）
                # 跳过

                # 5. JS eval
                if f.suffix == ".js" and re.search(r"\beval\(", line):
                    audit("CRITICAL", "security", rel, i, "使用了 eval()，存在安全风险")


def check_project_structure():
    """检查项目结构完整性"""
    required = [
        "requirements.txt",
        "README.md",
        "backend/main.py",
        "backend/config.py",
        "backend/models/schemas.py",
        "backend/core/fetcher.py",
        "backend/core/analyzer.py",
        "backend/api/routes.py",
        "frontend/index.html",
        "frontend/style.css",
        "frontend/app.js",
        "tests/test_main.py",
    ]
    for f in required:
        if not (PROJECT_ROOT / f).exists():
            audit("CRITICAL", "structure", "project", 0, f"缺失必要文件: {f}")


def check_dependencies():
    """检查依赖安全性"""
    req_file = PROJECT_ROOT / "requirements.txt"
    if not req_file.exists():
        audit("CRITICAL", "structure", "requirements.txt", 0, "缺失 requirements.txt")
        return

    content = req_file.read_text()
    # 检查是否有未锁定版本
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "==" not in line and ">=" not in line:
            audit("MEDIUM", "dependency", "requirements.txt", 0, f"依赖 '{line}' 未锁定版本")


def generate_report():
    """生成审计报告"""
    print("\n" + "=" * 60)
    print("  WebIntel-Agent 自动审计报告")
    print("=" * 60)

    if not REPORT:
        print("\n  ✅ 未发现任何问题！代码质量优秀。\n")
        return

    # 按严重程度排序
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    REPORT.sort(key=lambda x: severity_order.get(x["severity"], 99))

    stats = {}
    for r in REPORT:
        stats[r["severity"]] = stats.get(r["severity"], 0) + 1

    print(f"\n  发现 {len(REPORT)} 个问题:\n")
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        count = stats.get(sev, 0)
        if count > 0:
            icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵"}[sev]
            print(f"    {icon} {sev}: {count}")

    print("\n  详细列表:\n")
    for r in REPORT:
        icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵"}[r["severity"]]
        print(f"  {icon} [{r['category']}] {r['file']}:{r['line']}")
        print(f"     {r['message']}")
        print()

    # 写入 JSON 报告
    report_path = PROJECT_ROOT / "audit_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=2)
    print(f"  📄 详细报告已保存到: {report_path}\n")


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("\n🔍 开始审计...")
    check_project_structure()
    check_dependencies()
    scan_python_files()
    scan_frontend_files()
    generate_report()
