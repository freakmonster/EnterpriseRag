"""灰度配置管理：从 Nacos HTTP API 读取，TTL 缓存，线程安全"""
import json
import random
import threading
import time
import logging

import requests

from config.settings import settings

logger = logging.getLogger(__name__)


class GrayConfig:
    """灰度配置单例，5 秒 TTL 缓存，Nacos 不可达时降级为正常模式"""

    def __init__(self):
        self._gray_status: int = 0
        self._gray_ratio: int = 0
        self._last_fetch: float = 0
        self._ttl: float = 5.0
        self._lock = threading.Lock()

    def _needs_refresh(self) -> bool:
        return time.time() - self._last_fetch >= self._ttl

    def refresh(self):
        """强制刷新（webhook 触发时调用）"""
        with self._lock:
            self._fetch()
            self._last_fetch = time.time()

    def _ensure_fresh(self):
        now = time.time()
        if now - self._last_fetch < self._ttl:
            return
        with self._lock:
            if time.time() - self._last_fetch < self._ttl:
                return
            self._fetch()
            self._last_fetch = time.time()

    def _fetch(self):
        try:
            resp = requests.get(
                f"http://{settings.nacos_host}/nacos/v1/cs/configs",
                params={
                    "dataId": settings.nacos_data_id,
                    "group": settings.nacos_group,
                },
                timeout=3,
            )
            if resp.status_code == 200:
                data = json.loads(resp.text)
                self._gray_status = data.get("gray_status", 0)
                self._gray_ratio = data.get("gray_ratio", 0)
            elif resp.status_code == 404:
                # 配置不存在，保持默认
                pass
        except Exception:
            # Nacos 不可达，保持上一次的值不变（初始化时为 0）
            pass

    @property
    def gray_status(self) -> int:
        self._ensure_fresh()
        return self._gray_status

    @property
    def gray_ratio(self) -> int:
        self._ensure_fresh()
        return self._gray_ratio

    def is_gray_traffic(self) -> bool:
        """按 ratio 随机分流，返回 True 表示本次请求走灰度查询"""
        if self.gray_status == 0:
            return False
        return random.random() * 100 < self._gray_ratio

    def publish_config(self, gray_status: int, gray_ratio: int):
        """写入 Nacos 配置"""
        content = json.dumps(
            {"gray_status": gray_status, "gray_ratio": gray_ratio},
            ensure_ascii=False,
        )
        try:
            resp = requests.post(
                f"http://{settings.nacos_host}/nacos/v1/cs/configs",
                data={
                    "dataId": settings.nacos_data_id,
                    "group": settings.nacos_group,
                    "content": content,
                    "type": "json",
                },
                timeout=3,
            )
            if resp.status_code == 200:
                self._gray_status = gray_status
                self._gray_ratio = gray_ratio
                self._last_fetch = time.time()
                logger.info(f"Nacos 配置已更新: gray_status={gray_status}, gray_ratio={gray_ratio}")
            else:
                logger.warning(f"Nacos 写入失败: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.warning(f"Nacos 不可达，配置未持久化: {e}")


# 模块级单例
gray_config = GrayConfig()
