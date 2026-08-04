import re
from typing import Optional
from loguru import logger


def sanitize_input(text: str, max_length: int = 2048) -> str:
    """净化输入文本"""
    if not text:
        return ""
    
    # 移除潜在的危险字符
    text = text.strip()
    
    # 限制长度
    if len(text) > max_length:
        text = text[:max_length]
        logger.warning("输入文本被截断到{}字符", max_length)
    
    return text


def is_safe_filename(filename: str) -> bool:
    """检查文件名是否安全"""
    if not filename:
        return False
    
    # 检查危险字符
    dangerous_chars = r'[<>:"/\\|?*\x00-\x1f]'
    if re.search(dangerous_chars, filename):
        return False
    
    # 检查路径遍历
    if ".." in filename or "/" in filename or "\\" in filename:
        return False
    
    # 检查保留文件名
    reserved_names = [
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
    ]
    
    name_without_ext = filename.split(".")[0].upper()
    if name_without_ext in reserved_names:
        return False
    
    return True


def sanitize_sql_input(text: str) -> Optional[str]:
    """净化SQL输入"""
    if not text:
        return None
    
    # 移除潜在的SQL注入字符
    text = text.strip()
    
    # 检查危险模式
    dangerous_patterns = [
        r";\s*(DROP|ALTER|TRUNCATE|CREATE)\s+",
        r"UNION\s+ALL\s+SELECT",
        r"INTO\s+(OUTFILE|DUMPFILE)",
        r"LOAD_FILE\s*\(",
        r"BENCHMARK\s*\(",
        r"SLEEP\s*\(",
        r"WAITFOR\s+DELAY",
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            logger.warning("检测到危险SQL模式: {}", text[:200])
            return None
    
    return text


def validate_question(question: str) -> tuple[bool, str]:
    """验证用户问题"""
    if not question:
        return False, "问题不能为空"
    
    question = question.strip()
    
    if len(question) < 2:
        return False, "问题太短"
    
    if len(question) > 2048:
        return False, "问题太长"
    
    # 检查是否包含恶意内容
    malicious_patterns = [
        r"<script.*?>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",
        r"expression\s*\(",
    ]
    
    for pattern in malicious_patterns:
        if re.search(pattern, question, re.IGNORECASE):
            return False, "问题包含不允许的内容"
    
    return True, ""


def validate_api_key(api_key: str) -> bool:
    """验证API密钥格式"""
    if not api_key:
        return False
    
    # DeepSeek API密钥格式
    if api_key.startswith("sk-") and len(api_key) >= 20:
        return True
    
    # 其他格式的API密钥
    if len(api_key) >= 20 and api_key.isalnum():
        return True
    
    return False