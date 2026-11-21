import pytest

from hrrag.answer import Assistant, LLMAnswerer
from hrrag.config import Settings
from hrrag.retrieval import Retriever, visible


def test_role_filter_removes_restricted_passages(passages):
    emp = {passages[i].audience for i in visible(passages, "employee")}
    assert emp == {"employee"}
    assert {passages[i].audience for i in visible(passages, "hr")} == {"employee", "manager", "hr"}
    with pytest.raises(ValueError):
        visible(passages, "admin")


@pytest.mark.parametrize("method", ["bm25", "tfidf", "hybrid"])
def test_no_retriever_returns_restricted_passages(passages, method):
    r = Retriever(passages, method)
    for q in ("merit budget salary band", "performance improvement plan rating calibration", "pay equity"):
        hits, _ = r.search(q, role="employee", k=10)
        assert all(h.passage.audience == "employee" for h in hits)


def test_answers_carry_citations(retriever):
    a = Assistant(retriever).ask("How long can I take Elternzeit?")
    assert a.answered and "three years" in a.text
    assert a.citations[0]["pid"] == "HR-07#parental-leave"
    assert "[1]" in a.text


def test_declines_out_of_scope(retriever):
    for q in ("What is the capital of France?", "Write me a poem about cars", "", "   "):
        assert not Assistant(retriever).ask(q).answered


def test_long_input_is_truncated(retriever):
    a = Assistant(retriever).ask("vacation " * 400)
    assert a.latency_ms < 1000


def _llm(reply):
    return LLMAnswerer(Settings(llm_base_url="http://llm", llm_model="m"), transport=lambda payload: {"choices": [{"message": {"content": reply}}]})


def test_llm_answer_with_valid_citation_is_used(retriever):
    a = Assistant(retriever, answerer=_llm("You get 28 days of leave [1].")).ask("How many vacation days do I get?")
    assert a.engine == "llm" and a.text.startswith("You get 28") and a.citations[0]["n"] == 1


def test_llm_without_citations_falls_back_to_extractive(retriever):
    a = Assistant(retriever, answerer=_llm("You get lots of leave.")).ask("How many vacation days do I get?")
    assert "[1]" in a.text and "28" in a.text


def test_llm_citing_a_missing_passage_falls_back(retriever):
    a = Assistant(retriever, answerer=_llm("28 days [9].")).ask("How many vacation days do I get?")
    assert "[9]" not in a.text


def test_llm_not_found_declines(retriever):
    assert not Assistant(retriever, answerer=_llm("NOT_FOUND")).ask("How many vacation days do I get?").answered


def test_llm_errors_fall_back(retriever):
    def boom(payload):
        raise TimeoutError
    ans = LLMAnswerer(Settings(llm_base_url="http://llm", llm_model="m"), transport=boom)
    a = Assistant(retriever, answerer=ans).ask("How many vacation days do I get?")
    assert a.answered and "28" in a.text


def test_prompt_contains_only_given_passages(retriever):
    hits, _ = retriever.search("night shift allowance", role="employee")
    msgs = LLMAnswerer.prompt("night shift allowance", hits)
    assert "Use only the numbered passages" in msgs[0]["content"]
    assert msgs[1]["content"].count("[") >= len(hits)
