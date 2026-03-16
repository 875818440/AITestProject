"""多渠道告警分发服务。

渠道优先级：App 推送 > 短信 > 邮件 > WebSocket
去重：Redis SETNX + TTL（同用户 5 分钟内不重复告警）
"""
import uuid
from datetime import datetime, timezone

import aiohttp
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis_client import get_redis

logger = get_logger(__name__)

DEDUP_KEY_PREFIX = "alert:dedup:"


# ──────────────────────────────────────────────
# 去重检查
# ──────────────────────────────────────────────

async def _check_and_set_dedup(user_id: str) -> bool:
    """
    检查是否在去重窗口内。
    若未触发过，设置标记并返回 True（允许发送）；
    否则返回 False（跳过发送）。
    """
    redis = get_redis()
    key = f"{DEDUP_KEY_PREFIX}{user_id}"
    result = await redis.set(key, "1", nx=True, ex=settings.alert_dedup_window_seconds)
    return result is not None  # True = 成功设置（首次），False = 已存在（重复）


# ──────────────────────────────────────────────
# 邮件告警
# ──────────────────────────────────────────────

async def send_email_alert(
    to_email: str,
    subject: str,
    body: str,
) -> bool:
    """通过 SMTP 发送 HTML 邮件。"""
    if not settings.smtp_username:
        logger.warning("SMTP 未配置，跳过邮件发送")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to_email
    msg.attach(MIMEText(body, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            start_tls=True,
        )
        logger.info("邮件告警发送成功", to=to_email)
        return True
    except Exception as exc:
        logger.error("邮件告警发送失败", to=to_email, error=str(exc))
        return False


# ──────────────────────────────────────────────
# 短信告警（阿里云 SMS）
# ──────────────────────────────────────────────

async def send_sms_alert(phone: str, risk_score: int, level: str) -> bool:
    """通过阿里云 SMS 发送短信告警。"""
    if not settings.aliyun_access_key_id:
        logger.warning("阿里云 SMS 未配置，跳过短信发送")
        return False

    try:
        import hmac
        import hashlib
        import base64
        import urllib.parse
        from datetime import datetime

        params = {
            "Action": "SendSms",
            "Version": "2017-05-25",
            "SignatureMethod": "HMAC-SHA1",
            "SignatureVersion": "1.0",
            "SignatureNonce": str(uuid.uuid4()),
            "Timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "Format": "JSON",
            "AccessKeyId": settings.aliyun_access_key_id,
            "PhoneNumbers": phone,
            "SignName": settings.aliyun_sms_sign_name,
            "TemplateCode": settings.aliyun_sms_template_code,
            "TemplateParam": f'{{"score":"{risk_score}","level":"{level}"}}',
        }
        sorted_params = sorted(params.items())
        query_string = urllib.parse.urlencode(sorted_params)
        string_to_sign = f"GET&%2F&{urllib.parse.quote(query_string, safe='')}"
        signing_key = f"{settings.aliyun_access_key_secret}&".encode()
        signature = base64.b64encode(
            hmac.new(signing_key, string_to_sign.encode(), hashlib.sha1).digest()
        ).decode()
        params["Signature"] = signature

        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://dysmsapi.aliyuncs.com/",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if data.get("Code") == "OK":
                    logger.info("短信告警发送成功", phone=phone[-4:])
                    return True
                logger.error("短信告警发送失败", code=data.get("Code"), msg=data.get("Message"))
                return False
    except Exception as exc:
        logger.error("短信告警异常", phone=phone[-4:], error=str(exc))
        return False


# ──────────────────────────────────────────────
# FCM App 推送
# ──────────────────────────────────────────────

async def send_fcm_push(
    fcm_token: str,
    title: str,
    body: str,
    data: dict | None = None,
) -> bool:
    """通过 Firebase FCM 发送 App 推送通知。"""
    if not settings.fcm_server_key:
        logger.warning("FCM 未配置，跳过推送")
        return False

    payload = {
        "to": fcm_token,
        "notification": {"title": title, "body": body},
        "data": data or {},
        "priority": "high",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                settings.fcm_api_url,
                json=payload,
                headers={
                    "Authorization": f"key={settings.fcm_server_key}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                result = await resp.json()
                if result.get("success") == 1:
                    logger.info("FCM 推送成功")
                    return True
                logger.error("FCM 推送失败", result=result)
                return False
    except Exception as exc:
        logger.error("FCM 推送异常", error=str(exc))
        return False


# ──────────────────────────────────────────────
# 告警消息模板
# ──────────────────────────────────────────────

def _build_alert_message(risk_score: int, level: str, triggered_rules: list[str]) -> tuple[str, str]:
    """构建告警标题和正文。"""
    level_emoji = {"normal": "✅", "low": "⚠️", "medium": "🔶", "high": "🚨"}.get(level, "⚠️")
    title = f"{level_emoji} 账号安全预警 — 风险评分 {risk_score}/100"

    rules_text = "、".join(triggered_rules) if triggered_rules else "综合行为异常"
    body = f"""
    <h2>账号安全预警</h2>
    <p>您的账号检测到异常行为，风险评分为 <strong>{risk_score}/100</strong>（{level}）。</p>
    <p>触发规则：{rules_text}</p>
    <p>如非本人操作，请立即修改密码并联系客服。</p>
    <p><small>此邮件由系统自动发送，请勿回复。</small></p>
    """
    return title, body


# ──────────────────────────────────────────────
# 主告警分发入口
# ──────────────────────────────────────────────

async def dispatch_alert(
    user_id: str,
    risk_score: int,
    level: str,
    triggered_rules: list[str],
    user_email: str | None = None,
    user_phone: str | None = None,
    fcm_token: str | None = None,
) -> dict[str, bool]:
    """
    告警分发入口：
    1. 去重检查（窗口内已告警则跳过）
    2. 按渠道并发发送
    3. 返回各渠道发送结果
    """
    # 去重
    can_send = await _check_and_set_dedup(user_id)
    if not can_send:
        logger.info("告警去重，跳过发送", user_id=user_id)
        return {}

    title, body = _build_alert_message(risk_score, level, triggered_rules)
    results: dict[str, bool] = {}

    # FCM 推送（优先级最高）
    if fcm_token:
        results["push"] = await send_fcm_push(
            fcm_token, title,
            f"风险评分 {risk_score}/100，请确认是否为本人操作。",
            data={"risk_score": str(risk_score), "level": level},
        )

    # 短信
    if user_phone:
        results["sms"] = await send_sms_alert(user_phone, risk_score, level)

    # 邮件
    if user_email:
        results["email"] = await send_email_alert(user_email, title, body)

    logger.info(
        "告警分发完成",
        user_id=user_id,
        risk_score=risk_score,
        level=level,
        results=results,
    )
    return results
