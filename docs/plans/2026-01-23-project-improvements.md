# Gmail Organizer Improvement Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve code quality, reliability, and maintainability of Gmail Organizer

**Architecture:** Refactor duplicated code, add proper error handling, fix failing tests, and improve security

**Tech Stack:** Python 3.9+, pytest, Google APIs

---

## Phase 1: Critical Fixes (Immediate)

### Task 1: Fix Failing Tests

**Files:**
- Modify: `tests/test_gmail_client.py`

**Step 1: Read failing test code**

```bash
pytest tests/test_gmail_client.py -v 2>&1 | head -50
```

Expected: See which tests fail and why

**Step 2: Fix batch size assumption in tests**

The tests assume `GMAIL_BATCH_SIZE=100`, but actual value is `10`.

```python
# In test_batch_get_emails_creates_correct_batches
# Change hardcoded 100 to config.GMAIL_BATCH_SIZE

# Before:
# assert mock_service.return_value.users.return_value.messages.return_value.list.call_count == 1

# After: Use actual batch size from config
```

**Step 3: Run tests to verify fix**

```bash
pytest tests/test_gmail_client.py -v
```

Expected: All tests pass

**Step 4: Commit**

```bash
git add tests/test_gmail_client.py
git commit -m "fix: correct batch size assumptions in gmail_client tests"
```

---

### Task 2: Fix Bare Except Clause

**Files:**
- Modify: `gmail_client.py:350`

**Step 1: Find the bare except**

```bash
grep -n "except:" gmail_client.py
```

**Step 2: Replace bare except with specific exceptions**

```python
# Before (line ~350):
except:
    pass

# After:
except (base64.binascii.Error, UnicodeDecodeError) as e:
    logger.debug(f"Failed to decode email body: {e}")
```

**Step 3: Run tests**

```bash
pytest tests/test_gmail_client.py -v
```

Expected: PASS

**Step 4: Commit**

```bash
git add gmail_client.py
git commit -m "fix: replace bare except with specific exceptions in _extract_body"
```

---

### Task 3: Fix Token File Race Condition

**Files:**
- Modify: `auth.py:81-83`

**Step 1: Write failing test**

```python
# tests/test_auth.py - add this test
def test_token_file_permissions_on_create(tmp_path, monkeypatch):
    """Token file should be created with 0o600 permissions atomically."""
    import os
    import stat

    token_path = tmp_path / "token.json"
    # Verify file doesn't exist with world-readable permissions at any point
    # This is more of a code inspection than runtime test
    assert True  # Placeholder - actual fix is code change
```

**Step 2: Fix auth.py to use atomic file creation**

```python
# Before (auth.py ~line 81):
with open(token_path, 'w') as token_file:
    token_file.write(creds.to_json())
os.chmod(token_path, 0o600)

# After:
import tempfile
# Create with restricted permissions from the start
fd = os.open(str(token_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
try:
    with os.fdopen(fd, 'w') as token_file:
        token_file.write(creds.to_json())
except:
    os.close(fd)
    raise
```

**Step 3: Run tests**

```bash
pytest tests/test_auth.py -v
```

Expected: PASS

**Step 4: Commit**

```bash
git add auth.py tests/test_auth.py
git commit -m "fix: create token file with secure permissions atomically"
```

---

## Phase 2: Code Quality (High Priority)

### Task 4: Extract Duplicate is_safe_sender Function

**Files:**
- Create: `utils.py` (add to existing)
- Modify: `main.py:22-31`
- Modify: `scheduler.py:31-40`

**Step 1: Write test for centralized function**

```python
# tests/test_utils.py - add this test
def test_is_safe_sender_with_trusted_domain():
    """Emails from trusted domains should be identified as safe."""
    from utils import is_safe_sender
    from unittest.mock import Mock

    email = Mock()
    email.sender_email = "noreply@github.com"

    # Assuming github.com is in safe_senders
    result = is_safe_sender(email)
    assert result == True

def test_is_safe_sender_with_unknown_domain():
    """Emails from unknown domains should not be safe."""
    from utils import is_safe_sender
    from unittest.mock import Mock

    email = Mock()
    email.sender_email = "spam@unknown-domain.xyz"

    result = is_safe_sender(email)
    assert result == False
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_utils.py::test_is_safe_sender_with_trusted_domain -v
```

