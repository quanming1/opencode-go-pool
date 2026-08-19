"""上游错误分类单测。"""

from opencode_pool.proxy.errors import ErrorKind, classify_upstream_status, json_error


def test_classify_ok():
    assert classify_upstream_status(200) == ErrorKind.OK
    assert classify_upstream_status(299) == ErrorKind.OK


def test_classify_quota_status_and_keywords():
    assert classify_upstream_status(429) == ErrorKind.QUOTA
    # 关键词命中优先于 auth（403 + rate limit → quota）
    assert classify_upstream_status(403, "rate limit exceeded") == ErrorKind.QUOTA
    assert classify_upstream_status(500, "quota exhausted") == ErrorKind.QUOTA
    assert classify_upstream_status(500, "RateLimitError") == ErrorKind.QUOTA


def test_classify_auth():
    assert classify_upstream_status(401) == ErrorKind.AUTH
    assert classify_upstream_status(403) == ErrorKind.AUTH
    # 403 带 quota 关键词 → quota 优先
    assert classify_upstream_status(403, "rate limit") == ErrorKind.QUOTA


def test_classify_bad_request():
    assert classify_upstream_status(400) == ErrorKind.BAD_REQUEST
    assert classify_upstream_status(422) == ErrorKind.BAD_REQUEST


def test_classify_server_and_network():
    assert classify_upstream_status(500) == ErrorKind.SERVER
    assert classify_upstream_status(502) == ErrorKind.SERVER
    assert classify_upstream_status(None) == ErrorKind.NETWORK


def test_json_error_shape():
    body = json_error(503, "no healthy account available")
    assert body["error"]["message"] == "no healthy account available"
    assert body["error"]["code"] == 503
    assert body["error"]["type"] == "proxy_error"
