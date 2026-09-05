"""Error codes shared by the MCP server, the CLI and SKILL.md."""
from __future__ import annotations


class CgError(Exception):
    """A tool-level error the agent can act on (returned with isError=true, never a crash)."""

    def __init__(self, code: str, message: str, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra

    def to_dict(self) -> dict:
        d = {"ok": False, "error": self.code, "message": self.message}
        d.update(self.extra)
        return d


# code -> (what happened, what the agent should tell the user / do)
ERROR_TABLE = {
    "CDP_UNREACHABLE": ("Cannot connect to the Chromium CDP endpoint",
                        "Chromium servisi kapalı: `systemctl --user status chromium-cdp` (hermes kullanıcısı)"),
    "SESSION_LOST": ("chatgpt.com shows a login page or an anonymous session",
                     "ChatGPT girişi düştü; noVNC ile sunucudaki Chromium'da tekrar giriş yapılmalı"),
    "PROJECT_NOT_FOUND": ("The configured project is not in the sidebar and could not be created",
                          "Proje adı config ile ChatGPT'deki adla aynı mı? Gerekirse noVNC'de elle oluştur"),
    "MODEL_MISMATCH": ("The requested model could not be selected (strict mode)",
                       "Model adı/slug değişmiş olabilir; `doctor` çıktısındaki model listesini ilet"),
    "UPLOAD_UNAVAILABLE": ("No file input found or the upload never completed",
                           "Dosya yükleme çalışmadı; metni mesaja gömerek tekrar dene"),
    "FILE_NOT_ALLOWED": ("A file path is outside CHATGPT_WORK_DIR or does not exist",
                         "Dosyalar /home/hermes/work altında olmalı"),
    "RATE_LIMIT": ("ChatGPT reports a usage limit", "Kullanım sınırı; bir süre sonra tekrar dene"),
    "BOT_CHECK": ("Cloudflare challenge did not clear", "Bot kontrolü; noVNC'de sayfayı aç, gerekirse WARP IP değiştir"),
    "MESSAGE_TOO_LONG": ("ChatGPT refused the message length", "Mesajı kısalt veya dosya olarak yükle"),
    "GENERATION_ERROR": ("The reply failed even after one regenerate", "Sohbet URL'sini kullanıcıya ver, sonra tekrar dene"),
    "CHAT_NOT_FOUND": ("No open tab or reachable conversation for this handle", "`open_chat` ile URL'yi yeniden aç"),
    "LOCKED": ("Another chatgpt-web operation is running", "Bekle ve tekrar dene"),
    "TIMEOUT": ("The reply did not finish within the wait budget", "`wait` aracını tekrar çağır"),
    "INPUT": ("Bad arguments", "Argümanları kontrol et"),
    "INTERNAL": ("Unexpected failure; see screenshot/debug dir", "Ekran görüntüsünü ve mesajı kullanıcıya ilet"),
}