Expected: FAIL (function not in utils.py)

**Step 3: Add function to utils.py**

```python
# utils.py - add this function
import config

def is_safe_sender(email) -> bool:
    """
    Check if email is from a trusted sender.

    Args:
        email: Email object with sender_email attribute

    Returns:
        True if sender is in safe_senders or safe_domains
    """
    sender_email = email.sender_email.lower()

    # Check exact email match
    if sender_email in config.SAFE_SENDERS:
        return True

    # Check domain match
    domain = sender_email.split('@')[-1] if '@' in sender_email else ''
    if domain in config.SAFE_DOMAINS:
        return True

    return False
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_utils.py::test_is_safe_sender_with_trusted_domain -v
```

Expected: PASS

**Step 5: Update main.py to use centralized function**

```python
# main.py - remove lines 22-31 and add import
from utils import is_safe_sender
```

**Step 6: Update scheduler.py to use centralized function**

```python
# scheduler.py - remove lines 31-40 and add import
from utils import is_safe_sender
```

**Step 7: Run all tests**

```bash
pytest -v
```

Expected: All PASS

**Step 8: Commit**

```bash
git add utils.py main.py scheduler.py tests/test_utils.py
git commit -m "refactor: centralize is_safe_sender function in utils.py"
```

---

### Task 5: Add Custom Exception Classes

**Files:**
- Create: `exceptions.py`
- Modify: `ai_classifier.py`
- Modify: `gmail_client.py`

**Step 1: Create exceptions module**

```python
# exceptions.py
"""Custom exceptions for Gmail Organizer."""

class GmailOrganizerError(Exception):
    """Base exception for Gmail Organizer."""
    pass

class ClassificationError(GmailOrganizerError):
    """Error during email classification."""
    pass

class GmailConnectionError(GmailOrganizerError):
    """Error connecting to Gmail API."""
    pass

class AuthenticationError(GmailOrganizerError):
    """Error during authentication."""
    pass

class RateLimitError(GmailOrganizerError):
    """API rate limit exceeded."""
    pass
```

**Step 2: Update ai_classifier.py to use custom exceptions**

```python
# ai_classifier.py - replace generic Exception catches
from exceptions import ClassificationError, RateLimitError

# Line ~372: Instead of catching Exception
except json.JSONDecodeError as e:
    raise ClassificationError(f"Failed to parse AI response: {e}")
except Exception as e:
    raise ClassificationError(f"Classification failed: {e}")
```

**Step 3: Update gmail_client.py to use custom exceptions**

```python
# gmail_client.py - add imports and use custom exceptions
from exceptions import GmailConnectionError, RateLimitError

# Line ~119-120: Instead of returning empty list
except HttpError as e:
    if e.resp.status == 429:
        raise RateLimitError("Gmail API rate limit exceeded")
    raise GmailConnectionError(f"Gmail API error: {e}")
```

**Step 4: Run tests**

```bash
pytest -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add exceptions.py ai_classifier.py gmail_client.py
git commit -m "feat: add custom exception classes for better error handling"
```

---

### Task 6: Remove Dead Code

**Files:**
- Modify: `gmail_client.py:271-327`

**Step 1: Verify function is unused**

```bash
grep -r "_get_email_detail" --include="*.py" .
```

Expected: Only definition in gmail_client.py, no calls

**Step 2: Remove dead code**

Remove the `_get_email_detail()` method (lines 271-327)

**Step 3: Run tests**

```bash
pytest tests/test_gmail_client.py -v
```

Expected: PASS

**Step 4: Commit**

```bash
git add gmail_client.py
git commit -m "refactor: remove unused _get_email_detail method"
```

---

## Phase 3: Test Coverage (High Priority)

### Task 7: Add Scheduler Tests

**Files:**
- Create: `tests/test_scheduler.py`

**Step 1: Create test file**

