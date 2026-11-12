"""Small, dependency-free translation layer for user-facing backend messages.

The dashboard sends ``Accept-Language`` on every request and may override it
with ``X-Mori-Locale``. Chinese is the default so a fresh installation behaves
predictably even when the client sends no language header.
"""

from __future__ import annotations

import re
from typing import Any

DEFAULT_LOCALE = "zh-CN"
SUPPORTED_LOCALES = ("zh-CN", "en-US")

_ALIASES = {
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh-hans": "zh-CN",
    "zh-hans-cn": "zh-CN",
    "en": "en-US",
    "en-us": "en-US",
    "en-gb": "en-US",
}

MESSAGES: dict[str, dict[str, str]] = {
    "zh-CN": {
        "common.unauthorized": "请先登录",
        "common.forbidden": "没有操作权限",
        "common.not_found": "资源不存在",
        "common.conflict": "请求冲突",
        "common.invalid_request": "请求参数校验失败",
        "common.request_failed": "请求失败",
        "common.server_error": "服务器内部错误",
        "common.too_many_requests": "请求过于频繁，请稍后重试",
        "common.unknown_field": "未知字段",
        "auth.invalid_credentials": "用户名或密码错误",
        "auth.account_disabled": "该账户已被停用",
        "auth.token_expired": "登录已过期，请重新登录",
        "auth.token_invalid": "登录凭证无效",
        "auth.token_revoked": "登录状态已失效，请重新登录",
        "auth.account_unavailable": "账户不存在或已被停用",
        "auth.rate_limited": "登录尝试过于频繁，请在 {seconds} 秒后重试",
        "auth.login_success": "登录成功",
        "auth.logout_success": "已退出登录",
        "auth.password_updated": "密码已更新",
        "auth.password_mismatch": "两次输入的新密码不一致",
        "auth.current_password_incorrect": "当前密码不正确",
        "auth.new_password_same": "新密码不能与当前密码相同",
        "auth.account_missing": "账户不存在",
        "auth.account_data_error": "账户数据异常",
        "password.empty": "密码不能为空",
        "password.too_short": "密码长度至少为 {min_length} 位",
        "password.needs_uppercase": "密码必须包含至少一个大写字母",
        "password.needs_lowercase": "密码必须包含至少一个小写字母",
        "password.needs_digit": "密码必须包含至少一个数字",
        "accounts.file_title": "MoriBot 初始管理员账号",
        "accounts.file_line": "用户名: {username}\n密码:   {password}\n生成时间: {timestamp}",
        "accounts.file_hint": "请登录后尽快修改密码（当前版本可调用 /api/v1/auth/change-password）。\n修改成功后，本文件会自动删除。",
        "accounts.log_title": "MoriBot 已创建管理员账号",
        "accounts.log_hint": "请登录后尽快修改密码。",
        "accounts.credentials_file": "凭据文件",
        "accounts.log_block": "\n============================================================\n  {title}\n  用户名: {username}\n  密码:   {password}\n  {file_label}: {path}\n  {hint}\n============================================================",
        "backup.export_failed": "数据导出失败",
        "backup.import_failed": "数据导入失败",
        "backup.invalid_archive": "备份文件无效或已损坏",
        "backup.invalid_manifest": "备份清单缺失或格式错误",
        "backup.unsupported_format": "不支持的备份格式版本",
        "backup.checksum_mismatch": "备份文件校验失败: {path}",
        "backup.unsafe_path": "备份文件包含不安全的路径",
        "backup.database_corrupt": "备份中的数据库完整性校验失败",
        "backup.missing_config": "备份中缺少 config.json",
        "backup.import_success": "数据导入完成",
        "backup.export_success": "数据导出完成",
        "backup.file_not_found": "备份文件不存在",
        "backup.export_done": "备份已导出: {path}",
        "backup.import_done": "数据已导入: {path}",
        "backup.previous_dir": "原数据目录已保留: {path}",
        "backup.confirm": "将用 {archive} 替换 {data_dir} 中的全部数据。继续？[y/N] ",
        "backup.cancelled": "已取消",
        "backup.need_yes": "非交互环境下需要 --yes 才能导入",
        "backup.stop_server": "导入前请确保 MoriBot 服务已经停止。",
        "mobile.pairing_code_created": "配对码已生成，请在手机端输入",
        "mobile.invalid_pairing_code": "配对码无效或已使用",
        "mobile.pairing_code_expired": "配对码已过期，请重新生成",
        "mobile.device_name_required": "请填写设备名称",
        "mobile.device_paired": "设备配对成功",
        "mobile.invalid_device_token": "设备令牌无效",
        "mobile.device_revoked": "设备已下线",
        "mobile.device_not_found": "设备不存在",
        "mobile.device_offline": "设备当前不在线，无法发送消息",
        "mobile.message_sent": "消息已发送到设备",
        "mobile.pairing_rate_limited": "配对尝试过于频繁，请在 {seconds} 秒后重试",
        "mobile.message_too_large": "消息内容过长",
        "mobile.invalid_message": "消息格式无效",
        "mobile.revoked_message": "设备已被移除",
        "mobile.shutdown_message": "服务正在关闭",
        "mobile.too_many_devices": "设备数量已达到上限，请先移除不用的设备",
    },
    "en-US": {
        "common.unauthorized": "Authentication required",
        "common.forbidden": "Permission denied",
        "common.not_found": "Resource not found",
        "common.conflict": "Request conflict",
        "common.invalid_request": "Invalid request",
        "common.request_failed": "Request failed",
        "common.server_error": "Internal server error",
        "common.too_many_requests": "Too many requests, please try again later",
        "common.unknown_field": "Unknown field",
        "auth.invalid_credentials": "Incorrect username or password",
        "auth.account_disabled": "This account has been disabled",
        "auth.token_expired": "Your session has expired. Please sign in again",
        "auth.token_invalid": "Invalid authentication token",
        "auth.token_revoked": "Your session is no longer valid. Please sign in again",
        "auth.account_unavailable": "Account does not exist or has been disabled",
        "auth.rate_limited": "Too many login attempts. Try again in {seconds} seconds",
        "auth.login_success": "Signed in successfully",
        "auth.logout_success": "Signed out",
        "auth.password_updated": "Password updated",
        "auth.password_mismatch": "The new passwords do not match",
        "auth.current_password_incorrect": "Current password is incorrect",
        "auth.new_password_same": "New password must differ from the current password",
        "auth.account_missing": "Account not found",
        "auth.account_data_error": "Account data is invalid",
        "password.empty": "Password cannot be empty",
        "password.too_short": "Password must be at least {min_length} characters",
        "password.needs_uppercase": "Password must contain an uppercase letter",
        "password.needs_lowercase": "Password must contain a lowercase letter",
        "password.needs_digit": "Password must contain a digit",
        "accounts.file_title": "MoriBot initial administrator credentials",
        "accounts.file_line": "Username: {username}\nPassword: {password}\nGenerated: {timestamp}",
        "accounts.file_hint": "Change this password soon with /api/v1/auth/change-password.\nThis file is removed automatically after a successful change.",
        "accounts.log_title": "MoriBot created the administrator account",
        "accounts.log_hint": "Please change the password soon after signing in.",
        "accounts.credentials_file": "Credentials file",
        "accounts.log_block": "\n============================================================\n  {title}\n  Username: {username}\n  Password: {password}\n  {file_label}: {path}\n  {hint}\n============================================================",
        "backup.export_failed": "Failed to export data",
        "backup.import_failed": "Failed to import data",
        "backup.invalid_archive": "The backup file is invalid or corrupted",
        "backup.invalid_manifest": "Backup manifest is missing or invalid",
        "backup.unsupported_format": "Unsupported backup format version",
        "backup.checksum_mismatch": "Backup integrity check failed: {path}",
        "backup.unsafe_path": "The backup contains an unsafe path",
        "backup.database_corrupt": "Database integrity check failed for the backup",
        "backup.missing_config": "The backup does not contain config.json",
        "backup.import_success": "Data import completed",
        "backup.export_success": "Data export completed",
        "backup.file_not_found": "Backup file not found",
        "backup.export_done": "Backup exported: {path}",
        "backup.import_done": "Data imported: {path}",
        "backup.previous_dir": "Previous data directory kept at: {path}",
        "backup.confirm": "Replace all data in {data_dir} with {archive}? [y/N] ",
        "backup.cancelled": "Cancelled",
        "backup.need_yes": "Use --yes to import in a non-interactive environment",
        "backup.stop_server": "Stop the MoriBot server before importing data.",
        "mobile.pairing_code_created": "Pairing code created. Enter it on your phone",
        "mobile.invalid_pairing_code": "Pairing code is invalid or already used",
        "mobile.pairing_code_expired": "Pairing code expired. Please create a new one",
        "mobile.device_name_required": "Device name is required",
        "mobile.device_paired": "Device paired successfully",
        "mobile.invalid_device_token": "Invalid device token",
        "mobile.device_revoked": "Device disconnected",
        "mobile.device_not_found": "Device not found",
        "mobile.device_offline": "The device is offline; message not sent",
        "mobile.message_sent": "Message sent to device",
        "mobile.pairing_rate_limited": "Too many pairing attempts. Try again in {seconds} seconds",
        "mobile.message_too_large": "Message is too large",
        "mobile.invalid_message": "Invalid message format",
        "mobile.revoked_message": "This device has been removed",
        "mobile.shutdown_message": "Service is shutting down",
        "mobile.too_many_devices": "Device limit reached. Remove an unused device first",
    },
}

