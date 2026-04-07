from __future__ import annotations


class NotificationController:
    _OK = ("成功", "完成", "连接成功", "下载成功", "上传成功", "校验通过")
    _DANGER = ("失败", "错误", "崩溃", "超时", "无效")
    _WARN = ("未连接", "未实现", "功能不可用", "请稍候", "未检测到", "差异", "中止")
    _CONNECTION_STATUS = ("自动重连", "连接中断")

    @classmethod
    def classify_notice(cls, title: str, message: str) -> str:
        text = f"{title}{message}"
        if any(token in text for token in cls._OK):
            return "ok"
        if any(token in text for token in cls._DANGER):
            return "danger"
        if any(token in text for token in cls._WARN):
            return "warn"
        return "info"

    @classmethod
    def build_notice(cls, title: str, message: str, duration_ms: int = 3000) -> dict:
        title_text = str(title or "提示")
        message_text = str(message or "")
        return {
            "title": title_text,
            "message": message_text,
            "level": cls.classify_notice(title_text, message_text),
            "duration_ms": max(0, int(duration_ms or 0)),
            "fallback_text": f"提示: {title_text} {message_text}".strip(),
        }

    @classmethod
    def connection_error_notice(cls, message: str) -> dict:
        message_text = str(message or "连接异常")
        title = "连接状态" if any(token in message_text for token in cls._CONNECTION_STATUS) else "连接失败"
        return cls.build_notice(title, message_text)


__all__ = ["NotificationController"]