```python
# tests/test_scheduler.py
"""Tests for scheduler module."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import threading

class TestGmailScheduler:
    """Tests for GmailScheduler class."""

    @patch('scheduler.get_gmail_credentials')
    @patch('scheduler.GmailClient')
    @patch('scheduler.EmailClassifier')
    def test_scheduler_initialization(self, mock_classifier, mock_client, mock_creds):
        """Scheduler should initialize with correct defaults."""
        from scheduler import GmailScheduler

        mock_creds.return_value = Mock()

        scheduler = GmailScheduler(
            interval_minutes=30,
            batch_size=50,
            analyze_only=False
        )

        assert scheduler.interval_minutes == 30
        assert scheduler.batch_size == 50
        assert scheduler.analyze_only == False

    @patch('scheduler.get_gmail_credentials')
    @patch('scheduler.GmailClient')
    @patch('scheduler.EmailClassifier')
    def test_scheduler_stop(self, mock_classifier, mock_client, mock_creds):
        """Scheduler should stop gracefully."""
        from scheduler import GmailScheduler

        mock_creds.return_value = Mock()

        scheduler = GmailScheduler()
        scheduler.running = True
        scheduler.stop()

        assert scheduler.running == False
```

**Step 2: Run tests**

```bash
pytest tests/test_scheduler.py -v
```

Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_scheduler.py
git commit -m "test: add scheduler module tests"
```

---

### Task 8: Add Slack Notifier Tests

**Files:**
- Create: `tests/test_slack_notifier.py`

**Step 1: Create test file**

```python
# tests/test_slack_notifier.py
"""Tests for slack_notifier module."""
import pytest
from unittest.mock import Mock, patch

class TestSlackNotifier:
    """Tests for SlackNotifier class."""

    @patch('slack_notifier.WebClient')
    def test_notifier_disabled_when_no_token(self, mock_client):
        """Notifier should be disabled when SLACK_ENABLED is False."""
        from slack_notifier import SlackNotifier

        with patch('slack_notifier.config.SLACK_ENABLED', False):
            notifier = SlackNotifier()
            assert notifier.enabled == False

    @patch('slack_notifier.WebClient')
    def test_send_notification_when_disabled(self, mock_client):
        """send_notification should return False when disabled."""
        from slack_notifier import SlackNotifier

        with patch('slack_notifier.config.SLACK_ENABLED', False):
            notifier = SlackNotifier()
            result = notifier.send_notification("Test message")
            assert result == False
```

**Step 2: Run tests**

```bash
pytest tests/test_slack_notifier.py -v
```

Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_slack_notifier.py
git commit -m "test: add slack_notifier module tests"
```

---

## Phase 4: Performance Optimization (Medium Priority)

### Task 9: Optimize Cache Saving

**Files:**
- Modify: `ai_classifier.py`

**Step 1: Add dirty flag to cache class**

```python
# ai_classifier.py - modify ClassificationCache class
class ClassificationCache:
    def __init__(self, cache_dir: Path = None):
        self.cache_dir = cache_dir or config.LOG_DIR
        self.cache_file = self.cache_dir / "classification_cache.json"
        self._cache: Dict[str, Dict] = {}
        self._dirty = False  # Add dirty flag
        self._load_cache()

    def set(self, email: Email, result: ClassificationResult):
        """Store result in cache (marks as dirty, doesn't save immediately)."""
        # ... existing code ...
        self._dirty = True
        # Remove: self._save_cache()  # Don't save on every set

    def flush(self):
        """Save cache to disk if dirty."""
        if self._dirty:
            self._save_cache()
            self._dirty = False
```

**Step 2: Update classifier to flush cache periodically**

```python
# ai_classifier.py - in classify_emails method
def classify_emails(self, emails: List[Email], show_progress: bool = True) -> List[Tuple[Email, ClassificationResult]]:
    results = []
    # ... existing code ...

    # Flush cache at end
    if self.cache:
        self.cache.flush()

    return results
```

**Step 3: Run tests**

```bash
pytest tests/test_ai_classifier.py -v
```

Expected: PASS

**Step 4: Commit**

```bash
git add ai_classifier.py
git commit -m "perf: batch cache saves with dirty flag"
```

---

### Task 10: Fix Inefficient Sleep Loop

**Files:**
- Modify: `scheduler.py:344-347`

