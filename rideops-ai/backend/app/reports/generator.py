"""报告生成器"""

def generate_html_report(report: dict) -> str:
    """生成简易 HTML 报告"""
    kpi = report.get("kpi", {})
    anomalies = report.get("anomalies", [])

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>运营报告 {report.get("id", "")}</title>
<style>
body {{ font-family: sans-serif; max-width: 800px; margin: 20px auto; padding: 0 20px; }}
h1 {{ color: #1a1d2e; border-bottom: 2px solid #4f6ef7; }}
table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
th {{ background: #4f6ef7; color: white; }}
.anomaly {{ background: #fff3cd; }}
</style></head><body>
<h1>运营报告 {report.get("id", "")}</h1>
<h2>核心 KPI</h2>
<table><tr><th>指标</th><th>数值</th></tr>
"""
    for key, val in kpi.items():
        html += f"<tr><td>{key}</td><td>{val}</td></tr>"
    html += "</table>"

    if anomalies:
        html += "<h2>异常提醒</h2><table><tr><th>日期</th><th>指标</th><th>严重程度</th></tr>"
        for a in anomalies:
            cls = ' class="anomaly"' if a.get("severity") == "high" else ""
            html += f"<tr{cls}><td>{a['date']}</td><td>{a['metric']}</td><td>{a['severity']}</td></tr>"
        html += "</table>"

    html += "<h2>周度模式</h2><table><tr><th>星期</th><th>订单量</th><th>收入</th></tr>"
    for day, data in report.get("weekly", {}).items():
        html += f"<tr><td>{day}</td><td>{data['orders']}</td><td>{data['revenue']}</td></tr>"
    html += "</table></body></html>"

    return html


def save_report(report: dict) -> str:
    """保存报告到本地"""
    import json
    from pathlib import Path
    from app.config import settings

    out_dir = Path(settings.report_output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rpt_id = report.get("id", "unknown")
    filepath = out_dir / f"{rpt_id}.json"
    filepath.write_text(json.dumps(report, ensure_ascii=False, default=str), encoding="utf-8")

    html_path = out_dir / f"{rpt_id}.html"
    html_path.write_text(generate_html_report(report), encoding="utf-8")

    return str(html_path)
