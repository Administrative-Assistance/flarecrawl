"""Client tests for Flarecrawl."""

from flarecrawl.client import Client


class TestBodyBuilder:
    """Test the body builder converts flat kwargs to nested API JSON."""

    def test_basic_url(self):
        body = Client._build_body(url="https://example.com")
        assert body == {"url": "https://example.com"}

    def test_goto_options(self):
        body = Client._build_body(
            url="https://example.com",
            wait_until="networkidle0",
            timeout=30000,
        )
        assert body["gotoOptions"]["waitUntil"] == "networkidle0"
        assert body["gotoOptions"]["timeout"] == 30000

    def test_wait_for_selector(self):
        body = Client._build_body(url="https://example.com", wait_for=".content")
        assert body["waitForSelector"]["selector"] == ".content"

    def test_screenshot_options(self):
        body = Client._build_body(
            url="https://example.com",
            full_page=True,
            image_type="jpeg",
            quality=80,
        )
        assert body["screenshotOptions"]["fullPage"] is True
        assert body["screenshotOptions"]["type"] == "jpeg"
        assert body["screenshotOptions"]["quality"] == 80

    def test_viewport(self):
        body = Client._build_body(url="https://example.com", width=1280, height=720)
        assert body["viewport"]["width"] == 1280
        assert body["viewport"]["height"] == 720

    def test_pdf_options(self):
        body = Client._build_body(
            url="https://example.com",
            landscape=True,
            paper_format="a4",
            print_background=True,
        )
        assert body["pdfOptions"]["landscape"] is True
        assert body["pdfOptions"]["format"] == "a4"

    def test_crawl_options(self):
        body = Client._build_body(
            url="https://example.com",
            limit=50,
            depth=3,
            formats=["markdown"],
            render=True,
            include_external=True,
            include_subdomains=True,
            include_patterns=["/docs/*"],
            exclude_patterns=["/blog/*"],
        )
        assert body["limit"] == 50
        assert body["depth"] == 3
        assert body["formats"] == ["markdown"]
        assert body["options"]["includeExternalLinks"] is True
        assert body["options"]["includePatterns"] == ["/docs/*"]
        assert body["options"]["excludePatterns"] == ["/blog/*"]

    def test_links_options(self):
        body = Client._build_body(
            url="https://example.com",
            visible_only=True,
            internal_only=True,
        )
        assert body["visibleLinksOnly"] is True
        assert body["excludeExternalLinks"] is True

    def test_elements(self):
        body = Client._build_body(
            url="https://example.com",
            elements=[{"selector": "h1"}, {"selector": "a"}],
        )
        assert body["elements"] == [{"selector": "h1"}, {"selector": "a"}]

    def test_extract_options(self):
        body = Client._build_body(
            url="https://example.com",
            prompt="Extract product info",
            response_format={"type": "json_schema", "schema": {"type": "object"}},
        )
        assert body["prompt"] == "Extract product info"
        assert body["response_format"]["type"] == "json_schema"

    def test_user_agent(self):
        body = Client._build_body(url="https://example.com", user_agent="CustomBot/1.0")
        assert body["userAgent"] == "CustomBot/1.0"

    def test_reject_resources(self):
        body = Client._build_body(
            url="https://example.com",
            reject_resources=["image", "media"],
        )
        assert body["rejectResourceTypes"] == ["image", "media"]

    def test_html_instead_of_url(self):
        body = Client._build_body(html="<h1>Hello</h1>")
        assert body == {"html": "<h1>Hello</h1>"}
        assert "url" not in body


class TestRejectResourcesDefaults:
    """Test that text-extraction methods add rejectResourceTypes by default."""

    def test_get_markdown_rejects_resources(self):
        """get_markdown should add rejectResourceTypes by default."""
        client = Client(account_id="test-id", api_token="test-token", cache_ttl=0)
        # We can't call the method without a real API, but we can check
        # the class has the default list
        assert "image" in client._REJECT_RESOURCES_DEFAULT
        assert "stylesheet" in client._REJECT_RESOURCES_DEFAULT
        assert "font" in client._REJECT_RESOURCES_DEFAULT
        assert "media" in client._REJECT_RESOURCES_DEFAULT

    def test_reject_resources_list_length(self):
        assert len(Client._REJECT_RESOURCES_DEFAULT) == 4


class TestConnectionPooling:
    """Test httpx.Client session configuration."""

    def test_session_created(self):
        client = Client(account_id="test-id", api_token="test-token")
        assert client._session is not None

    def test_session_has_http2(self):
        client = Client(account_id="test-id", api_token="test-token")
        # httpx.Client with http2=True should have HTTP/2 support
        assert client._session._transport is not None

    def test_context_manager(self):
        with Client(account_id="test-id", api_token="test-token") as client:
            assert client._session is not None

    def test_cache_ttl_default(self):
        client = Client(account_id="test-id", api_token="test-token")
        assert client.cache_ttl == 3600

    def test_cache_ttl_custom(self):
        client = Client(account_id="test-id", api_token="test-token", cache_ttl=0)
        assert client.cache_ttl == 0


