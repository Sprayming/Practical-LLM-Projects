# 📚 RAG 企业知识库 — 教学目录

这里是整套学习资料，和你的 `my_version` 结构对齐，方便逐文件对照。

## 目录结构

```
teaching/
├── code/               ← 参考代码（每行带中文注释）
│   ├── config.py       ← 与 my_version/app/config.py 对照
│   ├── models.py       ← 与 my_version/app/models.py 对照
│   ├── main.py         ← 应用入口
│   ├── ingestion/      ← 文档加载 + 分块管线
│   ├── retrieval/      ← 嵌入 + 向量检索
│   ├── generation/     ← DeepSeek 调用
│   └── api/            ← HTTP 接口
├── docs/
│   ├── 项目脉络与步骤.txt  ← 学习路线图
│   ├── 方案说明.txt        ← 方案对比说明
│   └── .env.example       ← 环境配置模板
└── frontend/
    └── index.html         ← 前端页面
```

## 对照学习法

1. 打开 `teaching/code/xxx.py` 读注释（理解每行作用）
2. **关掉它**
3. 打开 `my_version/app/xxx.py` 凭记忆写
4. 卡住了再回头看 `teaching/code/xxx.py`
5. 写完后对比差异
