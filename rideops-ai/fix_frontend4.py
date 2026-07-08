import os

path = "D:/git/rideops-ai/frontend/index.html"
with open(path, "r", encoding="utf-8-sig") as f:
    html = f.read()

# uploadFile: 6715-7452
start = 6715
end = html.find("function loadSummary", start)  # 7452

old_func = html[start:end]
print(f"旧函数长度: {len(old_func)} 字符")
print(f"最后50字符: [{old_func[-50:]}]")

new_func = """function uploadFile(file) {
  if (!file) return;
  document.getElementById("uploadProgress").style.display = "block";
  document.getElementById("uploadInfo").textContent = "";
  document.getElementById("progressText").textContent = "上传中 0%";
  document.getElementById("progressFill").style.width = "0%";

  var form = new FormData();
  form.append("file", file);
  var xhr = new XMLHttpRequest();

  xhr.upload.onprogress = function(e) {
    if (e.lengthComputable) {
      var pct = Math.round(e.loaded / e.total * 100);
      document.getElementById("progressFill").style.width = pct + "%";
      var info = "上传中 " + pct + "%";
      if (file.size > 1048576) {
        info += " (" + (e.loaded / 1048576).toFixed(1) + "/" + (e.total / 1048576).toFixed(1) + " MB)";
      }
      document.getElementById("progressText").textContent = info;
    }
  };

  xhr.onload = function() {
    document.getElementById("uploadProgress").style.display = "none";
    if (xhr.status == 200) {
      var d = JSON.parse(xhr.responseText);
      var msg = d.message || "上传成功";
      document.getElementById("uploadInfo").textContent = msg;
      showMessage(msg, "success");
      if (d.type == "dataset" && d.sheets) {
        var keys = Object.keys(d.sheets).slice(0, 3);
        addChatMsg("ai", "加载了" + d.total_sheets + "个数据表，" + d.total_rows + "行。\\n你可以问：\\"" + keys[0] + "有什么数据？\\"");
      } else if (d.type == "orders") {
        addChatMsg("ai", "加载了" + d.orders_loaded + "条订单，可以提问了！");
      }
      loadSummary();
      document.getElementById("chatCard").classList.remove("hidden");
    } else {
      try {
        var d = JSON.parse(xhr.responseText);
        showMessage(d.detail || "上传失败", "error");
      } catch(e) {
        showMessage("上传失败 (" + xhr.status + ")", "error");
      }
    }
  };

  xhr.onerror = function() {
    document.getElementById("uploadProgress").style.display = "none";
    showMessage("网络错误，请确认服务已启动", "error");
  };

  xhr.open("POST", API + "/api/data/upload", true);
  xhr.send(form);
}

"""

html = html[:start] + new_func + html[end:]

with open(path, "w", encoding="utf-8") as f:
    f.write(html)

print("替换完成")
print(f"新函数长度: {len(new_func)} 字符")