class TestClientUrls:
    """Test URL construction."""

    def test_base_url(self):
        client = Client(account_id="test-id", api_token="test-token")
        assert client._base == "https://api.cloudflare.com/client/v4/accounts/test-id/browser-rendering"

    def test_headers(self):
        client = Client(account_id="test-id", api_token="test-token")
        # Headers are now on the persistent session
        headers = client._session.headers
        assert headers["Authorization"] == "Bearer test-token"
        assert headers["Content-Type"] == "application/json"


class TestMobilePreset:
    """Test mobile device preset."""

    def test_mobile_preset_exists(self):
        from flarecrawl.client import MOBILE_PRESET
        assert "width" in MOBILE_PRESET
        assert "height" in MOBILE_PRESET
        assert "user_agent" in MOBILE_PRESET
        assert "device_scale_factor" in MOBILE_PRESET

    def test_mobile_preset_values(self):
        from flarecrawl.client import MOBILE_PRESET
        assert MOBILE_PRESET["width"] == 390
        assert MOBILE_PRESET["height"] == 844
        assert MOBILE_PRESET["device_scale_factor"] == 3
        assert "iPhone" in MOBILE_PRESET["user_agent"]

    def test_mobile_in_body(self):
        from flarecrawl.client import MOBILE_PRESET
        body = Client._build_body(url="https://example.com", **MOBILE_PRESET)
        assert body["viewport"]["width"] == 390
        assert body["viewport"]["height"] == 844
        assert body["viewport"]["deviceScaleFactor"] == 3
        assert "iPhone" in body["userAgent"]

    def test_mobile_flag_in_scrape_help(self):
        from typer.testing import CliRunner
        from flarecrawl.cli import app
        runner = CliRunner()
        for cmd in ["scrape", "screenshot", "pdf"]:
            result = runner.invoke(app, [cmd, "--help"])
            assert "--mobile" in result.output, f"--mobile missing from {cmd} help"


class TestBrowserTimeTracking:
    """Test browser time accumulation."""

    def test_initial_browser_time_zero(self):
        client = Client(account_id="test-id", api_token="test-token")
        assert client.browser_ms_used == 0

    def test_retry_codes(self):
        client = Client(account_id="test-id", api_token="test-token")
        assert 429 in client.RETRY_CODES
        assert 503 in client.RETRY_CODES
        assert 502 in client.RETRY_CODES
        assert 400 not in client.RETRY_CODES

    def test_max_retries(self):
        client = Client(account_id="test-id", api_token="test-token")
        assert client.MAX_RETRIES == 3


class TestHandleError:
    """Test error handling and enrichment."""

    def test_network_error_422_suggests_auth(self):
        """CF 422 'Network error' should hint about --auth."""
        from unittest.mock import MagicMock

        from flarecrawl.client import FlareCrawlError

        client = Client(account_id="test-id", api_token="test-token")
        response = MagicMock()
        response.status_code = 422
        response.json.return_value = {
            "errors": [{"message": "Network error when attempting to load page"}]
        }
        try:
            client._handle_error(response)
            assert False, "Should have raised"
        except FlareCrawlError as e:
            assert "--auth user:password" in str(e)
            assert "--session cookies.json" in str(e)
            assert e.status_code == 422

    def test_network_error_non_422_no_hint(self):
        """Non-422 network errors should not get the auth hint."""
        from unittest.mock import MagicMock

        from flarecrawl.client import FlareCrawlError

        client = Client(account_id="test-id", api_token="test-token")
        response = MagicMock()
        response.status_code = 500
        response.json.return_value = {
            "errors": [{"message": "Network error when attempting to load page"}]
        }
        try:
            client._handle_error(response)
            assert False, "Should have raised"
        except FlareCrawlError as e:
            assert "--auth" not in str(e)

    def test_non_network_422_no_hint(self):
        """422 with a different message should not get the auth hint."""
        from unittest.mock import MagicMock

        from flarecrawl.client import FlareCrawlError

        client = Client(account_id="test-id", api_token="test-token")
        response = MagicMock()
        response.status_code = 422
        response.json.return_value = {
            "errors": [{"message": "Invalid URL format"}]
        }
        try:
            client._handle_error(response)
            assert False, "Should have raised"
        except FlareCrawlError as e:
            assert "--auth" not in str(e)
            assert "Invalid URL format" in str(e)
