"""Every DOM selector in one place, each as an ordered list of fallbacks.

Verified against chatgpt.com on 2026-09-05 (logged-in free plan). When the UI
drifts, fix it here and nowhere else.
"""
from __future__ import annotations

PROMPT_BOX = ["#prompt-textarea", 'div[contenteditable="true"][id*="prompt"]', 'div[contenteditable="true"]']
SEND_BUTTON = ['button[data-testid="send-button"]', 'button[aria-label="Send prompt"]', 'button[aria-label="Send message"]']
STOP_BUTTON = ['button[data-testid="stop-button"]', 'button[aria-label="Stop generating"]', 'button[aria-label="Stop streaming"]']
COMPOSER_PLUS = ['button[data-testid="composer-plus-btn"]', 'button[aria-label="Add files and more"]', 'button[aria-label*="Attach"]']
FILE_INPUT = ["input#upload-files", 'input[type="file"]:not([accept])', 'input[type="file"]']
MODEL_SWITCHER = ['button[data-testid="model-switcher-dropdown-button"]', 'button[aria-haspopup="menu"]:has-text("ChatGPT")']

ASSISTANT_TURN = ['[data-message-author-role="assistant"]']
USER_TURN = ['[data-message-author-role="user"]']
TURN_ARTICLE = ['article[data-testid^="conversation-turn-"]']
COPY_BUTTON = ['button[aria-label="Copy"]', 'button[data-testid="copy-turn-action-button"]']
REGENERATE_BUTTON = ['button[aria-label*="Regenerate"]', 'button:has-text("Regenerate")', 'button:has-text("Yeniden oluştur")']
CONTINUE_BUTTON = ['button:has-text("Continue generating")', 'button:has-text("Oluşturmaya devam et")']

# Session / page classification
PROFILE_BUTTON = ['[data-testid="accounts-profile-button"]', '[data-testid="profile-button"]']
LOGIN_BUTTON = ['[data-testid="login-button"]', 'button:has-text("Log in")', 'a[href*="/auth/login"]']
UPGRADE_BUTTON = ['button[aria-label="Upgrade"]', 'a[href*="/pricing"]']
CLOUDFLARE_IFRAME = ['iframe[src*="challenges.cloudflare.com"]', '#challenge-form']

# Projects (sidebar)
NEW_PROJECT_BUTTON = ['button[aria-label="New project"]', 'button:has-text("New project")', 'button:has-text("Yeni proje")']
PROJECT_OPTIONS_BUTTON = 'button[aria-label="Open project options for {name}"]'
PROJECT_OPTIONS_PREFIX = 'button[aria-label^="Open project options for "]'
CHAT_LINKS = ['a[href^="/c/"]']

# Text patterns (regex, case-insensitive) used on innerText
THINKING_RE = r"^(Thinking|Düşünüyor|Reasoning|Pro is thinking|Thought for|\d+ saniye düşündü)"
GENERATION_ERROR_RE = r"(Something went wrong|network error|Bir şeyler ters gitti|An error occurred)"
RATE_LIMIT_RE = r"(reached (your|the) .*limit|usage cap|too many requests|kullanım sınırı|limit(e|ine) ulaştı)"
TOO_LONG_RE = r"(message is too long|too long|çok uzun)"
UPLOADING_RE = r"(Uploading|Yükleniyor)"
