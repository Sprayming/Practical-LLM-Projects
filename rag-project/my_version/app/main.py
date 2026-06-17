"""
整个RAG项目的调度界面
1.创建fastAPI应用实例
2.配置“CORS”接口协议
3.注册路由，打通链路
4.启动chromaDB，初始化向量库
5.异常处理，当查询无果时，统一返回500
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware



@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期。
    """
    pass





# 创建fastAPI应用实例
app = FastAPI(
    title="RAG Enterprise Knowledge Base API",
    version="0.1.0",
    lifespan=lifespan)

# 引入CORS,配置跨域
app.add_middleware(
    CORSMiddleware,  # 允许前端页面访问后端API
    allow_origins=["*"],  # 允许所有的来源，不管访问者是本地服务器还是网络服务器（百度）
    allow_credentials=True,  # 允许携带cookie，默认为false，因为前端可能会带上 cookie
    allow_methods=["*"],  # 允许所有的请求方法，不管是GET POST PUT DELETE都可以支持
    allow_headers=["*"],  # 允许所有的请求头，任何请求头都可以支持
)

# 注册路由
app.include_router(documents.router)