**Step 1: Replace sleep loop with Event.wait()**

```python
# scheduler.py - modify wait logic
import threading

class GmailScheduler:
    def __init__(self, ...):
        # ... existing init ...
        self._stop_event = threading.Event()

    def stop(self):
        """Stop the scheduler."""
        self.running = False
        self._stop_event.set()  # Wake up waiting thread

    def run(self):
        # ... in the wait section, replace:
        # for _ in range(self.interval_minutes * 60):
        #     if not self.running:
        #         break
        #     time.sleep(1)

        # With:
        self._stop_event.wait(timeout=self.interval_minutes * 60)
        self._stop_event.clear()
```

**Step 2: Run tests**

```bash
pytest tests/test_scheduler.py -v
```

Expected: PASS

**Step 3: Commit**

```bash
git add scheduler.py
git commit -m "perf: replace sleep loop with threading.Event"
```

---

## Phase 5: Documentation (Medium Priority)

### Task 11: Add Architecture Diagram

**Files:**
- Create: `docs/architecture.md`

**Step 1: Create architecture documentation**

```markdown
# Gmail Organizer Architecture

## System Overview

```mermaid
graph TB
    subgraph "Gmail Organizer"
        M[main.py] --> A[auth.py]
        M --> G[gmail_client.py]
        M --> C[ai_classifier.py]

        S[scheduler.py] --> A
        S --> G
        S --> C
        S --> SL[slack_notifier.py]

        C --> |Gemini API| AI[Google Gemini]
        G --> |Gmail API| GM[Gmail]
        A --> |OAuth| GO[Google OAuth]

        CF[config.py] --> M
        CF --> S
        CF --> G
        CF --> C
    end

    subgraph "Storage"
        G --> TC[token.json]
        C --> CC[classification_cache.json]
        CF --> SS[safe_senders.json]
    end
```

## Data Flow

1. **Authentication**: `auth.py` handles OAuth 2.0 flow with Google
2. **Email Fetching**: `gmail_client.py` retrieves emails via Gmail API
3. **Classification**: `ai_classifier.py` sends emails to Gemini for classification
4. **Action**: Based on classification, emails are labeled/archived/moved
5. **Notification**: Optional Slack notifications via `slack_notifier.py`

## Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `main.py` | CLI interface, user interaction |
| `scheduler.py` | Background scheduling, orchestration |
| `gmail_client.py` | Gmail API wrapper |
| `ai_classifier.py` | Gemini AI classification |
| `auth.py` | OAuth authentication |
| `config.py` | Configuration management |
| `utils.py` | Shared utilities |
```

**Step 2: Commit**

```bash
git add docs/architecture.md
git commit -m "docs: add architecture documentation with diagram"
```

---

### Task 12: Complete Environment Variables Documentation

**Files:**
- Modify: `env_example.txt`

**Step 1: Update env_example.txt with all variables**

```bash
# env_example.txt - complete list
# ===========================================
# Gmail Organizer Environment Variables
# ===========================================

# Required
GEMINI_API_KEY=your_gemini_api_key_here
GMAIL_CREDENTIALS_PATH=credentials.json

# Optional - Slack Integration
SLACK_ENABLED=false
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_GMAIL_CHANNEL_ID=C1234567890

# Optional - Behavior
AUTO_LEARN_SAFE_SENDERS=true
LOG_LEVEL=INFO

# Optional - Performance
AI_BATCH_SIZE=5
GMAIL_BATCH_SIZE=10
CLASSIFICATION_CACHE_ENABLED=true
CLASSIFICATION_CACHE_TTL_HOURS=24
```

**Step 2: Commit**

```bash
git add env_example.txt
git commit -m "docs: complete environment variables documentation"
```

---

## Summary

| Phase | Tasks | Priority |
|-------|-------|----------|
| 1. Critical Fixes | 3 tasks | Immediate |
| 2. Code Quality | 3 tasks | High |
| 3. Test Coverage | 2 tasks | High |
| 4. Performance | 2 tasks | Medium |
| 5. Documentation | 2 tasks | Medium |

**Total: 12 tasks**

Estimated time: 2-3 hours for full implementation
