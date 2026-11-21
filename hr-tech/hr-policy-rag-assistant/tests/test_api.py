def test_health(client):
    st, body = client.request("GET", "/health")
    assert st == 200 and body["status"] == "ok" and body["passages"] > 40


def test_ask_redacts_and_logs(client):
    st, body = client.request("POST", "/api/ask", {"question": "My name is Lena Fischer, how long can I take Elternzeit?", "session": "t1"})
    assert st == 200 and body["answered"] and body["redacted"] == ["NAME"] and "query_id" in body
    store = client.app.state.store
    logged = store._exec("SELECT question FROM queries").fetchall()[0][0]
    assert "Lena" not in logged and "[NAME]" in logged


def test_identity_header_wins_over_body(client):
    st, body = client.request("POST", "/api/ask", {"question": "What is the merit budget for 2026?", "role": "hr"},
                              headers={"X-User-Role": "employee"})
    assert body["role"] == "employee" and not body["answered"]
    st, body = client.request("POST", "/api/ask", {"question": "What is the merit budget for 2026?"}, headers={"X-User-Role": "hr"})
    assert body["answered"] and "3.5 percent" in body["answer"]


def test_bad_requests(client):
    assert client.request("POST", "/api/ask", {"q": "x"})[0] == 400
    assert client.request("POST", "/api/ask", b"not json")[0] == 400
    assert client.request("POST", "/api/ask", {"question": "x" * 5000})[0] == 400
    assert client.request("POST", "/api/feedback", {"query_id": 1})[0] == 400


def test_feedback_and_stats_need_hr(client):
    st, body = client.request("POST", "/api/ask", {"question": "What is the night shift allowance?"})
    assert client.request("POST", "/api/feedback", {"query_id": body["query_id"], "helpful": True})[0] == 200
    assert client.request("GET", "/api/stats")[0] == 403
    st, stats = client.request("GET", "/api/stats", headers={"X-User-Role": "hr"})
    assert st == 200 and stats["questions"] == 1 and stats["helpful_share"] == 1.0


def test_rate_limit(client):
    codes = [client.request("POST", "/api/ask", {"question": "night allowance", "session": "flood"})[0] for _ in range(32)]
    assert codes[:30] == [200] * 30 and codes[-1] == 429


def test_policies_listing_respects_role(client):
    _, emp = client.request("GET", "/api/policies")
    _, hr = client.request("GET", "/api/policies", headers={"X-User-Role": "hr"})
    assert len(hr["policies"]) == len(emp["policies"]) + 2


def test_web_ui_served(client):
    st, html = client.request("GET", "/")
    assert st == 200 and b"HR policy assistant" in html
    assert client.request("GET", "/static/app.js")[0] == 200
