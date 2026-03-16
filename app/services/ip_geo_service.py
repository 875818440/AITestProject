"""IP 地理位置解析服务。

优先使用本地 GeoIP2 数据库，降级到免费在线 API (ip-api.com)。
"""
import asyncio
import math
from dataclasses import dataclass

import aiohttp

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GeoInfo:
    ip: str
    country: str | None = None
    country_code: str | None = None
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    isp: str | None = None
    is_vpn: bool = False
    timezone: str | None = None


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """计算两个经纬度之间的大圆距离（公里）。"""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class GeoIPService:
    _geoip_reader = None

    @classmethod
    def _load_local_db(cls):
        """懒加载本地 GeoIP2 数据库。"""
        if cls._geoip_reader is not None:
            return cls._geoip_reader
        try:
            import geoip2.database
            cls._geoip_reader = geoip2.database.Reader(settings.geoip_db_path)
            logger.info("GeoIP2 本地数据库已加载", path=settings.geoip_db_path)
        except Exception as exc:
            logger.warning("GeoIP2 本地数据库加载失败，将使用在线 API", error=str(exc))
        return cls._geoip_reader

    async def lookup(self, ip: str) -> GeoInfo:
        """解析 IP 地理信息（本地优先，降级到在线 API）。"""
        # 跳过私有/保留地址
        if _is_private_ip(ip):
            return GeoInfo(ip=ip, country="Local", country_code="ZZ")

        # 尝试本地 GeoIP2
        reader = self._load_local_db()
        if reader:
            try:
                return self._parse_local(reader, ip)
            except Exception:
                pass

        # 降级：ip-api.com 免费 API
        return await self._lookup_online(ip)

    def _parse_local(self, reader, ip: str) -> GeoInfo:
        response = reader.city(ip)
        return GeoInfo(
            ip=ip,
            country=response.country.name,
            country_code=response.country.iso_code,
            city=response.city.name,
            lat=float(response.location.latitude or 0),
            lng=float(response.location.longitude or 0),
            timezone=str(response.location.time_zone or ""),
        )

    async def _lookup_online(self, ip: str) -> GeoInfo:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
                async with session.get(
                    f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,city,lat,lon,isp,org,timezone"
                ) as resp:
                    data = await resp.json()
                    if data.get("status") == "success":
                        return GeoInfo(
                            ip=ip,
                            country=data.get("country"),
                            country_code=data.get("countryCode"),
                            city=data.get("city"),
                            lat=data.get("lat"),
                            lng=data.get("lon"),
                            isp=data.get("isp") or data.get("org"),
                            timezone=data.get("timezone"),
                        )
        except Exception as exc:
            logger.warning("在线 GeoIP 查询失败", ip=ip, error=str(exc))
        return GeoInfo(ip=ip)

    def distance_from_home(
        self,
        geo: GeoInfo,
        home_lat: float | None,
        home_lng: float | None,
    ) -> float | None:
        """计算与用户常驻地的距离（公里）。"""
        if home_lat is None or home_lng is None:
            return None
        if geo.lat is None or geo.lng is None:
            return None
        return _haversine_km(home_lat, home_lng, geo.lat, geo.lng)


def _is_private_ip(ip: str) -> bool:
    import ipaddress
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        return False


geo_service = GeoIPService()
