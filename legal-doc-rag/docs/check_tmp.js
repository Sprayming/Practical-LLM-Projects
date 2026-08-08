
const scenes = [...document.querySelectorAll('.scene')];
const capEl = document.querySelector('#caption span');
const sceneNames = ['标题','MVC 三层','上传入库','查询问答','调用关系','关键考点'];

const CAP = {
  0:{_: '欢迎看 legal-doc-rag 架构速览（含真实源码版）。右侧面板会把讲解到的每个函数，原样贴出真实源码。我会把抽象数据流对到具体函数，最后给你一棵树看文件间调用关系。'},
  1:{_: '项目本质是 MVC：View=API 返回的 JSON；Controller=app/api 下各路由，只收请求、做鉴权、调服务；Service=retrieval/processing/memory/security/tenant；Model=Chroma、SQLite、uploads、cache、memory_db。关键：每个 Model 按 tenant_id 子目录物理隔离。'},
  2:[
    '第1步：客户端 POST /api/documents/upload，由 documents.py:20 的 upload_document() 接收。右侧看它怎么拿 tenant_id、安全落盘、切块、向量化、persist。',
    '第2步：FastAPI 的 Depends(require_user) 触发 auth.py:79，内部 get_user_from_token() 解 JWT 取出 tenant_id。右侧是它的真实实现。',
    '第3步（红=安全把关）：security/middleware.py:114 get_safe_upload_path() 调 sanitize_filename()+is_safe_path()，把文件写到 uploads/{tenant}/，防 ../ 穿越。右侧是安全三件套源码。',
    '第4步：processing/multimodal_pipeline.py:29 MultimodalPipeline.process() 调 pdf_extractor + OCREngine + 文本分块器，把 文本+OCR+图片描述 合并切 500 字块。右侧看 process/_process_pdf。',
    '第5步：retrieval/embedder_factory.py:35 create_embedder() 返回 DirectEmbed，调 /embeddings API 把每个 chunk 转成向量，并按 index 排序保证顺序。右侧看源码。',
    '第6步（绿=落盘）：Chroma.from_texts(persist_directory=chroma_db/{tenant}).persist() 把向量索引写入该租户目录。右侧是 persist 那几行。',
    '第7步：upload_document() return {success, chunks, tenant_id}，上传完成。右侧是 return 代码。'
  ],
  3:[
    '第1步：用户提问，chat.py:179 chat() 由 Depends(require_user) 拿到 tenant_id。右侧看入口如何判空库、改写查询。',
    '第2步：chat.py:162 _build_pipeline() 按 tenant 载入 Chroma，并实例化 QueryRewriter / QueryCache / CitationTracker。右侧看它怎么重建向量库。',
    '第3步：query_rewriter.py:29 QueryRewriter.rewrite() 调 LLM 把问题改写成更利于检索的形式，失败回退原查询。右侧看 rewrite 实现。',
    '第4步：hybrid_retriever.py:238 HybridRetriever.retrieve() 内部跑稠密(Chroma)+稀疏(BM25)+RRF 融合。右侧看 retrieve 与 _dense_search。',
    '第5步（橙=精度关键）：hybrid_retriever.py:42 Reranker.rerank() 用 BGE Cross-Encoder 对候选精排，失败优雅降级。右侧看 rerank。',
    '第6步：chat.py:85 call_llm()(httpx 调 DeepSeek) + citation.py:55 CitationTracker.format_context() 拼出带 [N] 引用的上下文。右侧看 format_context。',
    '第7步：chat() return {answer, citations:[...]}，每条答案都能溯源到原文。右侧看 return 与缓存/记忆写入。'
  ],
  4:{_: '这就是真实的文件间调用关系：app/main.py 用 include_router 装配 9 个路由；API 路由是入口，require_user 统一鉴权，业务函数分散在 retrieval / processing / memory / security / tenant，最终落到 Chroma / SQLite / 磁盘。把这棵树记住，数据流就和具体函数对上号了。'},
  5:{_: '两个最常考点：① 租户隔离 = 根目录 + tenant_id 拼子目录，安全靠 get_safe_upload_path()(middleware.py:114) 清洗 + is_safe_path()( :102) 防 ../ 穿越；② hybrid+reranker 而非纯语义 —— 法律术语要精确匹配避免漏检，向量找语义相似，BGE 精排提精度。记住这两点，架构就吃透了。'}
};

let si = 0, stepIdx = -1, playing = false, started = false, elapsed = 0, fallbackTimer = null;
const audio = new Audio();
audio.preload = 'auto';

const prog = document.getElementById('progress');
scenes.forEach(()=>{const d=document.createElement('div');d.className='dot';d.onclick=()=>gotoScene(scenes.indexOf(d.__s), true);prog.appendChild(d);});
[...prog.children].forEach((d,i)=>d.__s=scenes[i]);

function setDots(){document.querySelectorAll('.dot').forEach((d,i)=>d.classList.toggle('on',i===si));}
function setName(){document.getElementById('sceneName').textContent=(si+1)+'/'+scenes.length+' · '+sceneNames[si];}

function showCaption(text){capEl.textContent=text;capEl.classList.remove('show');void capEl.offsetWidth;capEl.classList.add('show');}
function renderCaption(){
  const c=CAP[si];
  if(Array.isArray(c)) showCaption(c[Math.max(0,stepIdx)]||c[0]);
  else showCaption(c._);
}

