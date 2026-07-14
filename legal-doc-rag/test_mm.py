from app.processing.multimodal_pipeline import MultimodalPipeline
pipe = MultimodalPipeline()
chunks = pipe.process("D:/git/legal-doc-rag/data/labor_law.txt")
print("Chunks:", len(chunks))
for c in chunks[:2]:
    print(f"  Page {c.page_number}: {len(c.text)} chars, {len(c.images)} images")
print("Multimodal OK")