_LOCALE_TOKEN = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$")


def normalize_locale(value: str | None) -> str:
    """Normalize a locale tag to one of the supported locales."""
    if not value:
        return DEFAULT_LOCALE
    raw = value.strip().lower().replace("_", "-")
    if raw in _ALIASES:
        return _ALIASES[raw]
    if raw in {locale.lower() for locale in SUPPORTED_LOCALES}:
        return next(locale for locale in SUPPORTED_LOCALES if locale.lower() == raw)
    primary = raw.split("-", 1)[0]
    return _ALIASES.get(primary, DEFAULT_LOCALE)


def parse_accept_language(header: str | None) -> str | None:
    """Pick the highest-weighted supported locale from an Accept-Language header."""
    if not header:
        return None

    weighted: list[tuple[float, int, str]] = []
    for index, chunk in enumerate(header.split(",")):
        token = chunk.strip()
        if not token:
            continue
        parts = token.split(";")
        tag = parts[0].strip().lower()
        if tag in {"*", ""} or not _LOCALE_TOKEN.match(tag):
            continue
        quality = 1.0
        for parameter in parts[1:]:
            key, _, raw_value = parameter.strip().partition("=")
            if key.strip().lower() == "q":
                try:
                    quality = float(raw_value)
                except ValueError:
                    quality = 0.0
        locale = normalize_locale(tag)
        # Only accept tags that map to a real supported locale.
        if locale in SUPPORTED_LOCALES:
            weighted.append((quality, -index, locale))

    if not weighted:
        return None
    weighted.sort(reverse=True)
    return weighted[0][2]


def translate(key: str, locale: str | None = None, **kwargs: Any) -> str:
    """Translate a message key, falling back to Chinese and then the key."""
    resolved = normalize_locale(locale)
    catalog = MESSAGES.get(resolved, MESSAGES[DEFAULT_LOCALE])
    template = catalog.get(key) or MESSAGES[DEFAULT_LOCALE].get(key) or key
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError):
        return template