// 实时源码面板：根据当前 (幕, 步) 从 #codeStore 取出真实代码
const CODE_MAP = {
  2:['2-0','2-1','2-2','2-3','2-4','2-5','2-6'],
  3:['3-0','3-1','3-2','3-3','3-4','3-5','3-6']
};
function renderCode(){
  const cp = scenes[si]?.querySelector('.codepanel');
  if(!cp) return;                       // 只有 2/3 幕有面板
  const head = cp.querySelector('.cp-head');
  const pre  = cp.querySelector('.cp-code');
  const keys = CODE_MAP[si];
  if(!keys) return;
  const key = keys[Math.max(0, stepIdx)] || keys[0];
  const el = document.getElementById('code-'+key);
  if(el){
    head.querySelector('.file').textContent = el.dataset.file;
    head.querySelector('.fn').textContent   = el.dataset.fn;
    pre.textContent = el.textContent;
    pre.scrollTop = 0;
  }
}

function highlightStep(i){
  const steps=scenes[si].querySelectorAll('.step');
  steps.forEach((s,j)=>{ s.classList.remove('current'); s.classList.toggle('done', j<i); });
  if(steps[i]) steps[i].classList.add('current');
  renderCode();                          // 每步同步刷新源码面板
}
function updatePlayBtn(){document.getElementById('playBtn').textContent = playing ? '⏸ 暂停' : '▶ 播放(带声)';}
function pause(){ playing=false; updatePlayBtn(); audio.pause(); }

function gotoScene(i, autoplay){
  scenes[si]?.classList.remove('active');
  si=Math.max(0,Math.min(scenes.length-1,i));
  scenes[si].classList.add('active');
  const steps=scenes[si].querySelectorAll('.step');
  steps.forEach(s=>{s.classList.remove('current');s.classList.remove('done');});
  stepIdx=steps.length?0:-1;
  if(steps.length) steps[0].classList.add('current');
  setDots();setName();renderCaption();renderCode();
  if(autoplay) startSceneAudio();
}

// 每幕/每步对应的中文旁白音频（与 CAP 讲解词一一对应）
const AUDIO = {
 0:['audio/scene0.mp3'],
 1:['audio/scene1.mp3'],
 2:['audio/scene2_0.mp3','audio/scene2_1.mp3','audio/scene2_2.mp3','audio/scene2_3.mp3','audio/scene2_4.mp3','audio/scene2_5.mp3','audio/scene2_6.mp3'],
 3:['audio/scene3_0.mp3','audio/scene3_1.mp3','audio/scene3_2.mp3','audio/scene3_3.mp3','audio/scene3_4.mp3','audio/scene3_5.mp3','audio/scene3_6.mp3'],
 4:['audio/scene4.mp3'],
 5:['audio/scene5.mp3']
};

function startSceneAudio(){
  const clips = AUDIO[si];
  started = true;
  playing = true; updatePlayBtn();
  if(!clips || !clips.length){ return; }
  if(clips.length===1){
    audio.src=clips[0]; audio.play().catch(()=>{});
  } else {
    stepIdx=0; highlightStep(0); renderCaption();
    audio.src=clips[0]; audio.play().catch(()=>{});
  }
}
function onClipEnded(){
  if(!playing) return;
  clearTimeout(fallbackTimer);
  const clips=AUDIO[si];
  const steps=scenes[si].querySelectorAll('.step');
  if(clips.length===1){ advanceSceneOrStop(); return; }
  if(stepIdx < steps.length-1){
    stepIdx++; highlightStep(stepIdx); renderCaption();
    audio.src=clips[stepIdx]; audio.play().catch(()=>{});
  } else { advanceSceneOrStop(); }
}
function advanceSceneOrStop(){
  if(si<scenes.length-1) gotoScene(si+1, true);
  else { playing=false; updatePlayBtn(); document.getElementById('playBtn').textContent='↺ 重播'; }
}
// 兜底：若 ended 事件因故没触发（如某些浏览器/解码问题），按音频时长+余量推进
audio.addEventListener('loadedmetadata', ()=>{
  if(playing){
    clearTimeout(fallbackTimer);
    const dur = isFinite(audio.duration) && audio.duration > 0 ? audio.duration : 6;
    fallbackTimer = setTimeout(()=>{ if(playing && !audio.ended) onClipEnded(); }, dur*1000 + 1200);
  }
});
audio.addEventListener('ended', onClipEnded);
audio.addEventListener('timeupdate', ()=>{ document.getElementById('time').textContent='0:'+String(Math.floor(audio.currentTime)).padStart(2,'0'); });

function togglePlay(){ if(playing) pause(); else startSceneAudio(); }

document.getElementById('playBtn').onclick = togglePlay;
document.getElementById('prevBtn').onclick=()=>{ const w=playing; pause(); gotoScene(si-1,false); if(w) startSceneAudio(); };
document.getElementById('nextBtn').onclick=()=>{ const w=playing; pause(); gotoScene(si+1,false); if(w) startSceneAudio(); };
document.getElementById('restartBtn').onclick=()=>{ elapsed=0; gotoScene(0,true); };
// 仅在「点击视频画面」（而非控制条）时作为首次启动手势，且与按钮互不冲突
document.getElementById('stage').addEventListener('click', ()=>{ if(!started) startSceneAudio(); });

// 初始化：只渲染第 0 幕 + 显示字幕，不在加载时自动播放（避免被浏览器拦截）
gotoScene(0, false);
updatePlayBtn();
