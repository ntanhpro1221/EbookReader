from __future__ import annotations

import base64
import html
import os
import subprocess
import sys
from pathlib import Path


class WindowsNotifier:
    def __init__(self, app_name: str = "Ebook Reader") -> None:
        self.app_name = app_name

    def notify(self, title: str, message: str, *, critical: bool = False, project_path: Path | None = None) -> bool:
        if os.name != "nt":
            print(f"[{title}] {message}", file=sys.stderr)
            return False
        title_xml = html.escape(title[:120])
        message_xml = html.escape(message[:700])
        path_xml = html.escape(str(project_path)[:500]) if project_path else ""
        detail = f"<text>{path_xml}</text>" if path_xml else ""
        audio = "ms-winsoundevent:Notification.Looping.Alarm2" if critical else "ms-winsoundevent:Notification.Default"
        scenario = " scenario=\"alarm\"" if critical else ""
        xml = (
            f"<toast{scenario}><visual><binding template=\"ToastGeneric\">"
            f"<text>{title_xml}</text><text>{message_xml}</text>{detail}"
            f"</binding></visual><audio src=\"{audio}\"/></toast>"
        )
        xml_payload = base64.b64encode(xml.encode("utf-16le")).decode("ascii")
        app_payload = base64.b64encode(self.app_name.encode("utf-16le")).decode("ascii")
        script = rf"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$xmlText = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{xml_payload}'))
$appName = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{app_payload}'))
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($xmlText)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appName).Show($toast)
"""
        encoded_script = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        shown = False
        try:
            result = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                    "-EncodedCommand", encoded_script,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=12,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            shown = result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            shown = False

        if not shown:
            # Session notification fallback. It is non-blocking for the worker and visible over other apps.
            try:
                fallback = f"{title}: {message}"
                subprocess.Popen(
                    ["msg.exe", "*", "/TIME:60", fallback[:900]],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                shown = True
            except OSError:
                pass
        if critical:
            try:
                import winsound

                winsound.MessageBeep(winsound.MB_ICONHAND)
            except Exception:
                pass
        return shown

    def critical_stop(self, book_title: str, reason: str, project_path: Path, checkpoint: str = "") -> None:
        message = (
            f"Book: {book_title}. Lý do: {reason}. "
            "Các checkpoint đã commit vẫn được giữ; đoạn đang chạy sẽ được recovery kiểm tra."
        )
        if checkpoint:
            message += f" Vị trí: {checkpoint}."
        self.notify("Ebook Reader đã tự dừng", message, critical=True, project_path=project_path)

    def recovery_notice(self, book_title: str, project_path: Path, recovered: int, reset: int) -> None:
        self.notify(
            "Đã khôi phục audiobook bị gián đoạn",
            f"Book: {book_title}. Giữ lại {recovered} đoạn hợp lệ; {reset} đoạn dở sẽ được tạo lại.",
            critical=False,
            project_path=project_path,
        )
