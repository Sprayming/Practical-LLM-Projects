import os

path = "D:/git/rideops-ai/frontend/index.html"
with open(path, "r", encoding="utf-8") as f:
    html = f.read()

# 找到第一个card
card_start = html.find('<div class="card">')
# 找第二个card (hidden)
card_end = html.find('<div class="card"', card_start + 1)

new_card = """<div class="card">
    <h2>📤 上传数据</h2>
    <div class="upload-zone" id="uploadZone" onclick="document.getElementById('fileInput').click()">
      <div class="icon">📂</div>
      <div class="text">点击选择 CSV / Excel 文件</div>
    </div>

    <div id="uploadProgress" style="display:none; margin-top:12px">
      <div style="font-size:12px;color:#6b7280;margin-bottom:4px" id="progressText">准备上传...</div>
      <div style="width:100%;height:8px;background:#e5e7eb;border-radius:4px;overflow:hidden">
        <div id="progressFill" style="width:0%;height:100%;background:linear-gradient(90deg,#4f6ef7,#10b981);border-radius:4px;transition:width 0.3s"></div>
      </div>
    </div>

    <input type="file" id="fileInput" accept=".csv,.xlsx" style="display:none">
    <div id="uploadInfo"></div>
</div>"""

html = html[:card_start] + new_card + html[card_end:]

with open(path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"上传卡已重写: {card_start}-{card_end}, 总长度={len(html)}")
